#!/usr/bin/env python3
"""Manage the SLP OpenCode room (Supervisor / Lead / Peer) on an installed Paseo daemon.

The room is published in two Paseo layers, because Paseo splits the two jobs:

  * one derived provider per role (`opencode-supervisor`, `opencode-lead`,
    `opencode-peer`), each declaring `extends: opencode` plus its own label and
    model catalog. A provider entry carries the launch defaults an operator
    picks before naming an agent: the model (a model marked `isDefault` is the
    one Paseo suggests) and the thinking effort (a thinking option marked
    `isDefault` becomes the model's `defaultThinkingOptionId`). Providers cannot
    carry a role prompt or auto-accept, so they never replace the profiles.
  * one agent profile per role, still named after the role, bound to that role's
    derived provider. Profiles are Paseo's "named launch bundles": they carry the
    role prompt rendered from roles/<role>.md, `build` mode, auto-accept, and the
    pinned model + thinking effort.

Each derived role provider also carries an `env` overlay that Paseo merges into
the OpenCode server it launches for that seat. The room uses it to disable
OpenCode's own child agents, because Paseo owns the Supervisor/Lead/Peer
topology: a seat that could launch unmanaged children would bypass the reporting
and ownership contract. The overlay denies the `subagent` permission and drops
the built-in `general`/`explore` agents from that seat's catalog. Only the three
derived entries carry it — the base `opencode` provider keeps native subagents,
so the operator's own OpenCode work is unaffected.

sync also pins the base `opencode` provider entry's `enabled` flag and its
`command` override to the real OpenCode executable: npm installs put an
`opencode.CMD` shim on PATH, Node refuses to spawn `.cmd` shims without a
shell (EINVAL), and Paseo then silently falls back to its legacy OpenCode v1
integration, which requests API paths OpenCode v2 servers do not serve. Derived
providers inherit that pinned launch, so the executable path is owned in one
place. Paseo itself is operator-installed and is never built, patched, or
restarted by this repository.

Subcommands:
  sync        upsert the provider entry, the derived providers, and the three
              room profiles into the Paseo config, install the shared workspace
              protocol, reload the daemon.
  verify      read-only checks of the repo sources and the installed state.
  uninstall   remove exactly the artifacts sync manages.

All mutations back up the previous config first and are idempotent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "config" / "room.json"
ROLES_DIR = REPO_ROOT / "roles"
PROTOCOL_PATH = REPO_ROOT / "workflow" / "WORKSPACE_PROTOCOL.md"

PROTOCOL_INSTALL_SUBPATH = Path(".config") / "opencode-room" / "workflow" / "WORKSPACE_PROTOCOL.md"
PROFILE_ID_PREFIX = "agent_profile_"
BACKUP_DIRNAME = ".opencode-room-backups"
MANAGED_PROFILE_KEYS = ("provider", "model", "modeId", "thinkingOptionId", "featureValues", "notes")
PROVIDER_MANAGED_KEYS = ("enabled", "command")
# The whole derived entry is room-owned: it exists only because the spec declares it.
DERIVED_PROVIDER_MANAGED_KEYS = ("extends", "label", "description", "models", "env")
# Paseo accepts a custom provider id only in this alphabet, and derives a custom
# provider only when the id is not one of its built-in provider ids.
PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
BUILTIN_PROVIDER_IDS = ("claude", "codex", "copilot", "opencode", "pi", "omp")
LEGACY_STACK_PATTERN = re.compile(r"\b(?:codex|amp)\b", re.IGNORECASE)
SHIM_TARGET_PATTERN = re.compile(r'"([^"\n]*node_modules[^"\n]*opencode\.exe)"')

# Disabling OpenCode's native child agents for the room seats. Paseo owns the
# Supervisor/Lead/Peer topology, so a seat must not be able to spawn an agent of
# its own: an unmanaged child would sit outside the dispatch, ownership, and
# reporting contract. `permissions` is the enforcement layer — a configured deny
# cannot be approved away, and OpenCode filters any denied agent out of the
# `subagent` tool's catalog. `agents` removes the built-in `general`/`explore`
# subagents from the seat's catalog as well, so the capability is absent rather
# than merely refused.
NATIVE_AGENT_POLICY = {
    "permissions": [{"action": "subagent", "resource": "*", "effect": "deny"}],
    "agents": {
        "general": {"disabled": True},
        "explore": {"disabled": True},
    },
}
# Paseo merges a provider entry's `env` into the OpenCode server it launches for
# that provider; OpenCode layers OPENCODE_CONFIG_CONTENT over the discovered
# config documents, so the seat's permissions gain the deny rule and its agent
# catalog loses the built-in subagents. The user's own config files are untouched.
NATIVE_AGENT_ENV_KEY = "OPENCODE_CONFIG_CONTENT"


class RoomError(Exception):
    """A loud, user-facing failure."""


def load_spec() -> dict:
    try:
        return json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RoomError(f"missing room spec: {SPEC_PATH}")
    except json.JSONDecodeError as exc:
        raise RoomError(f"invalid JSON in {SPEC_PATH}: {exc}")


def role_notes(role: str) -> str:
    path = ROLES_DIR / f"{role}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RoomError(f"spec references role '{role}' but {path} is missing")
    text = text.replace("\r\n", "\n").strip("\n")
    if not text.strip():
        raise RoomError(f"role prompt is empty: {path}")
    return text


def render_profiles(spec: dict) -> list[dict]:
    """Build the full desired daemon.agentProfiles entries from the spec."""
    profiles = []
    seen = set()
    for entry in spec["agentProfiles"]:
        name = entry["name"]
        role = entry["role"]
        if role in seen:
            raise RoomError(f"duplicate role in spec: {role}")
        seen.add(role)
        profile = {
            "name": name,
            "provider": entry.get("providerId", spec["providerId"]),
            "model": entry["model"],
            "modeId": entry["modeId"],
            "featureValues": {"auto_accept": entry["autoAccept"]},
            "notes": role_notes(role),
        }
        # Optional per-model: a model without thinking options simply omits it.
        if entry.get("thinkingOptionId"):
            profile["thinkingOptionId"] = entry["thinkingOptionId"]
        profiles.append(profile)
    return profiles


def native_agents_enabled(spec: dict) -> bool:
    """Whether the room lets its seats keep OpenCode's own child agents."""
    return spec.get("nativeAgents") is not False


def native_agent_env() -> dict[str, str]:
    """The `env` overlay that removes OpenCode's native child agents from a seat."""
    return {NATIVE_AGENT_ENV_KEY: json.dumps(NATIVE_AGENT_POLICY)}


def render_providers(spec: dict) -> dict[str, dict]:
    """Build the desired `agents.providers` entries for the derived role providers.

    Paseo derives a provider from another provider when the entry declares
    `extends`; only a provider extending the bare `acp` protocol may pin its own
    `command`, so a derived provider inherits the base entry's launch — the one
    place where sync pins the real OpenCode executable. `models` replaces that
    provider's discovered catalog, so each role provider offers exactly the
    role's model, with the role's thinking effort marked as its default.

    Each derived entry also carries the native-agent `env` overlay unless the
    spec asks to keep them, so the seats lose OpenCode's child agents while the
    base `opencode` provider keeps them.
    """
    providers: dict[str, dict] = {}
    for entry in spec.get("providers", []):
        provider = {
            "extends": spec["providerId"],
            "label": entry["label"],
            "models": json.loads(json.dumps(entry["models"])),
        }
        if entry.get("description"):
            provider["description"] = entry["description"]
        if not native_agents_enabled(spec):
            provider["env"] = native_agent_env()
        providers[entry["id"]] = provider
    return providers


def validate_spec(spec: dict) -> list[str]:
    """Return the structural problems that make a spec unpublishable.

    Paseo accepts a role provider only if its id is one it can derive, and a
    profile only launches if it names a provider that exists, so a malformed
    spec must fail before sync writes anything.
    """
    problems: list[str] = []
    base_provider_id = spec.get("providerId")
    if not isinstance(base_provider_id, str) or not base_provider_id.strip():
        problems.append("spec is missing a non-empty providerId")
        base_provider_id = ""
    if not isinstance(spec.get("nativeAgents"), bool):
        problems.append("spec is missing a boolean nativeAgents flag")
    derived = spec.get("providers", [])
    if not isinstance(derived, list):
        problems.append("spec providers must be a list")
        derived = []
    declared: set[str] = set()
    for index, entry in enumerate(derived):
        where = f"providers[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object")
            continue
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not PROVIDER_ID_PATTERN.match(entry_id):
            problems.append(
                f"{where}.id must match {PROVIDER_ID_PATTERN.pattern}, got {entry_id!r}"
            )
        elif entry_id in BUILTIN_PROVIDER_IDS or entry_id == base_provider_id:
            problems.append(f"{where}.id {entry_id!r} is not a derivable provider id")
        elif entry_id in declared:
            problems.append(f"{where}.id {entry_id!r} is declared more than once")
        else:
            declared.add(entry_id)
        if not str(entry.get("label", "")).strip():
            problems.append(f"{where}.label must be a non-empty string")
        problems.extend(validate_models(entry.get("models"), where))
    seen_roles: set[str] = set()
    seen_names: set[str] = set()
    for index, entry in enumerate(spec.get("agentProfiles", [])):
        where = f"agentProfiles[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object")
            continue
        name = entry.get("name")
        role = entry.get("role")
        if not str(name or "").strip():
            problems.append(f"{where}.name must be a non-empty string")
        elif name in seen_names:
            problems.append(f"{where}.name {name!r} is declared more than once")
        else:
            seen_names.add(name)
        if not str(role or "").strip():
            problems.append(f"{where}.role must be a non-empty string")
        elif role in seen_roles:
            problems.append(f"{where}.role {role!r} is declared more than once")
        else:
            seen_roles.add(role)
        provider = entry.get("providerId", base_provider_id)
        if provider not in declared and provider != base_provider_id:
            problems.append(f"{where}.providerId {provider!r} is not a declared provider")
    return problems


def validate_models(models: object, where: str) -> list[str]:
    """Check one derived provider's `models` array against Paseo's schema."""
    if not isinstance(models, list) or not models:
        return [f"{where}.models must be a non-empty list"]
    problems: list[str] = []
    for index, model in enumerate(models):
        at = f"{where}.models[{index}]"
        if not isinstance(model, dict):
            problems.append(f"{at} must be an object")
            continue
        if not str(model.get("id", "")).strip():
            problems.append(f"{at}.id must be a non-empty string")
        if not str(model.get("label", "")).strip():
            problems.append(f"{at}.label must be a non-empty string")
        problems.extend(
            validate_thinking_options(model.get("thinkingOptions"), at, set_default_ok=True)
        )
    defaults = [m for m in models if isinstance(m, dict) and m.get("isDefault") is True]
    if len(defaults) > 1:
        problems.append(f"{where}.models marks more than one model as default")
    return problems


def validate_thinking_options(options: object, where: str, set_default_ok: bool = False) -> list[str]:
    """Check one model's `thinkingOptions` array against Paseo's schema."""
    if options is None:
        return []
    if not isinstance(options, list) or not options:
        return [f"{where}.thinkingOptions must be a non-empty list when present"]
    problems: list[str] = []
    for index, option in enumerate(options):
        at = f"{where}.thinkingOptions[{index}]"
        if not isinstance(option, dict):
            problems.append(f"{at} must be an object")
            continue
        if not str(option.get("id", "")).strip():
            problems.append(f"{at}.id must be a non-empty string")
        if not str(option.get("label", "")).strip():
            problems.append(f"{at}.label must be a non-empty string")
    defaults = [o for o in options if isinstance(o, dict) and o.get("isDefault") is True]
    if len(defaults) > 1:
        problems.append(f"{where}.thinkingOptions marks more than one option as default")
    return problems


def generate_profile_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    first = "".join(secrets.choice(alphabet) for _ in range(8))
    second = "".join(secrets.choice(alphabet) for _ in range(11))
    return PROFILE_ID_PREFIX + first + "_" + second


def resolve_opencode_binary() -> str:
    """Return the real OpenCode executable Paseo's daemon can spawn directly.

    npm installs create `opencode.CMD` shims. Node refuses to spawn `.cmd`
    and `.bat` files without a shell (spawn EINVAL), so Paseo's version probe
    fails and it silently falls back to the legacy OpenCode v1 integration,
    which requests root-path API endpoints that OpenCode v2 servers answer
    with the web UI's HTML page. Resolve the shim to the packaged
    `opencode.exe` so sync can pin it as the provider command.
    """
    found = shutil.which("opencode")
    if found is None:
        raise RoomError("'opencode' not found on PATH; install the OpenCode CLI first")
    resolved = Path(found)
    if resolved.suffix.lower() in (".exe", ".com"):
        return str(resolved)
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise RoomError(f"cannot read the opencode shim at {resolved} to resolve the real executable")
    match = SHIM_TARGET_PATTERN.search(text)
    if match is None:
        raise RoomError(
            f"cannot resolve the real opencode executable from the shim at {resolved}; "
            "reinstall the OpenCode CLI (npm install -g @opencode/cli)"
        )
    target = match.group(1)
    for token in ("%dp0%", "%~dp0", "$basedir"):
        target = target.replace(token, str(resolved.parent))
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = resolved.parent / candidate
    if not candidate.exists():
        raise RoomError(
            f"the opencode shim {resolved} points at {candidate}, which does not exist; "
            "reinstall the OpenCode CLI (npm install -g @opencode/cli)"
        )
    return str(candidate)


def desired_provider_entry(spec: dict) -> dict:
    """Render the provider keys this room manages from the spec and machine."""
    entry = dict(spec["provider"])
    entry["enabled"] = True
    entry["command"] = {"mode": "replace", "argv": [resolve_opencode_binary()]}
    return entry


def merge_provider(config: dict, spec: dict) -> bool:
    """Ensure the room provider entry exists with the managed keys correct.

    `enabled` and `command` are room-managed: the built-in opencode provider
    must be enabled and must launch the real OpenCode executable rather than
    an unspawnable npm shim. Any other keys in an existing entry are preserved
    untouched.
    """
    providers = config.setdefault("agents", {}).setdefault("providers", {})
    provider_id = spec["providerId"]
    desired = desired_provider_entry(spec)
    current = providers.get(provider_id)
    if current is None:
        providers[provider_id] = desired
        return True
    if not isinstance(current, dict):
        raise RoomError(f"agents.providers.{provider_id} in the Paseo config is not an object")
    merged = dict(current)
    for key, value in desired.items():
        merged[key] = value
    if merged == current:
        return False
    current.clear()
    current.update(merged)
    return True


def merge_providers(config: dict, spec: dict) -> bool:
    """Upsert the derived role providers; preserve every other provider entry.

    Each derived entry is wholly owned by the spec, so a managed key the desired
    entry does not carry is dropped — including the native-agent `env` overlay
    when the spec asks to keep native agents. Unrelated keys an operator added by
    hand (for example `enabled`, `order`, or `paseoTools`) survive.
    """
    providers = config.setdefault("agents", {}).setdefault("providers", {})
    if not isinstance(providers, dict):
        raise RoomError("agents.providers in the Paseo config is not an object")
    changed = False
    for provider_id, want in render_providers(spec).items():
        current = providers.get(provider_id)
        if current is None:
            providers[provider_id] = want
            changed = True
            continue
        if not isinstance(current, dict):
            raise RoomError(f"agents.providers.{provider_id} in the Paseo config is not an object")
        merged = dict(current)
        merged.update(want)
        for key in DERIVED_PROVIDER_MANAGED_KEYS:
            if key not in want:
                merged.pop(key, None)
        if merged != current:
            current.clear()
            current.update(merged)
            changed = True
    return changed


def unmerge_providers(config: dict, provider_ids: list[str]) -> bool:
    """Remove exactly the derived providers the spec declares."""
    providers = config.get("agents", {}).get("providers", {})
    if not isinstance(providers, dict):
        return False
    removed = False
    for provider_id in provider_ids:
        if providers.pop(provider_id, None) is not None:
            removed = True
    return removed


def merge_profiles(config: dict, desired: list[dict]) -> bool:
    """Upsert room profiles by name; preserve ids, other profiles, and order."""
    daemon = config.setdefault("daemon", {})
    existing = daemon.setdefault("agentProfiles", [])
    if not isinstance(existing, list):
        raise RoomError("daemon.agentProfiles in the Paseo config is not a list")
    changed = False
    by_name = {p.get("name"): p for p in existing if isinstance(p, dict)}
    for want in desired:
        current = by_name.get(want["name"])
        if current is None:
            entry = dict(want)
            entry["id"] = generate_profile_id()
            existing.append(entry)
            changed = True
            continue
        merged = dict(current)
        merged.update(want)
        # A managed key the desired entry does not carry is removed, so
        # dropping thinkingOptionId from the spec really removes it.
        for key in MANAGED_PROFILE_KEYS:
            if key not in want:
                merged.pop(key, None)
        if merged != current:
            current.clear()
            current.update(merged)
            changed = True
    return changed


def unmerge_profiles(config: dict, names: list[str]) -> bool:
    daemon = config.get("daemon", {})
    existing = daemon.get("agentProfiles", [])
    if not isinstance(existing, list):
        return False
    kept = [p for p in existing if not (isinstance(p, dict) and p.get("name") in names)]
    if len(kept) != len(existing):
        daemon["agentProfiles"] = kept
        return True
    return False


def paseo_config_path(home: Path) -> Path:
    return home / ".paseo" / "config.json"


def read_config(home: Path) -> dict:
    path = paseo_config_path(home)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RoomError(
            f"Paseo config not found: {path}\n"
            "Paseo must be installed and onboarded first (e.g. `paseo onboard`)."
        )
    except json.JSONDecodeError as exc:
        raise RoomError(f"invalid JSON in {path}: {exc}")


def write_config_atomic(path: Path, config: dict) -> None:
    payload = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix="config.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def backup_config(home: Path) -> Path | None:
    src = paseo_config_path(home)
    if not src.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    backup_dir = home / BACKUP_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / f"paseo-config-{stamp}.json"
    shutil.copy2(src, dst)
    return dst


def install_protocol(home: Path) -> bool:
    if not PROTOCOL_PATH.exists():
        raise RoomError(f"missing shared protocol: {PROTOCOL_PATH}")
    dst = home / PROTOCOL_INSTALL_SUBPATH
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = PROTOCOL_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    if dst.exists() and dst.read_text(encoding="utf-8") == text:
        return False
    dst.write_text(text, encoding="utf-8", newline="\n")
    return True


def remove_protocol(home: Path) -> bool:
    dst = home / PROTOCOL_INSTALL_SUBPATH
    if dst.exists():
        dst.unlink()
        # Drop the managed directories when they end up empty; keep anything else.
        for parent in (dst.parent, dst.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                pass
        return True
    return False


def daemon_reload(home: Path) -> str:
    """Ask a running daemon to reload config.json; never restart anything."""
    paseo = shutil.which("paseo")
    if not paseo:
        return "paseo CLI not found on PATH; start/restart the daemon to pick up the config"
    cmd = [paseo, "--home", str(home / ".paseo"), "daemon", "reload"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"daemon reload failed to run: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return f"daemon reload failed (exit {result.returncode}): {detail or 'no output'}"
    return ""


def verify_sources() -> list[str]:
    problems: list[str] = []
    spec = load_spec()
    problems.extend(validate_spec(spec))
    roles = sorted(p.stem for p in ROLES_DIR.glob("*.md"))
    wanted = sorted(entry["role"] for entry in spec["agentProfiles"])
    if roles != wanted:
        problems.append(f"roles/ files {roles} do not match spec roles {wanted}")
    for entry in spec["agentProfiles"]:
        try:
            notes = role_notes(entry["role"])
        except RoomError as exc:
            problems.append(str(exc))
            continue
        if "~/.config/opencode-room/" not in notes:
            problems.append(f"roles/{entry['role']}.md does not reference the opencode-room protocol path")
        if LEGACY_STACK_PATTERN.search(notes):
            problems.append(f"roles/{entry['role']}.md still mentions the legacy Codex/Amp stack")
    if not PROTOCOL_PATH.exists():
        problems.append(f"missing {PROTOCOL_PATH}")
    else:
        protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
        if "~/.config/opencode-room/" not in protocol:
            problems.append("WORKSPACE_PROTOCOL.md does not state its install path")
        if LEGACY_STACK_PATTERN.search(protocol):
            problems.append("WORKSPACE_PROTOCOL.md still mentions the legacy Codex/Amp stack")
    return problems


def verify_installed(home: Path, spec: dict, desired: list[dict]) -> list[str]:
    problems: list[str] = []
    config = read_config(home)
    providers = config.get("agents", {}).get("providers", {})
    if not isinstance(providers, dict):
        problems.append("agents.providers in the Paseo config is not an object")
        providers = {}
    provider_id = spec["providerId"]
    try:
        desired_provider = desired_provider_entry(spec)
    except RoomError as exc:
        problems.append(str(exc))
        desired_provider = None
    current_provider = providers.get(provider_id)
    if current_provider is None:
        problems.append(f"provider '{provider_id}' missing from ~/.paseo/config.json")
    elif not isinstance(current_provider, dict):
        problems.append(f"agents.providers.{provider_id} in the Paseo config is not an object")
    elif desired_provider is not None:
        for key in PROVIDER_MANAGED_KEYS:
            if current_provider.get(key) != desired_provider.get(key):
                problems.append(f"provider '{provider_id}' differs on '{key}'; run sync")
    for derived_id, want in render_providers(spec).items():
        current = providers.get(derived_id)
        if current is None:
            problems.append(f"derived provider '{derived_id}' missing from ~/.paseo/config.json; run sync")
            continue
        if not isinstance(current, dict):
            problems.append(f"agents.providers.{derived_id} in the Paseo config is not an object")
            continue
        for key in DERIVED_PROVIDER_MANAGED_KEYS:
            if current.get(key) != want.get(key):
                problems.append(f"derived provider '{derived_id}' differs on '{key}'; run sync")
    existing = {
        p.get("name"): p
        for p in config.get("daemon", {}).get("agentProfiles", [])
        if isinstance(p, dict)
    }
    for want in desired:
        current = existing.get(want["name"])
        if current is None:
            problems.append(f"agent profile '{want['name']}' missing; run sync")
            continue
        for key in MANAGED_PROFILE_KEYS:
            if current.get(key) != want.get(key):
                problems.append(f"agent profile '{want['name']}' differs on '{key}'; run sync")
    protocol_dst = home / PROTOCOL_INSTALL_SUBPATH
    if not protocol_dst.exists():
        problems.append(f"shared protocol missing at {protocol_dst}; run sync")
    elif protocol_dst.read_text(encoding="utf-8").replace("\r\n", "\n") != PROTOCOL_PATH.read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n"):
        problems.append(f"installed protocol differs from {PROTOCOL_PATH}; run sync")
    return problems


def cmd_sync(args: argparse.Namespace) -> int:
    home = args.home
    spec = load_spec()
    problems = validate_spec(spec)
    if problems:
        raise RoomError("invalid room spec:\n  - " + "\n  - ".join(problems))
    desired = render_profiles(spec)
    derived = render_providers(spec)
    config = read_config(home)
    provider_added = merge_provider(config, spec)
    providers_changed = merge_providers(config, spec)
    profiles_changed = merge_profiles(config, desired)
    protocol_changed = install_protocol(home)
    if not (provider_added or providers_changed or profiles_changed or protocol_changed):
        print("already in sync; nothing to do")
        reload_note = daemon_reload(home)
        if reload_note:
            print(f"note: {reload_note}")
        return 0
    backup = backup_config(home)
    write_config_atomic(paseo_config_path(home), config)
    print(f"config written: {paseo_config_path(home)}")
    if backup:
        print(f"backup: {backup}")
    print(f"provider '{spec['providerId']}': {'created or repaired' if provider_added else 'present (unchanged)'}")
    print(f"derived providers ({len(derived)}): {'updated' if providers_changed else 'present (unchanged)'}")
    print(f"agent profiles: {'updated' if profiles_changed else 'present (unchanged)'}")
    print(f"shared protocol: {'installed' if protocol_changed else 'present (unchanged)'}")
    reload_note = daemon_reload(home)
    if reload_note:
        print(f"note: {reload_note}")
    problems = verify_installed(home, spec, desired)
    if problems:
        print("post-sync verification failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("sync verified")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    problems = verify_sources()
    if args.source:
        for problem in problems:
            print(f"  - {problem}")
        print("source check:", "OK" if not problems else "FAILED")
        return 0 if not problems else 1
    if problems:
        print("source check failed:")
        for problem in problems:
            print(f"  - {problem}")
    spec = load_spec()
    desired = render_profiles(spec)
    installed = verify_installed(args.home, spec, desired)
    if installed:
        print("installed check failed:")
        for problem in installed:
            print(f"  - {problem}")
    else:
        print("installed check: OK")
    return 0 if not (problems or installed) else 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    home = args.home
    spec = load_spec()
    problems = validate_spec(spec)
    if problems:
        raise RoomError("invalid room spec:\n  - " + "\n  - ".join(problems))
    names = [entry["name"] for entry in spec["agentProfiles"]]
    derived_ids = list(render_providers(spec))
    config = read_config(home)
    profiles_removed = unmerge_profiles(config, names)
    derived_removed = unmerge_providers(config, derived_ids)
    provider_removed = False
    if args.purge_provider:
        providers = config.get("agents", {}).get("providers", {})
        if providers.pop(spec["providerId"], None) is not None:
            provider_removed = True
    protocol_removed = remove_protocol(home)
    if not (profiles_removed or derived_removed or provider_removed or protocol_removed):
        print("nothing managed by this room is installed")
        return 0
    backup = backup_config(home)
    write_config_atomic(paseo_config_path(home), config)
    if backup:
        print(f"backup: {backup}")
    if profiles_removed:
        print(f"removed agent profiles: {', '.join(names)}")
    if derived_removed:
        print(f"removed derived providers: {', '.join(derived_ids)}")
    if provider_removed:
        print(f"removed provider '{spec['providerId']}'")
    if protocol_removed:
        print(f"removed {home / PROTOCOL_INSTALL_SUBPATH}")
    reload_note = daemon_reload(home)
    if reload_note:
        print(f"note: {reload_note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    default_home = Path.home()

    p_sync = sub.add_parser("sync", help="publish the room into the installed Paseo config")
    p_sync.add_argument("--home", type=Path, default=default_home, help="operator home (default: ~)")
    p_sync.set_defaults(func=cmd_sync)

    p_verify = sub.add_parser("verify", help="read-only verification")
    p_verify.add_argument("--home", type=Path, default=default_home, help="operator home (default: ~)")
    p_verify.add_argument("--source", action="store_true", help="check repository sources only")
    p_verify.set_defaults(func=cmd_verify)

    p_uninstall = sub.add_parser("uninstall", help="remove the artifacts managed by this room")
    p_uninstall.add_argument("--home", type=Path, default=default_home, help="operator home (default: ~)")
    p_uninstall.add_argument(
        "--purge-provider", action="store_true", help="also remove the base opencode provider entry"
    )
    p_uninstall.set_defaults(func=cmd_uninstall)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RoomError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""Manage the SLP Amp room (Supervisor / Lead / Peer) on an installed Paseo daemon.

The room is three Paseo agent profiles backed by the `amp-acp` provider:
each profile pins a model effort level, `local` mode, auto-accept, and a role
prompt rendered from roles/<role>.md. Paseo itself is operator-installed and
is never built, patched, or restarted by this repository.

Subcommands:
  sync        upsert the provider and the three room profiles into the Paseo
              config, install the shared workspace protocol, reload the daemon.
  verify      read-only checks of the repo sources and the installed state.
  uninstall   remove exactly the artifacts sync manages.

All mutations back up the previous config first and are idempotent.
"""

from __future__ import annotations

import argparse
import json
import os
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
MANAGED_LABEL = "amp-room"

PROTOCOL_INSTALL_SUBPATH = Path(".config") / "amp-room" / "workflow" / "WORKSPACE_PROTOCOL.md"
PROFILE_ID_PREFIX = "agent_profile_"


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
        profiles.append(
            {
                "name": name,
                "provider": spec["providerId"],
                "model": entry["model"],
                "modeId": entry["modeId"],
                "featureValues": {"auto_accept": entry["autoAccept"]},
                "notes": role_notes(role),
            }
        )
    return profiles


def generate_profile_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    first = "".join(secrets.choice(alphabet) for _ in range(8))
    second = "".join(secrets.choice(alphabet) for _ in range(11))
    return PROFILE_ID_PREFIX + first + "_" + second


def merge_provider(config: dict, spec: dict) -> bool:
    """Ensure the room provider exists. Never modify an existing entry."""
    providers = config.setdefault("agents", {}).setdefault("providers", {})
    provider_id = spec["providerId"]
    if provider_id in providers:
        return False
    entry = dict(spec["provider"])
    entry["enabled"] = True
    amp_path = shutil.which("amp")
    if amp_path:
        entry.setdefault("env", {})["AMP_CLI_PATH"] = amp_path
    providers[provider_id] = entry
    return True


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
        merged["provider"] = want["provider"]
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
    backup_dir = home / ".amp-room-backups"
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
        if "~/.config/amp-room/" not in notes:
            problems.append(f"roles/{entry['role']}.md does not reference the amp-room protocol path")
        if "codex" in notes.lower().replace("amp-room", ""):
            problems.append(f"roles/{entry['role']}.md still mentions Codex")
    if not PROTOCOL_PATH.exists():
        problems.append(f"missing {PROTOCOL_PATH}")
    else:
        protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
        if "~/.config/amp-room/" not in protocol:
            problems.append("WORKSPACE_PROTOCOL.md does not state its install path")
    return problems


def verify_installed(home: Path, spec: dict, desired: list[dict]) -> list[str]:
    problems: list[str] = []
    config = read_config(home)
    providers = config.get("agents", {}).get("providers", {})
    provider_id = spec["providerId"]
    if provider_id not in providers:
        problems.append(f"provider '{provider_id}' missing from ~/.paseo/config.json")
    elif providers[provider_id].get("enabled") is not True:
        problems.append(f"provider '{provider_id}' is not enabled")
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
        for key in ("provider", "model", "modeId", "featureValues", "notes"):
            if current.get(key) != want[key]:
                problems.append(f"agent profile '{want['name']}' differs on '{key}'; run sync")
    protocol_dst = home / PROTOCOL_INSTALL_SUBPATH
    if not protocol_dst.exists():
        problems.append(f"shared protocol missing at {protocol_dst}; run sync")
    elif protocol_dst.read_text(encoding="utf-8").replace("\r\n", "\n") != PROTOCOL_PATH.read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n"):
        problems.append(f"installed protocol differs from {PROTOCOL_PATH}; run sync")
    for tool in ("amp", "amp-acp"):
        if shutil.which(tool) is None:
            problems.append(f"'{tool}' not found on PATH")
    return problems


def cmd_sync(args: argparse.Namespace) -> int:
    home = args.home
    spec = load_spec()
    desired = render_profiles(spec)
    config = read_config(home)
    provider_added = merge_provider(config, spec)
    profiles_changed = merge_profiles(config, desired)
    protocol_changed = install_protocol(home)
    if not (provider_added or profiles_changed or protocol_changed):
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
    print(f"provider '{spec['providerId']}': {'created' if provider_added else 'present (untouched)'}")
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
    names = [entry["name"] for entry in spec["agentProfiles"]]
    config = read_config(home)
    profiles_removed = unmerge_profiles(config, names)
    provider_removed = False
    if args.purge_provider:
        providers = config.get("agents", {}).get("providers", {})
        if providers.pop(spec["providerId"], None) is not None:
            provider_removed = True
    protocol_removed = remove_protocol(home)
    if not (profiles_removed or provider_removed or protocol_removed):
        print("nothing managed by this room is installed")
        return 0
    backup = backup_config(home)
    write_config_atomic(paseo_config_path(home), config)
    if backup:
        print(f"backup: {backup}")
    if profiles_removed:
        print(f"removed agent profiles: {', '.join(names)}")
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
        "--purge-provider", action="store_true", help="also remove the amp-acp provider entry"
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
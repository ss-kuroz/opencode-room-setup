# OpenCode Room Setup

Reproducible configuration for a three-role OpenCode room (SLP: Supervisor,
Lead, Peer) running through an **operator-installed** Paseo daemon:

```text
Paseo daemon (installed on the machine, ~/.paseo/config.json)
  -> daemon.agentProfiles "opencode-supervisor | opencode-lead | opencode-peer"
       provider opencode (Paseo built-in), mode build, auto_accept
  -> opencode (ACP server built into the OpenCode CLI)
  -> Ollama Cloud models resolved by OpenCode: minimax-m3 / glm-5.3 /
       glm-5.3-flash, with thinking effort medium / high / low
  -> shared contract at ~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md
```

This repository does **not** install Paseo, OpenCode, or Ollama, and it does
not manage any of their state. It owns exactly three things and re-applies them
idempotently:

| Repository source | Local destination |
| --- | --- |
| `config/room.json` + `roles/*.md` | `~/.paseo/config.json` → provider entry `opencode` and the three `daemon.agentProfiles` entries |
| `workflow/WORKSPACE_PROTOCOL.md` | `~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md` |
| (backup of every config it rewrites) | `~/.opencode-room-backups/` |

Everything else in `~/.paseo/config.json` — daemon settings, other providers,
other agent profiles (including the Amp room's `amp-*` profiles), plugins — is
preserved untouched. Sync never restarts the daemon; it asks a running daemon
to `reload` its config.

The provider entry is pinned, not just created: `sync` keeps
`agents.providers.opencode.enabled` true and its `command` override pointed at
the real OpenCode executable, resolved from the npm shim at sync time.
Without that override Paseo resolves `opencode` on PATH to the npm
`opencode.CMD` shim, which its daemon cannot spawn; it then silently falls
back to the legacy OpenCode v1 integration and every agent fails with
"Request is not supported by this version of OpenCode Server".

## Prerequisites

- Paseo installed, onboarded, and running (`paseo daemon status`).
- OpenCode CLI v2.0.10+ on PATH (`opencode --version`); v2.0.29 was
  verified. Its ACP server is built in — no adapter install.
- Ollama Cloud authenticated inside OpenCode
  (`paseo provider diagnostic opencode` must show a stored API key;
  `opencode auth login` otherwise).
- Python 3.11+ (stdlib only).

## Usage

```bash
python scripts/room.py sync      # publish provider + profiles + protocol, reload daemon
python scripts/room.py verify    # read-only check of repo sources and installed state
python scripts/room.py verify --source   # source-only check, no HOME access
python scripts/room.py uninstall # remove exactly the managed artifacts
make test                        # unit tests for the merge/render logic
```

`sync` is idempotent and is also the repair path: if the Paseo Desktop UI
deletes or edits a room profile, re-run `sync` to restore it. Profile `id`s of
existing same-named profiles are preserved, so agents and schedules referencing
them keep working.

## Roles

| Profile | Provider | Model (Ollama Cloud) | Thinking | Mode | Auto-accept |
| --- | --- | --- | --- | --- | --- |
| `opencode-supervisor` | `opencode` | `minimax-m3` | `medium` | `build` | yes |
| `opencode-lead` | `opencode` | `glm-5.3` | `high` | `build` | yes |
| `opencode-peer` | `opencode` | `glm-5.3-flash` | `low` | `build` | yes |

Human retains product, cost, external-effect, and irreversible-risk decisions.
Supervisor routes Human intent and bounded recovery. Lead owns technical
framing, dependency order, verification, and explicit candidate acceptance.
Peer owns one bounded outcome and returns an immutable candidate or a concrete
block signal. Role authority lives in `roles/*.md`; the shared coordination
contract lives in `workflow/WORKSPACE_PROTOCOL.md`. Read
[docs/architecture.md](docs/architecture.md) before changing these boundaries.

## Where to edit

- Role prompt or authority: `roles/<role>.md`.
- Model, thinking effort, mode, auto-accept, or profile names:
  `config/room.json`. Thinking options are per-model — list valid values with
  `paseo provider models opencode` (e.g. `glm-5.3` has no `medium`).
- Shared coordination rules: `workflow/WORKSPACE_PROTOCOL.md`.
- Merge/render behavior: `scripts/room.py` and `tests/test_room.py`.

Never hand-edit `~/.paseo/config.json` room entries; they are regenerated. No
secret, session, log, or keypair belongs in this repository.

## History

This repository continues the codex-room-setup lineage: it is a fork of
[hoangnb24/codex-room-setup](https://github.com/hoangnb24/codex-room-setup),
which was refactored from per-role `CODEX_HOME` runtimes into the Amp room and
is now converted to an OpenCode room — roles are Paseo agent profiles on the
built-in `opencode` provider, and models come from Ollama Cloud through the
operator's OpenCode install. The former amp-room-setup repository was retired
when this room replaced it; its live Paseo profiles were uninstalled with
`room.py uninstall --purge-provider`.
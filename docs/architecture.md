# Architecture

## Control flow

```text
~/.paseo/config.json                     (owned by the operator's Paseo install)
  daemon.agentProfiles[]                 (managed by scripts/room.py sync)
    "SLP - Supervisor"  amp-acp / medium / local / auto_accept
    "SLP - Lead"        amp-acp / high   / local / auto_accept
    "SLP - Peer"        amp-acp / low    / local / auto_accept
  agents.providers["amp-acp"]            (created if absent, never modified)
      |
      v
amp-acp (ACP adapter on PATH) -> Amp CLI -> model + effort from the profile
      |
      v
~/.config/amp-room/workflow/WORKSPACE_PROTOCOL.md   (installed by sync)
```

There is no generated runtime anymore. The former `~/.codex-runtime/<role>`
isolation is unnecessary: Paseo gives each agent its own session, and Amp owns
its own state. A role is fully described by its agent profile entry.

## Ownership

| Layer | Owner | Mutable state |
| --- | --- | --- |
| `~/.paseo` | Paseo (operator-installed) | Daemon, sessions, agents, projects, worktrees, identity |
| `~/.paseo/config.json` room entries | `scripts/room.py sync` | Provider `amp-acp` + the three `daemon.agentProfiles` |
| Rest of `~/.paseo/config.json` | Operator / Paseo Desktop | Never rewritten by this repository |
| `~/.config/amp-room/workflow/` | This repository | The shared `WORKSPACE_PROTOCOL.md` |
| Amp CLI (`~/.amp`) | Amp | Auth, threads, settings |
| `roles/*.md`, `config/room.json`, `workflow/` | This repository | Role prompts, room spec, shared contract |

## Merge semantics

`sync` renders the desired profiles from `config/room.json` (models, mode,
auto-accept) plus `roles/<role>.md` (the `notes` prompt), then upserts them
into `daemon.agentProfiles` **by name**:

- A missing profile is appended with a generated `agent_profile_<8>_<11>` id.
- An existing same-named profile is updated in place; its `id` and position are
  preserved, so Paseo agents and schedules that reference the profile keep
  working.
- Profiles with other names are never touched or reordered.
- The `amp-acp` provider entry is created only when absent; an existing entry
  (including a machine-specific `AMP_CLI_PATH`) is left untouched.
- The previous config is copied to `~/.amp-room-backups/` before each write,
  and the write itself is atomic (temp file + replace).
- After writing, sync asks a running daemon to `reload`; it never restarts the
  daemon or interrupts running agents.

`verify` compares the installed state (config entries, installed protocol,
`amp`/`amp-acp` on PATH) against the rendered desired state and reports drift.
`uninstall` removes exactly the three profiles by name, the installed protocol
file, and (with `--purge-provider`) the provider entry — nothing else.

## Failure modes

- The Paseo Desktop UI can edit or delete agent profiles at any time. This is
  expected operator state, not corruption: re-run `sync` to restore the room.
- If the daemon is stopped, sync still writes the config and notes that the
  next daemon start will pick it up.
- `sync` fails loudly when `~/.paseo/config.json` is missing or invalid JSON:
  Paseo must be installed and onboarded first.

## Role boundaries

Role authority lives in `roles/*.md` and the shared coordination contract in
`workflow/WORKSPACE_PROTOCOL.md`. Both are read by the agents at session
start; the protocol file is referenced from every role prompt via its install
path `~/.config/amp-room/workflow/WORKSPACE_PROTOCOL.md`. Changing a role
means editing those files and re-running `sync`, then starting new sessions —
existing sessions keep the instructions they were created with.
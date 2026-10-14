# Architecture

## Control flow

```text
~/.paseo/config.json                     (owned by the operator's Paseo install)
  daemon.agentProfiles[]                 (managed by scripts/room.py sync)
    "opencode-supervisor"  opencode / ollama-cloud/minimax-m3    / thinking medium / build / auto_accept
    "opencode-lead"        opencode / ollama-cloud/glm-5.3       / thinking high   / build / auto_accept
    "opencode-peer"        opencode / ollama-cloud/glm-5.3-flash  / thinking low    / build / auto_accept
  agents.providers["opencode"]            (created as {"enabled": true} if absent, never modified)
      |
      v
opencode (Paseo built-in provider -> OpenCode CLI ACP server)
  -> model + thinking effort from the profile, resolved against the
     operator's OpenCode config (Ollama Cloud provider, authenticated)
      |
      v
~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md   (installed by sync)
```

There is no generated runtime. Paseo gives each agent its own session, and
OpenCode owns its own state (auth, sessions, plugins under
`~/.config/opencode` / `~/.local/share/opencode`). A role is fully described
by its agent profile entry.

## Ownership

| Layer | Owner | Mutable state |
| --- | --- | --- |
| `~/.paseo` | Paseo (operator-installed) | Daemon, sessions, agents, projects, worktrees, identity |
| `~/.paseo/config.json` room entries | `scripts/room.py sync` | Provider entry `opencode` + the three `daemon.agentProfiles` |
| Rest of `~/.paseo/config.json` | Operator / Paseo Desktop | Never rewritten by this repository |
| `~/.config/opencode-room/workflow/` | This repository | The shared `WORKSPACE_PROTOCOL.md` |
| OpenCode CLI (`~/.config/opencode`, `~/.local/share/opencode`) | OpenCode | Ollama Cloud auth, sessions, plugins |
| `roles/*.md`, `config/room.json`, `workflow/` | This repository | Role prompts, room spec, shared contract |

## Merge semantics

`sync` renders the desired profiles from `config/room.json` (models, thinking
effort, mode, auto-accept) plus `roles/<role>.md` (the `notes` prompt), then
upserts them into `daemon.agentProfiles` **by name**:

- A missing profile is appended with a generated `agent_profile_<8>_<11>` id.
- An existing same-named profile is updated in place; its `id` and position are
  preserved, so Paseo agents and schedules that reference the profile keep
  working.
- A managed key the desired entry does not carry — `thinkingOptionId` for a
  model without thinking options — is removed from the installed profile, so
  deleting it from the spec really deletes it.
- Profiles with other names (including the Amp room's) are never touched or
  reordered.
- The `opencode` provider is built into Paseo; this room manages two keys of
  its entry: `enabled: true` and a `command` override
  `{"mode": "replace", "argv": [<real opencode.exe>]}`. The exe path is
  resolved at sync time by parsing the npm shim (`shutil.which` finds
  `opencode.CMD`, which the daemon's Node cannot spawn without a shell;
  without the override Paseo falls back to its legacy v1 integration and
  every request returns the web UI's HTML page). Other keys in the entry are
  preserved.
- The previous config is copied to `~/.opencode-room-backups/` before each
  write, and the write itself is atomic (temp file + replace).
- After writing, sync asks a running daemon to `reload`; it never restarts the
  daemon or interrupts running agents.

`verify` compares the installed state (config entries, installed protocol,
`opencode` on PATH) against the rendered desired state and reports drift.
`uninstall` removes exactly the three profiles by name, the installed protocol
file, and (with `--purge-provider`) the provider entry — nothing else.

## Failure modes

- The Paseo Desktop UI can edit or delete agent profiles at any time. This is
  expected operator state, not corruption: re-run `sync` to restore the room.
- If the daemon is stopped, sync still writes the config and notes that the
  next daemon start will pick it up.
- `sync` fails loudly when `~/.paseo/config.json` is missing or invalid JSON:
  Paseo must be installed and onboarded first.
- If the OpenCode CLI is missing or logged out of Ollama Cloud, the profiles
  still exist but agents cannot start; `paseo provider diagnostic opencode`
  shows the cause, and `verify` fails when the real executable cannot be
  resolved.
- If the provider entry loses its `command` override (for example after a
  Paseo reset), Paseo resolves `opencode` on PATH again, hits the npm
  `opencode.CMD` shim, and silently falls back to the legacy v1
  integration: agents fail with "Request is not supported by this version of
  OpenCode Server (Server responded with text/html)". Re-run `sync` to
  repair the override.
- Model and thinking ids can drift when the OpenCode/Ollama catalog changes.
  `paseo provider models opencode` lists what Paseo can currently see; update
  `config/room.json` to match.

## Role boundaries

Role authority lives in `roles/*.md` and the shared coordination contract in
`workflow/WORKSPACE_PROTOCOL.md`. Both are read by the agents at session
start; the protocol file is referenced from every role prompt via its install
path `~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md`. Changing a role
means editing those files and re-running `sync`, then starting new sessions —
existing sessions keep the instructions they were created with.
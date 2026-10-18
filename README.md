# OpenCode Room Setup

Reproducible configuration for a three-role OpenCode room (SLP: Supervisor,
Lead, Peer) running through an **operator-installed** Paseo daemon:

```text
Paseo daemon (installed on the machine, ~/.paseo/config.json)
  -> agents.providers "opencode-supervisor | opencode-lead | opencode-peer"
       one derived provider per role ("extends": "opencode", own label) whose
       model catalog is exactly the role's model, with the role's thinking
       effort marked as the provider-level default
       each entry also carries env: OPENCODE_CONFIG_DIR -> that seat's config
       directory (the seat's role prompt), plus the native-agent policy in
       OPENCODE_CONFIG_CONTENT
  -> daemon.agentProfiles "opencode-supervisor | opencode-lead | opencode-peer"
       one profile per role, bound to that role's derived provider: mode build,
       auto_accept, the pinned model and thinking effort, and the role prompt
       from roles/<role>.md in `notes` (chooser metadata, not a system prompt)
  -> opencode (ACP server built into the OpenCode CLI)
  -> Ollama Cloud models resolved by OpenCode: deepseek-v4.1-flash:1017 /
       deepseek-v4-pro / deepseek-v4.1-flash:1017, with thinking effort low / max / low
  -> files installed by sync per seat, which the seat's prompt is built from:
       ~/.config/opencode-room/seats/<provider>/agents/build.md
       ~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md
```

This repository does **not** install Paseo, OpenCode, or Ollama, and it does
not manage any of their state. It owns exactly three things and re-applies them
idempotently:

| Repository source | Local destination |
| --- | --- |
| `config/room.json` + `roles/*.md` | `~/.paseo/config.json` → the three derived entries in `agents.providers` and the three `daemon.agentProfiles` entries |
| `roles/<role>.md` + `workflow/WORKSPACE_PROTOCOL.md` | `~/.config/opencode-room/seats/<provider>/agents/build.md` (the seat's prompt) |
| `workflow/WORKSPACE_PROTOCOL.md` | `~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md` |
| (backup of every config it rewrites) | `~/.opencode-room-backups/` |

The room is published in two Paseo layers because Paseo splits the two jobs. A
**provider** entry carries what an operator picks before naming an agent — the
model, and the thinking effort behind that model — while an **agent profile**
carries `build` mode, auto-accept, and the pinned model + thinking. Providers
cannot hold those, so the derived providers never replace the profiles; together
they are the room. Because Paseo's provider list is fed by `agents.providers`, the
three roles show up there as `OpenCode - Supervisor / Lead / Peer`, each
suggesting its own model and thinking effort.

Neither layer delivers a prompt to the agent. An agent profile's `notes` are
chooser metadata — Paseo shows them in its profile list and returns them to
callers of its `list_profiles` tool — and a profile deliberately carries no system
prompt, because Paseo's session `systemPrompt` is creation-only: a profile holding
one would apply to a new agent and silently do nothing when applied to a running
one. The role contract therefore travels through the seat's own OpenCode server:
`sync` writes `~/.config/opencode-room/seats/<provider>/agents/build.md`, whose body
is the seat's prompt (its role contract plus the shared protocol), and the
provider's `env` points `OPENCODE_CONFIG_DIR` at that directory. OpenCode reads the
directory when it starts the seat's server, so the seat begins with the authority
boundary it was dispatched under.

Everything else in `~/.paseo/config.json` — daemon settings, other providers,
other agent profiles, plugins — is preserved untouched. Sync never restarts the
daemon; it asks a running daemon to `reload` its config.

The base provider entry is pinned, not just created: `sync` keeps
`agents.providers.opencode.enabled` true and its `command` override pointed at
the real OpenCode executable, resolved from the npm shim at sync time. The
derived role providers inherit that pinned launch, so the executable path is
owned in exactly one place. Without that override Paseo resolves `opencode` on
PATH to the npm `opencode.CMD` shim, which its daemon cannot spawn; it then
silently falls back to the legacy OpenCode v1 integration and every agent fails
with "Request is not supported by this version of OpenCode Server".

One cost of the provider layer: Paseo runs one OpenCode server per provider id,
so the three role providers can hold up to three `opencode` server processes
while agents are running, instead of one for the whole room.

Each role provider also carries an `env` overlay that Paseo merges into the OpenCode
server it launches for that seat, and it does two jobs. First, it is how a seat gets
its role: `OPENCODE_CONFIG_DIR` names the seat's config directory, whose
`agents/build.md` is the seat's prompt (role contract + shared protocol), so the seat
starts with the authority boundary it was dispatched under. Second,
`OPENCODE_CONFIG_CONTENT` denies the `subagent` permission and removes OpenCode's
built-in `general` and `explore` child agents, so a room seat has no OpenCode-native
child-agent tool — Paseo owns the Supervisor/Lead/Peer topology, and an agent spawned
by a seat would sit outside the dispatch, ownership, and reporting contract. Paseo's
bridge tools still reach every seat (Lead dispatches through them); the Peer's
provider adds a `paseoTools` policy that removes agent creation and lifecycle tools,
leaving reads and `send_agent_prompt`.
`config/room.json`'s `nativeAgents: false` turns that second half on; the role half is
always on. The base `opencode` provider is left alone, so the operator keeps native
subagents and their own prompt in their own OpenCode work.

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
python scripts/room.py sync      # publish provider + profiles + protocol + seat prompts, reload daemon
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
| `opencode-supervisor` | `opencode-supervisor` | `deepseek-v4.1-flash:1017` | `low` | `build` | yes |
| `opencode-lead` | `opencode-lead` | `deepseek-v4-pro` | `max` | `build` | yes |
| `opencode-peer` | `opencode-peer` | `deepseek-v4.1-flash:1017` | `low` | `build` | yes |

Each profile is bound to the derived provider of the same name, whose catalog
offers that role's model with the role's thinking effort as the provider-level
default (`isDefault` in `config/room.json`). `paseo provider ls` shows the three
role providers next to the base `opencode` provider.

Human retains product, cost, external-effect, and irreversible-risk decisions.
Supervisor routes Human intent and bounded recovery, and answers a Lead's
bounded question about scope, priority, authority, or intent from evidence (or
routes it to Human) without becoming the technical Lead. Lead owns technical
framing, dependency order, verification, and explicit candidate acceptance.
Peer owns one bounded outcome and returns an immutable candidate or a concrete
block signal. Every dispatch names a return channel — the assigning session's
agent id — and Lead reports completion upward as a background message with
notify-on-finish, so a finished result is never left silent; Lead also reports
when it runs out of ready work. Role authority lives in `roles/*.md`; the shared
coordination contract lives in `workflow/WORKSPACE_PROTOCOL.md`. Read
[docs/architecture.md](docs/architecture.md) before changing these boundaries.

## Where to edit

- Role prompt or authority: `roles/<role>.md`. `sync` re-renders each seat's
  `agents/build.md` — the prompt its OpenCode server loads — and refreshes the role
  prompt in the profile's `notes`; a session already running keeps the prompt it
  started with, so create a new agent to exercise the change.
- Model, thinking effort, mode, auto-accept, profile names, and the derived
  role providers (id, label, model catalog, and whether the seats keep
  OpenCode's native child agents — `nativeAgents`): `config/room.json`. Thinking
  options are per-model — list valid values with
  `paseo provider models opencode` (e.g. `deepseek-v4-pro` has no `low` and
  offers only `high`, `max`, while `deepseek-v4.1-flash:1017` offers `low`, `high`,
  `max`). A derived
  provider's `models` array *replaces* that provider's discovered catalog, so
  list every model and thinking option that role provider should offer.
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
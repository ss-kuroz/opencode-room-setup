# Architecture

## Control flow

```text
~/.paseo/config.json                     (owned by the operator's Paseo install)
  agents.providers[]                     (managed by scripts/room.py sync)
    "opencode"            command argv -> real opencode.exe (Paseo's default enabled)
    "opencode-supervisor"  extends opencode / deepseek-v4.1-flash:1017 (default) / thinking low  (default)
    "opencode-lead"        extends opencode / deepseek-v4-pro     (default) / thinking max  (default)
    "opencode-peer"        extends opencode / deepseek-v4.1-flash:1017 (default) / thinking low  (default)
                           each derived entry also carries env:
                             OPENCODE_CONFIG_DIR -> that seat's config directory,
                               whose agents/build.md is the seat's prompt
                             OPENCODE_CONFIG_CONTENT -> native-agent policy
  daemon.agentProfiles[]                 (managed by scripts/room.py sync)
    "opencode-supervisor"  provider opencode-supervisor / deepseek-v4.1-flash:1017 / thinking low  / build / auto_accept
    "opencode-lead"        provider opencode-lead       / deepseek-v4-pro     / thinking max  / build / auto_accept
    "opencode-peer"        provider opencode-peer       / deepseek-v4.1-flash:1017 / thinking low  / build / auto_accept
      |
      v
opencode (Paseo built-in provider -> OpenCode CLI ACP server)
  -> model + thinking effort from the profile, resolved against the
     operator's OpenCode config (Ollama Cloud provider, authenticated)
  -> files installed by sync, which build that seat's prompt:
       ~/.config/opencode-room/seats/<provider>/agents/build.md
       ~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md
```

There is no generated runtime. Paseo gives each agent its own session, and
OpenCode owns its own state (auth, sessions, plugins under
`~/.config/opencode` / `~/.local/share/opencode`). A role is fully described
by its derived provider entry plus its agent profile entry.

## Reporting loop

Paseo arms a finish notification per `send_agent_prompt` call, so events cover a
directly prompted turn but not the turn a Lead resumes when its Peer finishes.
Two channels close that gap: the dispatch envelope names the assigning session's
own agent id (from `PASEO_AGENT_ID`) as the return address, and Lead keeps the
project's work-status source current as a status surface. Supervisor reads the
Lead's lifecycle state, recent activity, and that surface on each wake before
concluding that nothing happened, asks once when an idle Lead still has an open
assignment, and relays the outcome to Human. A Lead that cannot settle scope,
priority, authority, or intent asks the Supervisor one bounded question and
continues its unrelated ready work meanwhile; the Supervisor answers from
evidence, routes a Human decision to Human, or says no evidence supports an
answer — without taking over the project's technical decisions.

## Why two layers

Paseo keeps launch defaults and instructions in different places, and only one
of them can carry the launch-time choices:

| Layer | Carries | Cannot carry |
| --- | --- | --- |
| `agents.providers.<role>` | the provider the operator picks, its label, its model catalog, the model's default thinking effort, and the `env` overlay that reaches that seat's OpenCode server | an auto-accept flag; a default mode |
| `daemon.agentProfiles.<role>` | `modeId`, `auto_accept`, the pinned model + thinking, and `notes` | a system prompt — Paseo's profiles deliberately carry none |
| `~/.config/opencode-room/seats/<provider>/agents/build.md` | the seat's prompt: its role contract and the shared protocol | — |

So the derived provider exists to make the three seats visible and correctly
defaulted in Paseo's provider list, and the profile exists because it is the
only Paseo object that can pin `modeId` and auto-accept. `modeId` is not
settable on a provider at all: for `opencode` it selects an agent *inside*
OpenCode, which the operator can rename or delete at will, so Paseo refuses to
hardcode one.

Paseo's rule for a derived provider (`extends` other than `acp`): the entry must
declare `label`, it inherits the base provider's launch settings, and a
non-empty `models` array replaces the catalog discovered from the provider.
That is why the role providers never declare `command` themselves — the base
`opencode` entry owns the resolved executable path.

## How a seat gets its role

`notes` is not the role prompt. Paseo defines it as free text that is *surfaced
to orchestrating agents by its `list_profiles` tool* — it appears in the Desktop
profile list and in that tool's output, and the CLI materializes a profile as
provider + model + mode + thinking + feature values, never as a prompt. A
profile carries no system prompt by design: `AgentSessionConfig.systemPrompt` is
creation-only, so a profile holding one would apply when starting a new agent and
silently do nothing when applied to a running one. A provider override has no
prompt field either — its schema is `extends`, `label`, `description`, `command`,
`env`, `options`, `params`, `models`, `additionalModels`, `disallowedTools`,
`paseoTools`, `enabled`, `order`.

The per-seat channel Paseo leaves open is the seat's own process environment:
it merges a provider entry's `env` into the OpenCode server it launches for that
provider. The room uses `OPENCODE_CONFIG_DIR` for the role contract, because that
directory is where OpenCode discovers agent definitions, and a discovered
`agents/build.md` *is* the prompt of the agent the seat's `modeId` selects:

- sync renders the seat's role prompt (`roles/<role>.md`) and the shared protocol
  into `~/.config/opencode-room/seats/<provider>/agents/build.md`, in that order,
  under a two-line note that the prompt is the seat's contract;
- the derived provider's overlay points `OPENCODE_CONFIG_DIR` at that directory,
  so the seat's server loads it when the agent starts.

Two neighbouring ideas do not work on OpenCode 2.0.29 and were not used: an
`instructions` list in `OPENCODE_CONFIG_CONTENT` (or in a file-based
`OPENCODE_CONFIG` document) is accepted at the config layer and never reaches the
model, and an `agents.build.prompt` override inside a config document is ignored —
only the agent definition discovered from the config directory takes effect.

Because a seat's prompt replaces OpenCode's built-in agent prompt, it carries its
own short working note before the room's contract. The seat's `build` mode
description in Paseo also changes to the seat's name, since Paseo reads the mode's
description from the same definition.

A seat whose overlay is missing has no role contract at all: it starts as a plain
OpenCode `build` agent, does not know whether it is the Supervisor, the Lead, or a
Peer, and will happily do a dispatched task itself. `verify` reports that drift on
`env` and on the installed definition; `sync` restores both, and the seat must be
created again, because the overlay is process environment for the OpenCode server,
not session state.

## No native child agents in a seat

Paseo owns the room topology — Supervisor, Lead, and Peer are the only agents,
and each dispatch names its owner and return channel. An OpenCode child agent
launched inside a seat would sit outside that contract: nobody assigned it,
nothing reports it, and no one owns its writes. The three derived role providers
therefore carry an `env` overlay that Paseo merges into that seat's OpenCode
server (the same overlay that names the directory holding the seat's prompt):

```jsonc
{
  "OPENCODE_CONFIG_CONTENT": {
    "permissions": [{ "action": "subagent", "resource": "*", "effect": "deny" }],
    "agents": { "general": { "disabled": true }, "explore": { "disabled": true } }
  }
}
```

OpenCode layers `OPENCODE_CONFIG_CONTENT` over the config documents it discovers,
so the seat's permissions gain a deny that no approval can override, and the
built-in child agents leave the seat's catalog. With no launchable child agent,
the seat has no OpenCode-native child-agent tool.

Paseo's own bridge is a second surface: every seat still receives
`create_agent`, `send_agent_prompt`, `list_agents`, and the rest of Paseo's MCP
catalog, because the Lead must dispatch Peers through it. Each derived provider
may therefore carry a `paseoTools` policy. The Peer uses
`disabledTools` to remove agent creation and lifecycle control
(`create_agent`, `kill_agent`, `create_workspace`, schedule creation, permission
approval), leaving read-only inspection plus `send_agent_prompt` for its report
to Lead. Paseo applies the policy per provider ID and a running session keeps
the catalog it launched with, so a policy change needs a new agent. The base
`opencode` provider entry carries no overlay and no policy — native subagents and
the full Paseo catalog stay available everywhere except in the seats.

`config/room.json`'s `nativeAgents` flag is the switch for that half: `false`
(the shipped value) renders the policy into every derived provider, `true`
renders it nowhere and sync drops it from the installed entries. The seat's role
delivery is not optional — `OPENCODE_CONFIG_DIR` stays in the overlay either way.
`verify` compares the whole overlay as a managed key, so a hand-edited or reset
derived provider is reported as drift and restored by the next `sync`.

## Ownership

| Layer | Owner | Mutable state |
| --- | --- | --- |
| `~/.paseo` | Paseo (operator-installed) | Daemon, sessions, agents, projects, worktrees, identity |
| `~/.paseo/config.json` room entries | `scripts/room.py sync` | Provider entry `opencode`, the three derived role providers, and the three `daemon.agentProfiles` |
| Rest of `~/.paseo/config.json` | Operator / Paseo Desktop | Never rewritten by this repository |
| `~/.config/opencode-room/workflow/` | This repository | The shared `WORKSPACE_PROTOCOL.md` |
| `~/.config/opencode-room/seats/` | This repository | One installed seat prompt per role provider, named by that seat's overlay |
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
- The `opencode` provider is built into Paseo; this room manages its launch:
  a `command` argv array, `["<real opencode.exe>"]`, and repair of a stale
  `enabled: false` (true is Paseo's default, so sync does not write it). The exe
  path is
  resolved at sync time by parsing the npm shim (`shutil.which` finds
  `opencode.CMD`, which the daemon's Node cannot spawn without a shell;
  without the override Paseo falls back to its legacy v1 integration and
  every request returns the web UI's HTML page). Paseo still accepts the older
  `{"mode": "replace", "argv": [...]}` object this repository used to write, and
  `verify` treats either shape as the same launch. Other keys in the entry are
  preserved.
- The derived role providers are upserted by id the same way. Every key this
  repository renders (`extends`, `label`, `description`, `models`, `env`,
  `paseoTools`) is room-owned, so a key the spec no longer carries is removed —
  for example the native-agent policy when `nativeAgents` is `true`, or the
  Peer's `paseoTools` policy when the spec drops it; unrelated keys an operator
  added by hand (`enabled`, `order`) survive. A derived provider id
  must match Paseo's `^[a-z][a-z0-9-]*$` and must not be one of Paseo's built-in
  ids — `verify --source` and `sync` both refuse a spec that breaks either rule,
  that binds a profile to a provider the spec never declares, that binds one seat
  to two profiles, or that leaves a declared seat bound to no profile at all: a
  seat's profile is what pairs it with the role prompt it receives.
- The previous config is copied to `~/.opencode-room-backups/` before each
  write, and the write itself is atomic (temp file + replace).
- The installed files (`workflow/WORKSPACE_PROTOCOL.md` and one
  `seats/<provider>/agents/build.md` per seat) are refreshed from this repository
  on every sync; `verify` reports a missing or hand-edited copy, and `uninstall`
  removes exactly the files the spec declares.
- After writing, sync asks a running daemon to `reload`; it never restarts the
  daemon or interrupts running agents.

`verify` compares the installed state (config entries, installed protocol and seat
prompt files, `opencode` on PATH) against the rendered desired state and reports
drift. `uninstall` removes exactly the three profiles by name, the three derived
role providers, the installed protocol and seat prompt files, and (with
`--purge-provider`) the base provider entry — nothing else.

## Failure modes

- The Paseo Desktop UI can edit or delete agent profiles at any time. This is
  expected operator state, not corruption: re-run `sync` to restore the room.
- The same applies to the derived role providers. Deleting one removes that
  seat from Paseo's provider list (agents created from it keep running until
  restarted); `verify` names the missing entry and `sync` restores it.
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
- A seat's role contract arrives through its derived provider's `env` overlay
  (which directory holds its prompt) and the installed
  `seats/<provider>/agents/build.md`. If either is lost — a hand edit, a Paseo
  reset, or a config restored from an older backup — the seat starts as a plain
  OpenCode agent with no role, and if the native-agent half of the overlay went with
  it, with OpenCode's child agents back too. `verify` names the entry, the `env` key,
  and the missing or hand-edited definition; `sync` restores all three. The overlay is
  process environment, so it reaches the seat when Paseo launches that provider's
  OpenCode server: a session already running keeps the prompt it started with, and a
  session that never had one cannot acquire it retroactively — give that session its
  role in a message or start a new agent.
- A seat created from the bare provider entry instead of the profile, or before the
  overlay existed, has no role prompt at all: Paseo never delivers a profile's `notes`
  into an agent's context. `python scripts/room.py verify` cannot see a *running*
  session's gap (the profile and the installed files are correct); check the session
  itself — a Supervisor that does not know it is one will do the project work itself.
- Model and thinking ids can drift when the OpenCode/Ollama catalog changes.
  `paseo provider models opencode` lists what Paseo can currently see; update
  `config/room.json` to match. A derived role provider shows only the models and
  thinking options the spec declares for it, so its catalog must list that
  role's model explicitly (`paseo provider models opencode-supervisor`).

## Role boundaries

Role authority lives in `roles/*.md` and the shared coordination contract in
`workflow/WORKSPACE_PROTOCOL.md`. `sync` renders both into each seat's
`~/.config/opencode-room/seats/<provider>/agents/build.md`, which is the prompt that
seat's OpenCode server loads — the repository files are what those installed copies
are generated from, not what an agent reads directly. The protocol is also installed
at `~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md`, the path every role
prompt names, so a human or a seat can open the same text. Changing a role means
editing those files and re-running `sync`, then starting new sessions: existing
sessions keep the prompt they were created with, and the profiles' `notes` are
refreshed for operators who read them in Paseo.
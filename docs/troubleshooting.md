# Troubleshooting

## A room profile disappeared from Paseo

Cause: the Paseo Desktop UI (or archiving its last agent) edited or deleted
the agent profile. `sync` restores it:

```bash
python scripts/room.py verify   # lists which profile/provider field drifted
python scripts/room.py sync     # restores it, preserving profile ids
```

## A role is missing from Paseo's provider list

The three roles appear in the provider list as `OpenCode - Supervisor`,
`OpenCode - Lead`, and `OpenCode - Peer`, because each is a derived entry in
`agents.providers` (`"extends": "opencode"`). If one is gone or renamed:

```bash
paseo provider ls                       # expect the three role providers
python scripts/room.py verify           # names the missing or drifted entry
python scripts/room.py sync             # recreates it and reloads the daemon
paseo provider diagnostic opencode-lead # Command source: override, Status: Ready
```

Deleting a derived provider does not stop agents already running on it; it only
removes the seat from the list for new agents.

## The daemon does not show the updated profiles or providers

`sync` asks a running daemon to reload; when the daemon is stopped the config
still takes effect at the next start. Check state without changing anything:

```bash
paseo daemon status
paseo daemon config get daemon.agentProfiles
paseo provider ls
```

## `error: Paseo config not found`

Paseo is not installed or not onboarded for this user. This repository never
installs Paseo:

```bash
paseo onboard
```

## Agents fail with "Request is not supported by this version of OpenCode Server"

Cause: Paseo resolved `opencode` on PATH to the npm `opencode.CMD` shim. The
daemon's Node cannot spawn `.cmd` shims without a shell (spawn EINVAL), so
Paseo's version probe fails and it silently falls back to the legacy OpenCode
v1 integration, which requests root-path API endpoints that OpenCode v2
servers answer with the web UI's HTML page.

`sync` prevents this by pinning a `command` override
(`{"mode": "replace", "argv": [<real opencode.exe>]}`) in the provider entry,
resolved from the shim at sync time. If the error still appears:

```bash
python scripts/room.py verify          # provider 'opencode' differs on 'command'?
python scripts/room.py sync            # repairs the override, reloads the daemon
paseo provider diagnostic opencode     # expect: Command source: override, Status: Ready
```

## The OpenCode CLI is missing or logged out of Ollama Cloud

```bash
opencode --version                     # v2.0.10 minimum; v2.0.29 was verified
opencode auth login                    # Ollama Cloud credentials live inside OpenCode
paseo provider diagnostic opencode     # installation, auth, availability
paseo provider models opencode         # models Paseo can currently see
```

Credentials stay inside OpenCode; this repository never stores them.

## A model or thinking option is rejected

Model and thinking ids drift with the OpenCode/Ollama catalog. List what the
providers currently accept, then align `config/room.json`:

```bash
paseo provider models opencode            # the base provider's full catalog
paseo provider models opencode-supervisor # a role provider: only its own models
```

Thinking options are per-model (`deepseek-v4.1-flash` offers `low`, `high`, and
`max`; `deepseek-v4-pro` offers only `high` and `max`). A profile may also omit
`thinkingOptionId` entirely for a model without thinking options. A role
provider's catalog is
exactly what `config/room.json` declares for it, so a model that exists on
`opencode` is still unavailable on that seat until the spec lists it.

## Creating an agent from inside a room agent fails with HTTP 500

Symptom: a Lead (or a Supervisor) calls the Paseo `create_agent` tool and gets
`Paseo tool bridge returned HTTP 500` back, with no other explanation. The
bridge validates the tool call itself, so the real cause is in the daemon log:

```bash
tail -n 200 ~/.paseo/daemon.log | grep "OpenCode bridge request failed"
```

Two causes were seen on Paseo 0.11.2:

- `provider must be provider/model, for example codex/gpt-5.4` — the call
  passed a bare provider id. A room seat is a derived provider, so the id has
  to carry its model explicitly: `opencode-peer/ollama-cloud/deepseek-v4.1-flash`,
  `opencode-supervisor/ollama-cloud/deepseek-v4.1-flash`,
  `opencode-lead/ollama-cloud/deepseek-v4-pro`.
- `Unrecognized key: "background"` — `create_agent`'s bridge schema has no
  `background` field even though the tool description mentions one. Create the
  session with a one-line `initialPrompt`, then send the real brief through
  `send_agent_prompt` with `background: true` and `notifyOnFinish: true`; that
  is also the call whose notification reports the Peer's finish, error, or
  permission request.

A top-level create without `workspaceId` also opens a new workspace rather than
adopting the project's checkout, so pass the project's existing workspace id.
The mechanics are in [operations](operations.md#dispatch-work-to-a-peer).

## A finished assignment leaves the Supervisor with no event

Symptom: the Supervisor dispatches work to a Lead, the Lead (and its Peer)
finishes, and the Supervisor never learns the result — it goes idle, or wakes
once, sees nothing actionable, and stops watching.

Cause: Paseo arms a finish notification per `send_agent_prompt` call, not per
session. The Lead's closing turn is resumed by its Peer's notification rather
than by a Supervisor message, so no notification is armed towards the
Supervisor and no finish event is raised.

Fix, both halves described in
[operations](operations.md#close-the-loop-upward):

- The dispatch envelope names the assigning session's own agent id (read from
  `PASEO_AGENT_ID`, which Paseo injects into every agent session, alongside
  `PASEO_AGENT_CWD`) as the address the result goes back to. Lead sends its
  completion report as a background message with `notifyOnFinish=true`, which
  wakes the Supervisor; with no address known the report goes to the project's
  status surface instead.
- The Supervisor reads the Lead's lifecycle state, recent activity
  (`list_agents`, `get_agent_status`, `get_agent_activity`), and that status
  surface on every wake — event or heartbeat — before concluding that nothing
  happened. An idle Lead with an assignment still open gets one concise question
  for the result or the blocker.

Lead going idle is not evidence that nothing happened, and neither is a quiet
workspace: a closed assignment nobody relayed to Human is a supervision gap.
The same section of the protocol is the recovery path for a Lead that stalls
because it is confused: it asks the Supervisor one bounded question about scope,
priority, authority, or intent and keeps unrelated ready work moving.

## A room seat has a child-agent tool again

Symptom: an agent created from `opencode-supervisor`, `opencode-lead`, or
`opencode-peer` can launch OpenCode subagents (`general`, `explore`), which the
room does not own and nothing reports.

Cause: the seat's derived provider entry lost its `env` overlay — a hand edit, a
Paseo reset, or a config restored from an older backup. The room takes OpenCode's
native child agents away through `env.OPENCODE_CONFIG_CONTENT` on the derived
providers only; the base `opencode` provider intentionally keeps them.

```bash
python scripts/room.py verify          # names the derived entry that differs on 'env'
python scripts/room.py sync            # re-renders the overlay, reloads the daemon
paseo daemon config get agents.providers --json   # each derived entry carries the overlay
```

Paseo's config-path reader does not resolve dynamic keys, so read the whole
`agents.providers` object instead of one provider's `env`.

The overlay is process environment: it reaches a seat when Paseo launches that
provider's OpenCode server, so create a new agent from the profile after the
repair. To keep native agents in the seats on purpose, set `"nativeAgents": true`
in `config/room.json` and run `sync` — it removes the overlay from all three
derived entries.

## Roll back a bad sync

Every sync copies the previous config to `~/.opencode-room-backups/`. To
restore:

```bash
cp ~/.opencode-room-backups/<stamp>.json ~/.paseo/config.json
paseo daemon reload
```

or remove everything the room manages with
`python scripts/room.py uninstall`.
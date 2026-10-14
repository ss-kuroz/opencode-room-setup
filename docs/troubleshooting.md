# Troubleshooting

## A room profile disappeared from Paseo

Cause: the Paseo Desktop UI (or archiving its last agent) edited or deleted
the agent profile. `sync` restores it:

```bash
python scripts/room.py verify   # lists which profile/field drifted
python scripts/room.py sync     # restores it, preserving profile ids
```

## The daemon does not show the updated profiles

`sync` asks a running daemon to reload; when the daemon is stopped the config
still takes effect at the next start. Check state without changing anything:

```bash
paseo daemon status
paseo daemon config get daemon.agentProfiles
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
provider currently accepts, then align `config/room.json`:

```bash
paseo provider models opencode
```

Thinking options are per-model (`minimax-m3` has `medium`; `glm-5.3` does
not). A profile may also omit `thinkingOptionId` entirely for a model without
thinking options.

## Roll back a bad sync

Every sync copies the previous config to `~/.opencode-room-backups/`. To
restore:

```bash
cp ~/.opencode-room-backups/<stamp>.json ~/.paseo/config.json
paseo daemon reload
```

or remove everything the room manages with
`python scripts/room.py uninstall`.
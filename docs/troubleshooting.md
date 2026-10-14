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

## Agents fail with a provider error for `amp-acp`

The ACP adapter or the Amp CLI is missing or logged out:

```bash
amp --version            # Amp CLI installed and authenticated
amp-acp --version        # adapter on PATH (npm install -g amp-acp)
```

If `amp` is not on the daemon's PATH, set `AMP_CLI_PATH` in the provider's
`env` in `~/.paseo/config.json`; an existing provider entry is never modified
by `sync`, so this stays operator-owned.

## Roll back a bad sync

Every sync copies the previous config to `~/.amp-room-backups/`. To restore:

```bash
cp ~/.amp-room-backups/<stamp>.json ~/.paseo/config.json
paseo daemon reload
```

or remove everything the room manages with
`python scripts/room.py uninstall`.
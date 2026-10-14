# Operations

## Change a role

1. Edit `roles/<role>.md` (prompt/authority) or `config/room.json` (model,
   thinking effort, mode, auto-accept, profile names, and the role's derived
   provider: id, label, model catalog).
2. Run `make test` and `python scripts/room.py verify --source`.
3. Run `python scripts/room.py sync` and check the post-sync verification.
4. Existing sessions keep their original instructions; create a new session
   with the profile to exercise the change.

A role is two entries in `~/.paseo/config.json`: a derived provider
(`extends: opencode`) that makes the seat visible in Paseo's provider list with
its model and thinking effort as the default, and an agent profile that carries
the role prompt, `build` mode, and auto-accept. Edit the profile's `providerId`
and the provider's `models` array together when you change a role's model; a
derived provider's `models` array replaces the catalog Paseo discovered from
OpenCode, so it must list every model and thinking option that seat should
offer.

The three roles have distinct authority. Human keeps product, cost, external
effect, and irreversible-risk decisions. Supervisor observes and routes Human
intent. Lead owns the project's technical decision and acceptance. Lead may
run writable Peers in parallel only with verified, accepted inputs and
separate write scopes. Each moving scope has one owner; shared file or
interface changes are sequenced against agreed contracts. A Peer owns one
bounded outcome and returns an immutable candidate or a concrete premise,
dependency, or block signal.

## Dispatch work to a Peer

An authorized task is not Lead's own workload. Framing, the shared contract
between the parts, integration, verification, and explicit acceptance stay with
Lead; the hands-on legwork — code, probes, captures, file edits — goes to a
Peer through the `opencode-peer` profile. Give each moving write scope one
owner and stay out of that scope while its Peer owns it.

Paseo's tool bridge constrains how that session gets created:

```text
create_agent(provider="opencode-peer/ollama-cloud/deepseek-v4.1-flash",
             workspaceId=<the project's existing workspace>,
             settings={mode: build, thinking: low},
             initialPrompt=<one short line>)
send_agent_prompt(agentId=<returned id>, background=true,
                  notifyOnFinish=true, prompt=<the full brief>)
```

- `provider` must be the `provider/model` form. A bare provider id
  (`opencode-peer`) fails the daemon's validation, and the failure reaches the
  caller only as `Paseo tool bridge returned HTTP 500` — see
  [troubleshooting](troubleshooting.md#creating-an-agent-from-inside-a-room-agent-fails-with-http-500).
- `create_agent` does not accept a `background` key, so the create call carries
  a one-line prompt and the real brief follows as a background message. That
  message's `notifyOnFinish` is what wakes the sender when the Peer finishes,
  errors, or asks for permission.
- Create inside the project's existing workspace. A top-level create with no
  `workspaceId` opens a *new* workspace instead of adopting the project's
  checkout.

The brief stays self-contained (observable outcome, inputs and dependencies,
write scope, invariants, acceptance evidence, reopen condition), and every
actionable response gets closed with an answer, a resolved dependency or
ownership question, a request for the specific missing evidence, or an explicit
ACCEPT/REJECT with a reason. Silence, DONE, and passing tests are not a
disposition.

## Supervision and attention

Assign a new Supervisor a named project to begin monitoring. It first reads the
current Lead, decisions, and local contract without sending an onboarding
message to Lead. Private conversations remain private; Lead receives only a
needed project decision or an evidence-based open question about actual drift.
Healthy work does not require periodic Lead reports.

The Supervisor uses events and one self-targeted Paseo heartbeat every two
minutes where event coverage is incomplete. It checks existing schedules to
avoid duplicates and deletes its heartbeat when supervision ends. A necessary
message uses `background=true` with `notifyOnFinish=true`. No heartbeat is
created by `sync`; the Supervisor establishes it when assigned supervision.

After changing a role prompt, create a new Supervisor session to test it.
Check that assignment creates a self-targeted heartbeat without messaging a
healthy Lead, that a real ownership/dependency/acceptance deviation elicits one
concise open question without private attribution, and that unchanged state
produces no repeat. Confirm the heartbeat is removed when supervision stops.
`verify` and unit tests do not establish this behavioral acceptance.

## Project handoff

Lead first records the observable outcome, dependencies, write scope, relevant
invariants, acceptance evidence, and the condition that would reopen the
decision. The writer then reports the exact candidate, original base, changed
paths, commands run, and residual risk. Lead inspects that candidate and
explicitly accepts or rejects it. Tests and lifecycle state support the
decision but do not replace it.

When independent architecture or candidate judgment can change the decision,
Lead requests a fresh read-only Peer against an exact candidate or
deterministic snapshot. The reviewer returns only evidence relevant to the
bounded question; there is no extra standing role.

After dispatch, wait for finish, error, attention, or decision events. Do not
repeatedly query a seat while its state is unchanged.

## Restore drift

The Paseo Desktop UI can edit or delete room profiles or derived role providers.
`python scripts/room.py verify` reports exactly which field of which profile or
provider drifted; `python scripts/room.py sync` restores it without disturbing
unrelated profiles or providers. Config backups from every sync live under
`~/.opencode-room-backups/`.
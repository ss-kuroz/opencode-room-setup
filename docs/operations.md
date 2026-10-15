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

Each derived provider also carries the native-agent overlay that takes OpenCode's
child agents away from the seat (`nativeAgents: false` in `config/room.json`).
It is a managed key like `models`, so sync re-renders it and `verify` reports a
seat that lost it; the base `opencode` provider keeps native subagents.

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

Each wake is a liveness check, not just an inbox check. Before concluding that
nothing happened, the Supervisor lists the agents in the monitored scope, reads
the Lead's lifecycle state and recent activity (`list_agents`,
`get_agent_status`, `get_agent_activity`), and reads the project's status
surface. An idle Lead with an assignment still open gets one concise question
for the result or the blocker; a closed assignment that was never relayed to
Human is a supervision gap. The question is not repeated while the state is
unchanged.

The Supervisor also answers Lead's bounded questions about scope, priority,
authority, or ambiguous intent: from current evidence, or by routing a Human
decision to Human, or by stating that no evidence supports an answer. Answering
never makes the Supervisor the project's technical Lead — it does not accept a
candidate or direct a Peer.

After changing a role prompt, create a new Supervisor session to test it.
Check that assignment creates a self-targeted heartbeat without messaging a
healthy Lead, that a real ownership/dependency/acceptance deviation elicits one
concise open question without private attribution, and that unchanged state
produces no repeat. Check the loop in both directions: an idle Lead with an open
assignment gets one request for the result or blocker, a finished assignment is
relayed to Human, and a bounded Lead question about scope or intent is answered
from evidence or routed to Human. Confirm the heartbeat is removed when
supervision stops. `verify` and unit tests do not establish this behavioral
acceptance.

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

## Close the loop upward

A Peer's finish wakes its Lead, and the Lead then continues and closes the
assignment. That closing turn is not started by a message from the Supervisor,
so it does not always raise a finish event to the Supervisor, and the Supervisor
can be left unaware while a result sits finished. Two explicit mechanisms keep
Human informed, and both belong in every dispatch:

- **A return channel in the envelope.** The assigning session reads its own
  agent id from the environment (`PASEO_AGENT_ID`, injected per session
  alongside `PASEO_AGENT_CWD`) and states it once as the address the result goes
  back to. Lead then sends a concise completion report — outcome, candidate and
  base, evidence, residual limits, the decision Human must make — as a
  background message with `notifyOnFinish`, which wakes the Supervisor directly
  (`roles/lead.md`). The address is operational metadata, not attribution: it
  stays out of Peer briefs and project artifacts. With no address known, the
  report goes to the status surface and says the direct channel is unknown.
- **A status surface plus a wake-up.** Lead keeps the project's existing
  work-status source current while work is moving (assignment and owner, state,
  next checkpoint, open decisions with owners), and the Supervisor establishes a
  wake-up for the monitored scope before claiming it is monitored, so a missing
  event is caught on the next check (`roles/supervisor.md`).

The Supervisor relays the outcome and any Human decision to Human; a closed
assignment that no one mentions is a supervision gap, not a quiet success.

Lead's questions close the same way: when scope, priority, authority, or intent
cannot be settled from the instructions and current evidence, Lead sends the
Supervisor one bounded question (ambiguity, evidence, decision needed, options,
what it continues meanwhile) instead of stalling or inventing scope. The
Supervisor answers from evidence, routes a Human decision to Human, or says no
evidence supports an answer — without becoming the project's technical Lead.
This is the recovery path for a Lead that is confused rather than blocked on a
Peer.

## Restore drift

The Paseo Desktop UI can edit or delete room profiles or derived role providers.
`python scripts/room.py verify` reports exactly which field of which profile or
provider drifted — including a derived provider that lost its `env` overlay and
so regained OpenCode's native child agents — `python scripts/room.py sync`
restores it without disturbing unrelated profiles or providers. Config backups
from every sync live under `~/.opencode-room-backups/`.

The overlay is process environment, not session state: it reaches a seat when
Paseo launches that provider's OpenCode server, so after a repair create a new
agent from the profile instead of expecting a running one to change.

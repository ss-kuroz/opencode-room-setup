# Operations

## Change a role

1. Edit `roles/<role>.md` (prompt/authority) or `config/room.json`
   (model, mode, auto-accept, profile names).
2. Run `make test` and `python scripts/room.py verify --source`.
3. Run `python scripts/room.py sync` and check the post-sync verification.
4. Existing sessions keep their original instructions; create a new session
   with the profile to exercise the change.

The three roles have distinct authority. Human keeps product, cost, external
effect, and irreversible-risk decisions. Supervisor observes and routes Human
intent. Lead owns the project's technical decision and acceptance. Lead may
run writable Peers in parallel only with verified, accepted inputs and
separate write scopes. Each moving scope has one owner; shared file or
interface changes are sequenced against agreed contracts. A Peer owns one
bounded outcome and returns an immutable candidate or a concrete premise,
dependency, or block signal.

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

The Paseo Desktop UI can edit or delete room profiles. `python scripts/room.py
verify` reports exactly which field of which profile drifted;
`python scripts/room.py sync` restores it without disturbing unrelated
profiles or providers. Config backups from every sync live under
`~/.amp-room-backups/`.
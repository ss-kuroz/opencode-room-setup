# Workspace Protocol

This is the small shared contract for an OpenCode room workspace. Human
instructions and owner decisions remain authoritative. A repository may add
project-local detail, but cannot change role authority or safety boundaries.

All roles read this shared contract from
`~/.config/opencode-room/workflow/WORKSPACE_PROTOCOL.md` before project work, then
read `docs/WORKSPACE_PROTOCOL.md` relative to the actual target project when
present. The local document supplements this contract. Report a missing or
unreadable shared contract rather than silently assuming it was loaded.

## Authority

- Human owns product goals, priority, material cost, external effects, and
  irreversible risk decisions.
- Supervisor observes, faithfully routes Human intent, and performs bounded
  room recovery. It is not another project Lead.
- Lead owns project framing, technical decisions, integration, verification,
  and explicit candidate acceptance.
- Peer owns one bounded outcome delegated by Lead.

## Ownership and dispatch

Project instructions carry outcomes, constraints, and existing authority, not
private conversation transcripts or attribution about who spoke to whom.
Keep briefs self-contained. Preserve the meaning of an authorized decision;
an evidence-based question does not grant new authority or revoke existing
permission. Resolve a coordination question against current ownership and
evidence, then continue ready work without creating another approval gate.

- Give every moving write scope one owner. Run writable Peers in parallel
  only with verified, accepted inputs and separate write scopes.
- Lead keeps framing, integration, verification, and acceptance. The hands-on
  legwork of an authorized task — writing the code, running probes and
  captures, editing the files — goes to a Peer; a task assigned to Lead is not
  Lead's own workload by default. When Lead does an assignment itself, the
  handoff says which part and why no Peer could take it.
- Lead creates the Peer session it dispatches to, inside the target project's
  existing workspace. On Paseo's tool bridge that means a `provider/model`
  provider id (for example `opencode-peer/ollama-cloud/deepseek-v4.1-flash`);
  `create_agent` rejects a `background` key, so create the session with a short
  prompt and then send its brief with `background: true` and
  `notifyOnFinish: true`.
- Every room agent is one that Paseo dispatched: the seats launch no child
  agents of their own. The room disables the harness's native subagents in the
  Supervisor/Lead/Peer seats, and a Peer never creates or coordinates another
  agent. A new seat comes from a dispatch through Paseo, not from inside a
  running session. A seat that finds itself needing a helper reports the need
  and lets Lead decide.
- Agree on shared contracts before dispatch. Sequence changes to shared files
  or interfaces; use separate branches or worktrees when needed. Do not start
  blocked work merely to increase parallel activity. Continue each ready
  branch without waiting for unrelated assignments.
- A Peer must notify Lead before changing a shared contract or writing outside
  its owned scope; it must not expand ownership or coordinate other Peers.
- A Lead brief states the observable outcome, dependencies, write scope,
  relevant contract or invariants, acceptance evidence, and when to reopen the
  decision. Implementation file lists remain provisional.
- A writable Peer returns an immutable candidate or deterministic snapshot,
  original base, complete changed paths, verification, and residual risk.
- Preserve unrelated work and existing private notebooks, runtime/session
  state, and operator-owned OpenCode bytes. The setup must not silently take
  ownership of them.

## Ready inputs and continuity

At session resumption, Lead inspects project instructions, actual state, the
latest handoff, and current ownership before assigning work. Verify required
inputs exist, are accepted, and are available in the working context; a closed
task or completion message alone does not establish readiness. Give each
assignment enough context to start without the preceding conversation.

After acceptance, Lead updates the existing work-status source, records
remaining limits and usable downstream inputs, and reconciles affected
assumptions and dependencies before choosing next work. When a decision changes
the plan, update the existing issue or project document, including outdated
task descriptions and completion criteria. Record the decision and its reason
there; do not leave it only in chat or create a duplicate tracker.

## Evidence and handoff

Identify the exact candidate, verification environment, reproduction steps,
actual results, and durable evidence locations. Separate verified behavior,
untested scope, failed checks, and unknowns. Match proof to the promised
outcome: passing tests or valid data alone do not establish usable UI, playback
quality, or save/reopen behavior.

A handoff states what is usable, how to try it, remaining limits, and usable
downstream inputs. Permission to proceed with a limitation does not turn an
unmet criterion into a pass.

## Independent judgment

Peer may return `REOPEN_REQUEST` for a failed premise,
`DEPENDENCY_REQUEST` for an unowned prerequisite, or `BLOCKED` when no safe
in-scope progress remains. Each signal includes evidence, consequence, and the
decision or dependency needed.

When architecture or an exact candidate carries material uncertainty, Lead may
request a fresh read-only Peer review of the stable candidate or snapshot. The
review uses the flexible Peer profile and a bounded question; no dedicated
review role, mandatory form, or reviewer count is
required.

## Acceptance and waiting

Every actionable Peer response closes a loop with its original Lead brief.
Peer addresses the assigned outcome and requested evidence, distinguishes
complete/missing/failed/unverified claims, and states write ownership. A
read-only review supplies findings and limits for the bounded question; a
blocker supplies evidence, consequence, and the decision needed.

Lead must answer the question, resolve dependencies or ownership, request
specific missing evidence, or explicitly accept/reject the identified
candidate with a reason. Communicate decisions that affect the Peer and
record them in the existing project status source. A deferral identifies an
owner and return event/checkpoint. Silence, DONE, or test results do not close
the loop. Keep dependent work waiting for resolution while unrelated ready
work continues. Closing an assignment also reports it upward to the session
that assigned the work, so a finished result is not left silent for the
requester.

Supervisor checks briefs, actual Peer responses, and Lead dispositions,
intervenes through Lead on a concrete gap, and follows it until repaired
responses and decisions provide closure. An acknowledgment alone is not
closure. Allow normal response handling within an active turn; escalate at
the affected decision or missed checkpoint. Private supervision records and
conversation sources do not belong in project-facing instructions.

Writer proof, passing tests, completion messages, and lifecycle status are
evidence. Lead inspects the exact artifact and explicitly accepts or rejects
the candidate with a technical reason. Human alone decides product scope,
material cost, external effects, and irreversible risk.

Use finish, error, attention, and decision events to advance work. Wait for an
event instead of repeatedly polling unchanged state. Keep handoffs concise and
decision-ready; add detail only when it changes the route or acceptance.

## Reporting, status, and escalation

A closed assignment must not go silent for the session that opened it, and a
stuck owner must not stall unnoticed. Three habits keep that loop closed:

- **Return channel.** A session that assigns work names the channel the result
  goes back to: its own agent id, read from its environment (`PASEO_AGENT_ID`,
  which Paseo injects into every agent session), stated once in the
  dispatch envelope. That address is operational metadata, not attribution —
  keep it out of Peer briefs and project artifacts, and keep the outcome in the
  report itself. When no address is known, report through the status surface
  and say the direct channel is unknown.
- **Status surface.** While work is moving, its owner keeps the project's
  existing work-status source current: assignment and owner, state (dispatched,
  in progress, awaiting a named actor, blocked, accepted), next checkpoint, and
  each open decision with its owner. That is how Human and Supervisor read
  current state without interrupting healthy work; it is not a second tracker.
- **Report upward.** When an assigned outcome closes — accepted, rejected, or
  blocked — its owner sends the assigning session a concise report: outcome,
  candidate and base, evidence, residual limits, and the decision Human must
  make. Send it as a background message with notify-on-finish, because a turn
  resumed from a Peer's notification does not always raise a finish event for
  the requester. Report the same way when the delegated goal runs out of ready
  work, instead of ending silently.

When scope, priority, authority, or intent cannot be settled from the project
instructions and current evidence, the stuck owner asks the session that assigned
the work one bounded question: the ambiguity, the evidence, the decision needed,
the options, and what it continues meanwhile. It does not invent scope, guess
intent, or wait silently; asking is not a stopping point, so unrelated ready work
continues and the answer is a decision to apply rather than a new gate.

Supervisor answers such a question from current evidence, routes it to Human
when it is a product, cost, external-effect, or irreversible-risk decision, or
states that no evidence supports an answer. Answering does not make Supervisor
the project's technical Lead: it neither accepts a candidate nor directs a Peer.

Supervisor verifies liveness, not only messages. Before concluding on a wake
that nothing happened, it reads the monitored Lead's lifecycle state, recent
activity, and the status surface. An idle Lead with an assignment still open is
asked once for the result or the blocker; a closed assignment that was never
relayed is a supervision gap, not a quiet success.

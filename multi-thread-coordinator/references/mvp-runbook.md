# Basic Coordination MVP Runbook

Use this runbook to coordinate a complex TODO or high-level outcome through the host's native task and subagent surfaces. Resolve the current host's surfaces and return model from [hosts.md](hosts.md) before dispatch. It implements intake, decomposition, mode selection, worker-surface recommendation, bounded briefs, dispatch, evidence reconciliation, and current-status reporting.

Use [protocol.md](protocol.md) for detailed identities and gates, and [workspaces.md](workspaces.md) for project authority and persistence. This runbook does not create a broker, daemon, task board, or external permission.

## Contents

1. Supported MVP slice
2. Start a run
3. Build the compact run plan
4. Decide readiness and ownership
5. Build the worker brief
6. Dispatch and reconcile
7. Accept primary evidence
8. Recommend worker surfaces
9. Coordinate independent parallel cases
10. Report current status
11. Handle user questions and changes
12. MVP acceptance probes

## 1. Supported MVP Slice

Use this runbook now for:

- one or more delegated `staged` chains;
- multiple independent `parallel` modules with stable inputs and disjoint or isolated writes;
- mode identification for dependent or ambiguous work while holding its later work behind a declared gate;
- bounded native dispatch when a task or subagent surface is available and permitted;
- evidence-backed acceptance and concise current-status reporting.

Do not start a coordinator run for a simple action that one ordinary agent can complete and verify directly.

Do not use the basic slice to claim that later-stage capabilities have been exercised. Use [staged-execution.md](staged-execution.md) for progressive multi-stage rework and adaptive briefs, and [resilience.md](resilience.md) for fresh review, recovery, audited retry, supersession propagation, and active-write conflict handling.

When the request falls outside the basic slice, classify it accurately, keep unsafe work held, and use the applicable protocol rather than forcing it into `parallel`.

## 2. Start a Run

Perform these steps before dispatch:

1. Read the latest user request and separate effective TODO items from status questions or superseded instructions.
2. Establish or refresh the Workspace Binding when project artifacts are involved.
3. Identify each item's outcome, authority, deliverable, consumer, verification, dependencies, mutable writes, required capability, permission, and risk.
4. Choose `staged`, `parallel`, or mixed mode per work chain.
5. Build only the minimum run plan needed to identify ready work, held work, owners, write sets, and gates.
6. Recommend internal subagents or user-visible tasks for ready packages and obtain one consolidated user choice when material work lacks a current surface decision.
7. Preflight the selected surface before announcing dispatch.
8. Give the user one compact kickoff update.

Do not ask the user to approve the plan merely because a plan exists. Ask only for a decision or authority that changes what may safely run.

Use this kickoff shape:

```text
Outcome: <interpreted current result>
Mode: <mode per chain and one-sentence reason>
Boundaries: <important read, write, forbidden, data, and external-action limits>
Ready now: <tasks that may start>
Held: <tasks and the gate keeping them held>
Acceptance: <primary evidence that will prove the result>
Worker surfaces: <recommended or selected surface per ready package and why>
```

Omit empty lines and fields that add no decision value.

## 3. Build the Compact Run Plan

Keep this as a logical record in native task history unless persistence is required:

```yaml
batch_id: batch_NNNN
run_id: run_NNNN
binding_id: binding_vNNN | null
skill_commit_at_creation: <immutable installed Skill revision>
return_contract_version: automatic_v1 | task_event_v1 | notify_v1 | push_v1 | manual_v1
coordinator_id: <canonical native coordinator identity>
schema_provenance: <trusted-writer created_v2 or migrated_from_v1 structural attestation>
coordinator_return_target: {task_id: <task>, host_id: <host>} | null
outcome: <current user outcome>
mode: staged | parallel | mixed
chains:
  - chain_id: chain_<slug>
    mode: staged | parallel
    rationale: <one sentence>
tasks:
  - task_id: task_<slug>
    chain_id: chain_<slug>
    objective: <one testable outcome>
    owner_surface: internal_subagent | user_visible_task | worktree | pending_user_choice
    surface_rationale: <traceability, continuity, helper scope, isolation, or user choice>
    depends_on: []
    reads: []
    writes: []
    deliverables: []
    acceptance: []
    expected_return: automatic | task_event | notify | push | manual
    return_contract_version: automatic_v1 | task_event_v1 | notify_v1 | push_v1 | manual_v1
    worker_task_identity: <created worker identity, such as threadId/hostId or agent name/id, or null>
    return_target: <worker task for task_event, coordinator task for push, or null>
    status: pending | running | needs_input | blocked | succeeded | failed | superseded
ready_now: []
held: []
```

Also retain the current stage, next action, acceptance state, and user-delivery receipt in native history under [handoffs.md](handoffs.md); these are not extensions to the persisted v2 schema.

Keep reasoning outside the record except for one mode rationale and concrete hold reasons. Do not persist copied source content, credentials, internal chain-of-thought, or a full duplicate of native task history.

For parallel work, record enough task identity and writes to demonstrate independence. For a material staged chain, record the continuing worker surface selected for that chain.

## 4. Decide Readiness and Ownership

A task is ready only when:

- every `depends_on` source is current and `succeeded`, and its current coordinator acceptance will strictly precede each current or retry-ancestor delivery under the task's immutable declarations;
- its authoritative inputs are available and stable for the attempt;
- its write set has one owner and conflicts with no concurrently ready task;
- the selected owner has the required read, write, tool, return, and evidence capabilities;
- a user-visible task can use native task-event waiting, verified wake notifications, or a verified worker-push path with supported coordinator continuation, when autonomous continuation is expected;
- every required external or consequential action is already allowed;
- its acceptance can be observed from available primary evidence.

Keep a non-ready task in `held` with one concrete reason. Do not dispatch it with instructions to guess missing input or wait inside a worker.

Assign one accountable worker per task. The current task remains the coordinator and acceptance owner rather than the primary producer for material deliverables.

- Recommend an internal subagent for a short helper that returns immediately and needs no durable user continuation.
- Recommend a user-visible task for material, multi-stage, long-running, likely-to-be-reworked, or later-resumable work where durable traceability helps.
- Recommend an isolated worktree-backed task when concurrent mutable code changes require it and the user authorizes that environment.

If the current user request already selects the surfaces, use that selection. Otherwise ask one consolidated question covering the recommended mix before material dispatch. Simple helper work may use internal subagents without a pause. If the selected surface is unavailable, revise the recommendation, narrow the work, or provide a manual handoff; do not silently move material production into the coordinator.

## 5. Build the Worker Brief

Use the full brief contract in `protocol.md` when correlation or recovery matters. For the basic slice, include at least:

```text
Identity: <batch/run/task/attempt>
Objective: <one testable result>
Inputs: <authoritative pointers>
Allowed reads: <exact roots or artifacts>
Allowed writes: <exact outputs>
Allowed actions: <local, network, application, or external actions>
Prohibited: <paths, data movement, publication, destructive actions, or scope>
Deliverable: <location and concrete artifact>
Evidence required: <primary observations>
Acceptance: <observable pass conditions>
Coordinator: <actual native identity and routing target, or native parent>
Return: <verified native channel; follow handoffs.md on completion, failure, blockage, or required input>
Return report: <request/stage/attempt, disposition, paths and candidate identity, evidence, unresolved items, next action/owner>
Approval refusal: <return stated reason, held action/target/candidate, exact worker identity/title, observed user remedy; coordinator routes the user under handoffs.md>
Return mode: <automatic subagent return, task_event by worker task ID/host, notify by armed worker identity, verified push, or disclosed manual return>
Return events: <completed or needs_attention for task_event; result, needs_input, or blocked for push>
Stop when: <missing input, authority conflict, unsafe write, or other concrete condition>
```

Make the brief self-contained through pointers, not copied project context. Include only the current task. Keep later dependent instructions out of the brief.

## 6. Dispatch and Reconcile

Run this event-driven loop until no ready work remains:

1. Select the smallest useful set of ready, write-safe tasks.
2. Recheck owner capability and the still-applicable authorization immediately before dispatch. This is a coordinator check, not a request for the user to authorize the same action again.
3. Dispatch through the native surface. For a user-visible task, use the host's durable worker creation capability, such as `create_thread` on Codex or a background agent on Claude Code, and capture its ready worker identity. Where creation yields `threadId` and `hostId`, capture both; a `clientThreadId` means setup is still pending and is not a valid wait target. Preserve the receipt and follow [runtime-recovery.md](runtime-recovery.md) to resolve the exact task without creating a duplicate.
4. Record the dispatch Skill revision and return-contract version. For every delivered task-event, notify, push, or manual attempt, including preserved history, require the ready native worker identity; task-event additionally requires its first native wait, and notify additionally requires `return_armed_at`, the moment the host's notification path for that exact worker became live. These modes require a `user_visible_task` or `worktree` surface. If a coordinator return target is recorded, keep its exact native task/host pair distinct from every delivered task-event, notify, push, or manual producer in the run and every required reviewer. For push, bind that exact target plus verified native-send evidence before preflight; for manual, record disclosure and evidence before delivery; for automatic, require `internal_subagent` and bind the native parent/worker identities. Mark the identified attempt `running` only after its mode contract exists; treat tool delivery only as a transport observation.
5. Satisfy the host's return model. For `expected_return: task_event`, call the native event wait capability such as `wait_threads` for the exact worker identity before ending the coordinator turn, and wait on all eligible user-visible workers together when the surface supports it. For `expected_return: notify`, end the turn after arming and resume from the host's notification; polling in-turn returns no sooner. Never leave a delivered attempt with no live return path.
6. On a bounded task-event timeout, preserve the returned cursor and wait again without treating the task as failed or reading it repeatedly. A notify attempt has no cursor and needs no re-arming; an absent notification is not a failure. Under either contract, new user input may interrupt the return; retain the worker identity and resume, redirect, or supersede it according to that input.
7. On `completed` or `needs_attention`, associate the returned final text, candidate, evidence, question, or failure with its task attempt. Treat it as `returned`, not accepted. One native task-event response may atomically expose the event and payload, so their recorded timestamps may be equal; reversal fails. A notify event and its payload arrive together and carry the same allowance. For a preflighted `push` fallback, apply the same rule to the correlated worker message and keep event before association strict.
8. Before unrelated new material dispatch—including independent-review dispatch—reconcile every completion or attention event already returned to the coordinator. Reconciliation must be strictly earlier than the later dispatch; equal timestamps do not prove order. Inspect the real candidate and primary evidence. Use a bounded worker read, such as `read_thread`, only when returned detail is insufficient or recovery requires it, not as the ordinary completion detector; where the host's stored worker output is a full transcript rather than a result, use the returned result instead.
9. Mark `succeeded` only after task and candidate carry the same nonempty unique criterion set, exactly one passing current-authority/current-candidate evidence row covers each criterion, every effective review is clean, validly superseded, or—only when optional—exactly evidence-adjudicated by the coordinator, dependencies passed their acceptance-time gate, and the attempt records `accepted_by` as the canonical coordinator. Otherwise record the precise non-pass status.
10. Recompute ready and held work from current accepted candidates and authority.
11. Send a correlated next-stage or rework brief to the same worker when appropriate, then establish the host-appropriate return path for that attempt: a fresh task-event wait, notify arming, or verified push contract.
12. Apply [handoffs.md](handoffs.md) in this same active turn: pair receipt with actual review, rework, continuation, delivery, or a concrete hold. Before ending, process current returned-but-unprocessed and accepted-but-undelivered outcomes; record final user delivery separately from acceptance. Give the user a compact update when a material gate passes, a concrete issue arises, or the ready set changes materially.

Inspect native task state directly only for recovery: after an interruption, ambiguous return transport, a user status request, or an evidence gap in the returned event. This is reconciliation, not routine progress supervision. Do not report repeated unchanged state or turn worker availability into a reason to create unnecessary tasks.

If a legacy push attempt is still in flight when task-event waiting becomes available, preserve the push attempt and migrate once through a new correlated task-event transition with explicit version and reconciliation evidence. Validate every actual direct transition independently of current pointer or task status, reject more than one transition per task, and compare pushes unresolved at that transition's own delivery: it directly retries the latest such same-task push, its acyclic `retry_of` chain includes every earlier unresolved push, and `contract_migration` names the direct source. Any retry whose predecessor recorded uncertainty is delivered only after that predecessor's parsed reconciliation, with strict ordering across all statuses. Later ordinary task-event retries reuse the validated transition through ancestry and neither repeat migration nor directly retry the original push. Do not change the old attempt's return mode in place.

## 7. Accept Primary Evidence

Require evidence that directly supports the stated deliverable:

| Candidate | Primary evidence examples |
|---|---|
| Code or repository change | Exact commit or diff, relevant tests, inspected files, clean state |
| Document | Exact file digest or version, source checks, rendered inspection when layout matters |
| Dataset or workbook | Authority version, bounded table/sheet scope, calculations, formula/error checks |
| Research result | Source URLs or records, claim-to-source mapping, date and scope checks |
| Native message result | Exact task/attempt identity plus independently inspectable supporting evidence |

For persisted v2, use only the compact supported task fields and give each acceptance criterion a unique ID and exact requirement text on both task and candidate. Every candidate records a documented kind, nonempty location and scope, and timezone-aware observed timestamp. Record exactly one passing evidence row per criterion with that same ID/text, exact candidate identity, exact authority identities, method, raw-output pointer, timestamp, and an observer equal to the coordinator or an effective structurally qualifying reviewer bound to that candidate. Reject implicit waivers, local task/candidate supersession fields, and unsupported extensions. Distinguish:

- source fact: what an authority states;
- observation: what the coordinator inspected or measured;
- inference: the conclusion drawn from facts and observations.

For numerical re-performance, bind the check to the source precision, units, and governing rounding rule. Recompute from authoritative full-precision values with exact decimal or other suitable arithmetic; round only at the specified boundary. A mismatch produced by reusing rounded display values is not yet a candidate defect. If only displayed values exist, state the resulting verification limit and obtain the necessary source evidence rather than inventing precision or a tolerance. The check must still reject a real discrepancy beyond the source-supported rounding boundary.

Reject summaries that do not identify the actual candidate or let the coordinator inspect it. If the candidate changes, require new evidence for affected criteria.

## 8. Recommend Worker Surfaces

After decomposition, show the user only the decision-relevant packages and one recommended mix:

```text
Recommended worker surfaces:
- <material chain>: user-visible task — <traceability or continuation reason>
- <small helper>: internal subagent — <short bounded-return reason>
Question: Use this recommended mix, or change any named package to the other surface?
```

Use a still-applicable surface choice from the conversation without asking again. Ask once only for material packages that lack a choice, unless later requirements create a materially different work package. One user answer authorizes the named user-visible tasks for that run. Do not ask about every stage in a continuing chain; reuse its selected worker. Do not ask for small helpers when an internal subagent is plainly sufficient.

## 9. Coordinate Independent Parallel Cases

Parallelize only independent modules through acceptance.

Example request: prepare three unrelated synthetic guidance notes from three separate source packs.

Required plan properties:

- one task per genuinely independent note when concurrent execution is useful;
- each task names its own source pack, output path, and acceptance checklist;
- output paths are disjoint and source packs are stable read-only inputs;
- no task consumes an unresolved sibling output;
- each note can be accepted or rejected independently from source-bound evidence;
- one failed note does not invalidate succeeded siblings;
- the final user report reconciles all three current statuses without pretending that task return equals acceptance.

Do not add a combined-summary join unless the user requested one. If a combined result is requested, represent it as held dependent work until all required upstream candidates pass.

## 10. Report Current Status

Use this compact shape for kickoff updates, gate changes, and closure:

```text
Succeeded: <verified tasks and exact candidates>
Running: <identified active attempts>
Needs input: <one concrete decision or missing authority>
Blocked: <external blocker after safe alternatives are exhausted>
Failed: <attempt and unmet criterion>
Superseded: <stale work and replacing authority or candidate>
Held/next: <not-yet-ready work and its gate>
Evidence: <primary checks completed or still required>
```

Omit empty categories. Use `pending` internally for known later work and present it as `Held/next` with the reason that matters to the user.

At closure, map every effective TODO item to a status, identify usable outputs, reconcile every delivered noncurrent attempt through causal retry ancestry or valid same-task run-level supersession, hold on any unresolved delivered-without-return work, and never treat `status: superseded` alone as reconciliation. State remaining risk and exclusions, complete the active-work audit, and do not say the broader project is final or approved.

## 11. Handle User Questions and Changes

Respond to new user input before resuming a wait. Treat a status question as a request for the current compact report; do not start a new batch. Keep unaffected tasks running and preserve their identities and cursors. A task that has not returned does not block authorized independent work. For an already received event, first perform bounded reconciliation under the protocol; full acceptance can remain held while independent work proceeds.

Preserve explicit pause and cancellation instructions in native task history or the recovery capsule, alongside the observed execution state. Do not automatically resume such work when handling a new request. A requested stop is not proof that a running operation stopped: use the available native control within authorization and verify its result, or retain the uncertainty. These observations do not add `paused` or `cancelled` to the persisted protocol status enum, and do not manufacture `succeeded` or `superseded` merely to close a run. After verifying a requested cancellation and its remaining side effects, report the work as intentionally not done and stop pursuing that cancelled objective. The current strict schema has no standalone cancellation terminal state: retain its historical records without claiming `--closure` for the original outcome. This audit limitation must not keep a cancelled worker alive, create a replacement task, or block a user answer or independent authorized work.

Treat an additive requirement as new work in the current batch only when it does not change authoritative input or the intended result of existing work. Recompute dependencies and writes before dispatch.

Treat replacement input or a changed intended result as a new batch. Keep affected active work from becoming current, preserve unaffected accepted work, and route the earliest affected stage through the supersession procedure in `protocol.md`.

Answer concrete user objections with the actual plan, candidate, and evidence. Do not restart accepted independent work merely because another item changed.

## 12. MVP Acceptance Probes

Before treating the basic coordination MVP as usable, verify both probes against the current Skill:

### Worker-surface probe

- Material work is not silently assigned to the coordinator or defaulted to internal subagents.
- The recommendation distinguishes durable traceable work from short helper work.
- One consolidated question covers all material packages lacking a user choice.
- A selected continuing worker is reused across a dependent staged chain.
- A user-visible task defaults to the host's event contract—`task_event` where the coordinator waits in-turn, `notify` where the host wakes it—records the created worker identity such as `threadId` and `hostId`, and is returned through that contract rather than by polling.
- A task-event attempt is not `running` before its ready worker identity and first wait contract exist, and a notify attempt is not `running` before its ready worker identity and `return_armed_at` exist.
- A returned completion or attention event is reconciled before unrelated new material dispatch.
- Independent-review delivery is material dispatch and cannot cross an earlier unreconciled return.
- Causal lifecycle boundaries use strict order. The only equality allowance is atomic native observation: task-event event/payload, notify event/payload, and review completion/event/payload, may share a timestamp; delivery/wait, delivery/arming, push event/association, return/reconciliation, reconciliation/resolution, resolution/acceptance, and later dispatch remain strict.
- A bounded event-wait timeout preserves the worker identity and cursor and does not become failure, completion, or a blind retry.
- After rework or a next-stage follow-up, the coordinator establishes a fresh return wait for the same worker.
- A user-visible task without task-event return uses push only after its exact coordinator task/host target and native-send evidence are verified, with that native pair distinct from every delivered visible producer across modes and every required reviewer; manual records prior disclosure evidence; automatic identifies an internal subagent worker distinct from its coordinator parent and cannot contradict a user-visible surface.
- Small bounded helpers may use internal subagents without unnecessary user coordination.
- A legacy push attempt moves to task-event waiting only through a new versioned migration attempt; prior history is preserved.
- A persisted v2 pass reports structural `fail_closed_v2` conformance over `trusted_persisted_attestation`, explicitly reports `cryptographic_actor_or_creation_proof: false`, rejects missing or inconsistent provenance and boolean schema discriminators, and warns that coordinated full-record rewriting or backfill is outside what it can prove.
- Every delivered attempt uses the allowed surface/mode pair: task-event, push, and manual on user-visible or worktree task surfaces with native host/thread identity; automatic only on an internal subagent.
- The first push-to-task-event transition is validated once against pushes unresolved at transition delivery and covers them through complete acyclic lineage; later task-event retries reuse it through ancestry, while omitted, repeated, side-chain, and cyclic migrations fail.
- Task/candidate criteria and candidate-bound passing evidence have exact, nonempty, unique set coverage; implicit waivers fail.
- A required review keeps producer, reviewer, and coordinator pairwise distinct, uses a different native task from production, and only the coordinator is recorded as `accepted_by`.
- Candidate admission follows producer-return reconciliation, review delivery follows admission, and the first wait or notification arming follows review delivery under the selected contract.
- Every effective review gates acceptance; a clean review cannot mask an adverse review. Supersession requires a coordinator-owned exact evidence-bound resolution, while an optional adverse review may remain effective only when the coordinator exactly adjudicates every adverse criterion with prior bound evidence and no confirmed material disposition.
- `consumes` rejects duplicate, unknown, or candidate/authority-ambiguous identities; every consumed candidate and declared prerequisite gates every current and retry-ancestor delivery strictly before dispatch, even when `depends_on` is omitted.
- Every candidate and producer attempt link each other exactly, and every non-superseded task with delivered work identifies a delivered `current_attempt_id`, including failed, blocked, and needs-input outcomes.
- Retry deliveries are strictly causal. Every noncurrent delivered attempt is in complete retry ancestry or has a reconciled same-task acyclic run-level supersession path to current ancestry; unrelated, cross-task, reversed, or undelivered bridges fail, and unresolved delivered work blocks closure. Candidate supersession uses strictly forward `observed_at`, and superseded authorities stale bound tasks, candidates, pointers, and descendants.
- A retry of an uncertain predecessor is strictly later than that predecessor's parsed uncertainty reconciliation for every running or terminal status; pre-retry inspection cannot legalize equality or reversal.
- V2 task and candidate schemas reject local supersession or unknown task fields and missing, empty, boolean, or unsupported candidate kind/location/scope/observed timestamp. Acceptance evidence observers are restricted to the coordinator or an effective structurally qualifying reviewer on the same candidate.
- An attempt-bound active row matches the attempt's task and owner, and no second row may claim the same task/attempt even under a different isolation label.
- Active filesystem write claims undergo host-independent lexical normalization against `project_root` when supplied; POSIX/Windows forms, `.`, repeated separators, and safe `..` cannot hide overlap, mixed relative/absolute claims without a root fail closed, opaque authority tokens remain opaque, and root escape fails.
- A generic `latest_result` uses exact keys with integer version `1` and either four nulls or four nonempty strings. A non-null pointer uses a `sha256` candidate identity and `--project-root` verification proving equality to an actual verified output; only the canonical null pointer may omit the root.

### Independent-parallel probe

- Every module is acceptance-independent.
- Shared inputs are read-only and mutable outputs are disjoint or isolated.
- Each brief has its own deliverable and source-bound acceptance.
- Returned work remains unverified until the coordinator inspects primary evidence.
- One failure leaves independent succeeded siblings reusable.
- The status report accounts for running, failed, succeeded, and held work without extra lifecycle states.

If either probe fails, revise the Skill before adding more complex staged behavior. Do not use a passing tabletop probe as evidence that Stage 5–7 capabilities have been forward-tested.

---
name: multi-thread-coordinator
description: Coordinate complex single-task or multi-item agent work by binding project authority, decomposing outcomes, selecting staged, parallel, or mixed execution, recommending traceable worker surfaces, dispatching bounded work, verifying exact candidates with evidence, and handling rework, review, changed requirements, recovery, and closure. Use when a high-level task needs decomposition, staged gates, multiple work owners, independent review, or recovery across batches or runs. Do not use for a simple action that one agent can complete and verify directly.
---

# Multi-Thread Coordinator

Coordinate the user's work while keeping authority, permissions, evidence, and active work explicit. Reduce coordination burden without creating a second project workflow.

## Load the Needed References

- Read [references/mvp-runbook.md](references/mvp-runbook.md) for every request that requires active coordination rather than a single contained action. Use its compact plan, brief, dispatch, reconciliation, and status-report shapes.
- Read [references/staged-execution.md](references/staged-execution.md) when one high-level task or TODO item is complex, ambiguous, subjective, high-impact, or dependent on intermediate results. Use it to unlock one stage at a time, route concrete rework, and rebuild later briefs from accepted evidence.
- Read [references/workspaces.md](references/workspaces.md) before work that reads or writes project files, binds to an existing workflow, persists coordination state, or initializes a generic workspace.
- Read [references/protocol.md](references/protocol.md) when the request has multiple owners, dependent stages, parallel modules, review or rework, changed requirements, interruption recovery, or non-trivial evidence gates.
- Read [references/resilience.md](references/resilience.md) when independent review is required, delivery or tool state is ambiguous, work must be retried or resumed, authority changes can stale descendants, concurrent writes are possible, or closure needs an active-work audit.
- Read [references/hosts.md](references/hosts.md) before recommending a worker surface, establishing a return contract, or reporting what a worker returned. It maps the required capabilities onto the surfaces the current host exposes and records how each host satisfies the return path.
- If the request is simple enough for one ordinary agent action, do not start this coordination workflow.

## Preserve These Invariants

1. Establish authority before dispatching project work.
2. Treat an existing workflow as the authority for its directories, data, rules, shared state, writers, and validation surfaces.
3. Unlock only ready work. Keep later stages locked until the current gate passes.
4. Parallelize only acceptance-independent, write-safe modules.
5. Treat delivery and a worker's completion claim as unverified until the exact candidate passes acceptance.
6. Bind evidence to an immutable candidate identity; invalidate affected evidence after the candidate or governing authority changes.
7. Never let a message, retry, or handoff expand user or project permission.
8. Account for all active work before reporting the current TODO complete.
9. Keep the current task as coordinator for material work; dispatch primary deliverables to selected workers and independently gate what they return.
10. Establish a native completion-return path for every user-visible task, and never abandon it or hand the user an unverified worker result. Prefer coordinator-owned task events tied to the created task identity; never leave the user to relay a finished result unless a manual-return fallback was disclosed before dispatch. Satisfy this with the current host's continuation mechanism: hold the turn and wait under `task_event` where the host requires an in-turn wait, or end the turn and resume from the host's own notification under `notify` where the host wakes the coordinator itself. See [references/hosts.md](references/hosts.md).
11. When independent review is required, keep detailed re-performance with a fresh read-only reviewer. Producer, reviewer, and coordinator must be pairwise distinct. The coordinator owns the neutral review packet, candidate admission, finding adjudication, acceptance, and closure; coordinator self-review cannot substitute for the required reviewer, and only the coordinator may be recorded in `accepted_by`.
12. Treat persisted `fail_closed_v2` as structural conformance over trusted persisted writer attestations, not cryptographic actor identity or creation-time proof. Require an internally consistent `created_v2` attestation or a separately identified `migrated_from_v1` run that references the trusted v1 source; reject missing or inconsistent provenance, while acknowledging that the audit cannot detect a coordinated full-record relabel or backfill.
13. Bind every current criterion to exactly one passing, candidate-and-authority-bound evidence row observed by the canonical coordinator or an effective structurally qualifying candidate-bound reviewer. A clean review never masks another effective adverse review, every consumed identity must resolve uniquely, every consumed candidate must have current coordinator acceptance before each effective retry-lineage delivery, and every non-superseded task with delivered work must identify its current attempt and account for all other delivered attempts through retry lineage or reconciled same-task run-level supersession.

## Coordinate the Work

For active coordination, maintain one compact logical run plan in native task history unless the Workspace Binding requires persistence. Before dispatch, tell the user the interpreted outcome, selected mode, important boundaries, currently ready work, recommended worker surfaces, and the evidence that will establish acceptance. Ask only the consolidated worker-surface question required below or for a business decision, missing authority, or consequential permission.

### 1. Bind the Workspace and Authority

Resolve the approved project root, authoritative inputs and rules, allowed reads and writes, forbidden paths, shared-writer rules, validation surfaces, data boundary, and external-action permissions.

Use `existing_workflow` mode whenever a suitable workflow already exists. A project folder, repository, user-organized file set, coordinator record, or this Skill's own validation tool is not by itself an existing workflow: this mode requires pre-existing project authority, writer, shared-state, or validation surfaces that govern the work independently of this coordination run. Store only coordination pointers the workflow permits; do not create competing mappings, approvals, release states, module states, or result hierarchies.

Use `generic_workspace` mode only when no suitable workflow exists. When the user has already created an ordinary folder and placed source files there, adopt that folder in place as the project root; do not move, copy, or reorganize those sources merely to fit the coordinator. This logical mode does not require initialization: keep transient coordination in native task history when persistence is unnecessary. When persistence is justified, default to the `adopted_folder` layout with only `RESULTS/` plus `AGENT_WORKSPACE/`. Use `managed_intake` and its `HUMAN_PORTAL/` drop surface only when ongoing file intake is genuinely requested or useful.

After a persistent `generic_workspace` binding passes, use [scripts/init_generic_workspace.py](scripts/init_generic_workspace.py) with the approved binding JSON, batch ID, run ID, canonical coordinator identity, and immutable installed Skill commit or revision. Run `--dry-run` first, inspect its selected layout and exact paths, then initialize. Never run this initializer for native-history-only work or `existing_workflow` mode.

Do not dispatch mutating work while a required authority, permission, evidence source, or writer rule is unresolved.

### 2. Decompose the TODO

For each requested outcome, identify:

- authoritative inputs and governing rules;
- deliverable, consumer, and verification method;
- dependencies and downstream consumers;
- mutable write set and shared authorities;
- ambiguity, business decisions, consequence of error, capability, permission, and risk.

Split by independent module only when sibling output is unnecessary for acceptance and mutable writes are disjoint or isolated. Split by dependent stage when an intermediate result can change, constrain, or safely gate later work. Keep small same-owner work together when separation adds no verification or isolation value.

Treat each user item as an outcome to analyze, not an indivisible task. A request containing one high-level item may still become a staged chain or several genuinely independent modules. Do not require the user to provide a pre-decomposed TODO list.

### 3. Select an Execution Mode

Choose and state the run execution shape, with one sentence of rationale for each chain:

- `staged`: complex, ambiguous, subjective, dependent, or high-impact work; use this by default when an intermediate result matters;
- `parallel`: two or more acceptance-independent, write-safe modules;
- `mixed`: a run-level graph containing independent modules followed by one or more staged join points; individual chains remain `staged` or `parallel`.

If the request has no meaningful stage, delegation, review, or coordination need, it is outside this Skill rather than a `direct` coordinator run. Do not create artificial stages or use available concurrency as a reason to parallelize dependent work.

### 4. Recommend the Work Surface and Preflight It

Do not silently default material work to internal subagents. After decomposition and before dispatch, recommend an execution surface for each ready work package:

- recommend an internal subagent for a short, bounded helper whose result returns immediately to the coordinator and does not need durable user follow-up;
- recommend a user-visible durable task for a material or multi-stage chain when traceability, direct inspection, later continuation, recovery, or likely rework makes a durable task useful. Weigh how durable that surface actually is on the current host and what a fresh worker costs; where workers are scoped to the session, do not recommend one on the promise of continuation later;
- recommend an authorized worktree-backed task when concurrent mutable code changes require checkout isolation.

If the user already chose the surfaces in the current request, follow that choice. Otherwise present the recommended mix and ask one consolidated question before dispatching material work. Small helper work may use an internal subagent without pausing. Creating user-visible tasks requires the user's selection or authorization; one answer may authorize all named tasks in the current run.

The current task remains the coordinator: it may inspect authority, run acceptance checks, reconcile evidence, and route rework, but it must not silently become the primary producer for material deliverables. Keep a dependent chain with the same selected worker where practical. If no selected worker surface is available, report the limitation and ask for a surface choice or provide a bounded manual handoff instead of completing the chain entirely in the coordinator.

Before dispatch, confirm the owner can read the authority, write only allowed destinations, use required tools, inspect the real candidate and evidence, and return through the intended surface. Resolve the host adapter in [references/hosts.md](references/hosts.md) by observing which capabilities the host actually exposes, never by inferring them from a product or model name. For a user-visible task, prefer a coordinator-owned native task-event return: confirm the host exposes durable worker creation, such as `create_thread` on Codex or a background agent on Claude Code, plus a way to learn of completion, then capture the created worker identity and await that exact identity. Where creation returns `threadId` and `hostId`, capture both; a queued setup identifier such as `clientThreadId` is not a runnable task identity and must not be passed to task-state tools. If task-event return is unavailable, use worker push only when the exact coordinator task identity is known and the worker can actively send a native task-to-task message to it. Otherwise do not present that task as an autonomous chain: recommend an internal subagent or identify it as manual-return and state the user burden before dispatch. Never simulate a worker, invent an identity, or claim a return path exists when the surface is unavailable.

### 5. Brief and Dispatch Only Ready Work

Give every worker one concise current-stage brief containing identity, one testable objective, authoritative inputs, satisfied dependencies, allowed reads/writes/actions, prohibited actions, concrete deliverables, evidence, acceptance criteria, return surface, and stop conditions.

For a user-visible task, make the return contract and its version explicit, and choose the contract the host's return model actually supports; resolve that from [references/hosts.md](references/hosts.md).

On a host whose coordinator waits in-turn, default to `expected_return: task_event` with `return_contract_version: task_event_v1`. After creation, record the returned worker `threadId` and `hostId`, establish the first native wait such as `wait_threads` on that exact identity, and only then treat the attempt as `running`. Persist strict causal order: delivery precedes the first wait, coordinator reconciliation precedes acceptance, and an earlier return is reconciled strictly before unrelated new material dispatch. A native wait may expose its completion event and final payload atomically, so a task-event `return_event_received_at` may equal `returned_at`; this narrow observation equality does not relax any other lifecycle boundary. A bounded wait timeout means only that no event arrived in that interval; retain the identity and cursor and wait again without treating the attempt as failed. Do not end the coordination chain while the task is merely running, because nothing would wake the coordinator afterwards. Use `read_thread` only for bounded evidence recovery or missing detail, not as a periodic status poll.

On a host that wakes the coordinator with its own task notification, default to `expected_return: notify` with `return_contract_version: notify_v1`. Record the worker identity, record `return_armed_at` once the notification path for that exact worker is live, and only then treat the attempt as `running`. Delivery precedes arming. End the turn after dispatch and resume from the notification; holding the turn open to poll returns no sooner and wastes the wait. A notify attempt has no wait cursor to retain, so recover missing detail from the worker's returned result rather than from its stored transcript, which on such a host may be the whole conversation.

Under either contract, when the task completes or needs attention, associate the returned final response or question with the run, task, and attempt, then reconcile it before unrelated new material dispatch and verify the exact candidate. Never abandon the return path, and never report a running or merely returned task as finished.

If native task-event waiting is unavailable, `expected_return: push` may instruct the worker to use native task-to-task messaging after producing a result, reaching `needs_input`, or encountering a real blocker, but only after the exact coordinator task/host target and native send capability evidence pass preflight. When that target is recorded, its native pair differs from every delivered `task_event`, `push`, or `manual` producer pair in the run and from every required reviewer pair, regardless of symbolic aliases; this separation applies even when the current attempt uses another return mode. Use `expected_return: manual` only after recording the disclosure and its evidence strictly before delivery. Every delivered `task_event`, `push`, and `manual` attempt records the actual worker `hostId` and `threadId` and belongs only to `user_visible_task` or `worktree` task surfaces; `automatic` belongs only to `internal_subagent` and identifies a native worker distinct from its coordinator parent. A return event reports work; it does not accept it. The coordinator sends any rework or next-stage brief back to the same worker and establishes a fresh return wait for that attempt.

Record `skill_commit_at_creation`, the run's creation-time `return_contract_version`, canonical coordinator, and `schema_provenance`. A native v2 writer attests to an empty creation snapshot and establishment time through a same-record digest; migration creates a differently identified v2 run whose attestation names a trusted preserved v1 source and compares its supplied digest. These are structural consistency checks, not independent proof of who wrote the record or when it was created. If an in-flight legacy push attempt continues under task-event waiting, preserve the push attempt and create one new correlated attempt with an explicit push-to-task-event migration, current dispatch commit, native-state and side-effect reconciliation, and the new worker identity and wait contract. Validate every direct transition independently of current pointer or task status and permit at most one per task. That transition directly retries the latest push unresolved at its own delivery, its complete acyclic `retry_of` lineage includes every earlier unresolved same-task push, and its `contract_migration` names the direct source. Later ordinary task-event retries inherit that validated migration through ancestry and neither repeat it nor retry the original push directly. Source delivery may equal but cannot follow migration; migration must strictly precede replacement delivery, which must strictly precede the first wait. Never rewrite legacy push history as native task-event execution.

Reference authoritative files instead of copying large context. Do not include credentials, unsupported permissions, accumulated chat history, hidden future-stage instructions, or conclusions the worker is meant to test.

For staged work, expose only the current stage and its small deliverable. For parallel work, dispatch only modules with proven independent acceptance and safe writes. A join starts only when every required upstream candidate is current and verified.

Use the dispatch and reconciliation loop in `references/mvp-runbook.md`. Keep status in native task state where possible; do not create a persistent task board merely to mirror it.

For a dependent chain, follow `references/staged-execution.md`: keep later stages `pending` with a concrete lock reason, continue the chain with the same owner when practical, and build the next brief only after the current candidate passes.

### 6. Inspect and Gate the Exact Candidate

Identify the exact returned candidate with a commit, digest, versioned manifest, authoritative record ID, or other immutable scope-appropriate identity. Persisted v2 candidates also record one documented `kind`, a nonempty `location` and bounded `scope`, and a timezone-aware canonical `observed_at`. Inspect actual files, diffs, calculations, source records, tests, or rendered output as required; do not accept a summary alone.

Pass a gate only when the task and candidate carry the same nonempty, unique structured criterion set; each criterion has exactly one passing evidence row bound to the current candidate identity and authority; `candidate.produced_by` and `attempt.candidate_id` bind each other exactly; boundaries were respected; material findings are resolved; and no dependency or conflicting writer can still change it. Persisted v2 audit does not accept implicit waiver fields. Then mark the attempt `succeeded` and unlock only declared dependents. Treat a task's declared dependencies and consumed identities as immutable for its attempt lineage. Before delivering its current attempt or any retry ancestor, require each `consumes` identity to be unique and resolve either to an authority declared on that consumer or to a known candidate; require every consumed candidate and declared prerequisite to resolve to its producer task's current coordinator-accepted attempt, with acceptance strictly earlier than that attempt's own delivery.

Use `failed` for a concrete unmet criterion or error, `needs_input` for one specific user choice or missing authority, `blocked` only after safe alternatives are exhausted, and `superseded` when work no longer matches current authority. No non-pass outcome unlocks downstream work.

### 7. Rework or Review

Return a concrete failure delta to the original owner first when its context remains valid. Name the exact candidate, failed criterion, expected and observed result, evidence, impact, smallest requested change, protected behavior, and checks to rerun. Create a new attempt and candidate identity after any change.

For staged work, use the rework and adaptive-brief procedure in `references/staged-execution.md`. A failed or unresolved attempt leaves every dependent stage locked.

Use a fresh read-only reviewer when risk or independence warrants it, especially for irreversible or security-sensitive work, external publication, material financial or executive output, high-impact interpretation, or a critical join. The coordinator prepares a neutral, immutable candidate-bound packet containing current authority, criterion-level coverage, raw evidence, boundaries, lineage, and the native return contract. Exclude the producer's verdict, a preferred conclusion, and unsupported narrative.

When `review_required: true`, producer, reviewer, and coordinator must be pairwise distinct, and the reviewer owns detailed assigned re-performance. The reviewer task's native host/thread pair must also differ from the producer attempt. It must not mutate the candidate, waive a criterion, unlock dependent work, update a current-result pointer, or accept its own review. The coordinator reconciles the producer return, admits the exact candidate, dispatches review, establishes the first wait, reconciles the returned review, adjudicates findings, maps every criterion to current evidence, records itself in `accepted_by`, and alone accepts or closes. Delivery/wait, return/reconciliation, reconciliation/resolution, and resolution/acceptance remain strictly ordered; one native review response may record `completed_at <= return_event_received_at <= returned_at`. The packet uses exact nested schemas, bounded iterative inspection, and a maximum depth of 64 while excluding verdict-biased keys or unsupported narrative. Every effective review gates acceptance: one clean review cannot mask another failed criterion or material finding. Preserve the existing later-clean-review supersession route. For an optional review only (`review_required: false`), the coordinator may instead reject every adverse criterion exactly once as `false_positive`, `nonmaterial`, or `outside_supported_scope`, but only with passing same-candidate/same-criterion evidence observed before adjudication and with adjudication strictly after review reconciliation and before acceptance. This prevents both review shopping and a de facto optional-review veto: the reviewer challenges the candidate, while the coordinator retains cross-task authority and in-scope materiality ownership. Confirmed material, omitted, structurally invalid, or required-review findings hold the gate; clean reviews cannot be discarded. If the independent reviewer, complete packet, returned review evidence, or permitted resolution is unavailable, keep the gate held; do not substitute coordinator self-review.

Accept reviewer findings only when they show concrete impact within the current supported scope. The reviewer challenges the candidate; it does not become a new project authority.

For persisted coordination, use the review, attempt, recovery, supersession, and active-write records in `references/resilience.md`. Run [scripts/audit_coordination_state.py](scripts/audit_coordination_state.py) before accepting a required independent review, retrying uncertain work, moving a current-result pointer, or claiming closure. For a non-null generic-workspace result, include the approved `--project-root` so the audit verifies the manifest and actual files rather than only pointer fields.

### 8. Handle Changed Requirements

Classify new user input as a replacement, addition, or status/question. When authoritative input or the intended result changes, create a new batch, identify tasks and candidates bound through `authority_identities` as well as explicit consumers and descendants, mark conflicting work `superseded`, and treat late affected output as stale. Preserve unaffected verified work.

Resume from the earliest affected stage with a rebuilt brief. Do not move the current-result pointer until replacement work passes its gates. Ask the user only for a concrete business judgment, missing authority, or permission that cannot safely be inferred.

### 9. Recover and Close

Before a long pause, handoff, or interruption, retain a compact recovery capsule when native history is insufficient. On resume, re-read current authority, verify candidate identities, inspect actual task and command state, and resolve possible side effects before retrying. Never blindly resend a mutating request after an ambiguous timeout.

When state is persisted, audit the reconciled run after recovery and use `--closure` before reporting the effective TODO complete. Treat a failed audit as a concrete hold: inspect the reported invariant, reconcile native and artifact state, then audit again rather than editing records to manufacture a pass.

Before reporting completion:

1. account for every requested item and follow-up using only `pending`, `running`, `needs_input`, `blocked`, `succeeded`, `failed`, or `superseded`;
2. verify every usable output by exact candidate identity and current upstream inputs;
3. reconcile the existing workflow's current pointer or the generic workspace result pointer;
4. account for every delivered noncurrent attempt through complete retry ancestry or reconciled, acyclic, same-task run-level supersession, and hold closure on unresolved delivered-without-return work; `status: superseded` alone never discharges an attempt;
5. enumerate and resolve all active agents, tasks, commands, monitors, automations, worktrees, and external operations;
6. report outputs, evidence, remaining risk, blockers, and work intentionally not done.

Use the compact current-status report in `references/mvp-runbook.md` for user updates. Distinguish work returned by a worker from work verified by the coordinator.

Do not introduce `final`, `approved`, or `frozen` project states. A run may succeed while the broader project continues.

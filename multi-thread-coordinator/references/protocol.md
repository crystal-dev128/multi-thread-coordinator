# Coordination Protocol

Use this reference for multi-owner work, dependent stages, parallel modules, evidence gates, rework, independent review, changed requirements, or recovery. Keep native task and subagent tools as the transport; these contracts define meaning and traceability, not a new broker or task board. Use [resilience.md](resilience.md) for the exact fresh-review, interruption, retry, supersession, active-write, and closure audit procedure.

## Contents

1. Identifiers and scope
2. Decomposition and dependency edges
3. Mode selection and execution gates
4. Work surface and capability preflight
5. Task brief contract
6. Attempts and message correlation
7. Status vocabulary
8. Candidate and evidence references
9. Acceptance gates
10. Rework and independent review
11. Requirement changes and supersession
12. Recovery, retry, and closure

## 1. Identifiers and Scope

Use only the identifiers needed to distinguish current work and evidence:

| Concept | Purpose | Suggested identifier |
|---|---|---|
| Binding | Points to authorities and boundaries | `binding_v001` |
| Batch | One effective set of inputs and requirements | `batch_NNNN` |
| Run | One coordinated plan against a batch | `run_NNNN` |
| Work chain | A dependent sequence or independent module | `chain_<slug>` |
| Stage | A gated step inside a chain | `stage_NNN` |
| Task | A bounded unit with one accountable owner | `task_<slug>` |
| Attempt | One dispatch or continuation | `attempt_NNN` |
| Candidate | Exact artifact under evaluation | `candidate_<slug>_<NNN>` |
| Evidence | Observation tied to one candidate | `evidence_<slug>_<NNN>` |

Keep identifiers unique within their parent. Correlate an attempt with `(batch_id, run_id, task_id, attempt_id)` rather than a mutable title.

Create a new batch when authoritative input, a governing requirement, or the intended result changes. Create a new run when the same batch restarts after stopping or its execution plan is materially replaced. Keep ordinary rework, continuation, or owner replacement in the current run as a new attempt when the batch and plan remain current.

Preserve history. Move current-result pointers only after replacement output passes acceptance.

For a persisted current-contract run, record integer `schema_version: 2`, `skill_commit_at_creation`, the creation-time `return_contract_version`, one canonical `coordinator_id`, and one exact `schema_provenance` object. Schema discriminators are exact integers, never booleans. Keep those creation fields immutable by contract. Every v2 run explicitly carries the eight list-valued record keys `chains`, `tasks`, `attempts`, `candidates`, `evidence`, `reviews`, `supersedes`, and `active_work`, even when a list is empty; omission is not equivalent to an empty v2 record. Schema-version-1 records remain readable as legacy history, may treat omitted record-list keys as empty, and do not establish structural `fail_closed_v2` conformance.

A run created natively under v2 records:

```yaml
schema_provenance:
  mode: created_v2
  established_at: <timezone-aware timestamp before any delivery>
  creation_digest: <canonical sha256 of the empty v2 creation snapshot>
```

The creation snapshot contains schema/run/batch/binding identity, Skill commit, creation return contract, coordinator identity, `established_at`, and every run record list as empty. Canonicalize it with the same sorted-key compact UTF-8 JSON rule used for review packets. The initializer emits this trusted-writer structural attestation when it creates `run.json`.

The auditor reports `provenance_trust_model: trusted_persisted_attestation` and `cryptographic_actor_or_creation_proof: false`. The same-record creation digest catches missing or internally inconsistent fields but is not an independent receipt and cannot prove actor identity, historical creation time, or absence of a coordinated full-record rewrite/backfill. Likewise, migration digest comparison proves equality only to the supplied trusted v1 source record. Explicit migration is the required contract and audit shape; cryptographic historical provenance would require an independently controlled signing or append-only authority that this Skill does not implement.

By contract, do not change a populated v1 record to `schema_version: 2` and backfill fields. Explicit schema migration creates a new v2 `run_id` and records:

```yaml
schema_provenance:
  mode: migrated_from_v1
  established_at: <timestamp before any target-run delivery>
  source_run_id: <trusted preserved v1 run id different from the target>
  source_run_digest: <canonical sha256 of the complete supplied v1 source record>
  reason: <why the new contract is required>
  evidence: [<source capture or authority evidence>]
```

The source remains schema v1, shares the target batch and binding, and is supplied to the audit with `--legacy-run` so its digest can be re-performed. This schema migration is distinct from per-attempt push-to-task-event migration; neither rewrites legacy history.

## 2. Decomposition and Dependency Edges

Split by independent module when each unit can pass without an unresolved sibling and without unsafe overlapping writes. Split by dependent stage when an intermediate conclusion, artifact, or decision determines later work. Do not split solely to create more workers.

Use three graph edge types:

- `depends_on`: the target stays locked until the source passes;
- `consumes`: the target uses an identified authority or candidate;
- `supersedes`: a newer requirement, attempt, or candidate makes an older one non-current.

Represent write conflicts on tasks and authorities, not as another edge type.

Status alone does not unlock a dependency. Treat each task's `depends_on`, `consumes`, and authority declarations as the immutable applicable snapshot for its current attempt and complete retry ancestry; changing them requires a new task identity or explicit supersession rather than rewriting old attempt causality. For each delivered attempt in that effective lineage, resolve every `depends_on` task's current attempt and require its `accepted_at` to be owned by the canonical coordinator and strictly earlier than the child's own attempt `delivered_at`. Task-level and candidate-level `consumes` lists contain no duplicates, and every identity resolves uniquely either to a known candidate or to an authority declared on that same consumer; unknown or candidate/authority-ambiguous identities fail. Resolve each consumed candidate to its producer task's current accepted attempt and apply the same strict-before gate even when `depends_on` omits that producer. Apply these rules to running and terminal child attempts alike; equal timestamps or later prerequisite acceptance prove that the child dispatched too early, and a pre-retry audit cannot erase the earlier dispatch. Every non-superseded task with delivered work records a `current_attempt_id` pointing to delivered work, including `failed`, `blocked`, and `needs_input` outcomes. When a superseded task deliberately has no current pointer, fail closed by applying its immutable declarations to every delivered same-task attempt; later reconciliation can discharge transport closure but cannot legalize an early dispatch.

The persisted v2 auditor uses an exact compact task allowlist: `task_id`, `status`, optional `owner_surface`, `depends_on`, `consumes`, `current_attempt_id`, `authority_identities`, `acceptance_criteria`, and optional `decisions`. Do not place `supersedes`, free-form extensions, or a duplicate task-board schema on a task; `run.supersedes` remains the sole supersession authority.

## 3. Mode Selection and Execution Gates

Evaluate the run and its chains in this order:

1. Select `staged` when intermediate output can change, constrain, or gate later work. Default to staged execution for complex, ambiguous, subjective, or high-impact work.
2. Select `parallel` only for at least two acceptance-independent, write-safe modules.
3. Select `mixed` at the run level when independent modules feed a staged join; keep each individual chain `staged` or `parallel`.

If the request needs no meaningful delegation, staged gate, independent review, or coordination, handle it outside this Skill rather than recording a `direct` chain.

For every staged step, define its authoritative input, predecessor candidate, allowed action, one small deliverable, evidence, acceptance conditions, and dependents. Unlock only the current stage. Rebuild later briefs after each pass so they consume the actual succeeded candidate and current authority.

Before parallel dispatch, prove that each module has independent acceptance, consumes no unresolved sibling, has disjoint or isolated mutable writes, reads stable shared inputs, and has a known join rule. Accept modules independently unless a declared dependency or changed shared authority connects them.

Start a join only when all required upstream candidates are current and `succeeded`. List their exact identities in the join brief. Supersede the join and affected descendants when an upstream candidate becomes superseded.

## 4. Work Surface and Capability Preflight

Recommend the surface that best matches traceability and coordination value:

| Need | Preferred surface |
|---|---|
| Short bounded helper with immediate return and no durable follow-up | Internal subagent, when available and permitted |
| Material, multi-stage, long-running, resumable, or likely-to-be-reworked chain | User-visible durable task with a verified native completion-return path |
| Concurrent mutable writes needing checkout isolation | Authorized worktree-backed task |
| No selected worker surface available | Revised recommendation or concise manual handoff |

After decomposition, present the recommended mix and ask one consolidated surface question before material dispatch unless the user already chose in the current request. Small helper work may use internal subagents without pausing. One answer may authorize all named user-visible tasks for the current run.

Keep a dependent chain with one continuing selected owner where practical. The current task remains coordinator and acceptance owner, not the primary producer of material deliverables. Change workers for independence, unavailable capability, repeated evidenced failure, contamination risk, or fresh review—not merely to create activity. If no selected surface is available, report that limitation rather than silently completing the material chain in the coordinator.

Confirm before dispatch that the owner can:

- read the authoritative inputs;
- write only allowed destinations;
- execute required local tools;
- use permitted network, browser, connector, or application access;
- inspect the real candidate and raw evidence;
- return through the intended surface.

Resolve the host adapter in [hosts.md](hosts.md) before recommending a surface. Bind it from the capabilities the host actually exposes rather than from a product or model name, and record the resolved adapter with the run so recovery and rework use the same return semantics as dispatch. Durability is a property of the host, not of the recommendation: where durable workers are scoped to the session, do not recommend one for work whose value depends on continuation after the session ends, and weigh the cost of a cold worker against the traceability gained.

For an autonomous user-visible chain, prefer coordinator-owned task events because the coordinator receives the worker identity directly from task creation and does not need the worker to discover its parent. Preflight that durable worker creation and a completion-return path are exposed. After creation, capture the exact returned worker identity. Where creation yields `threadId` and `hostId`, capture both; `clientThreadId` only identifies queued setup and must not be used with tools that require a ready task identity. On a host that returns a usable worker identity immediately, that precaution is satisfied on creation, but the identity is still recorded with the attempt before it is marked `running`.

If native event waiting is unavailable, preflight two facts before using worker push: the coordinator's exact native task identity is known, and the worker can send a native task-to-task message to it. If neither event waiting nor verified push is available, select an internal subagent that returns automatically or label the user-visible task manual-return and disclose that the user must bring the result back. Do not present periodic status reads as completion return.

Set concurrency to the lowest of ready independent work, platform capacity, write-safe ownership capacity, and any user or project limit. Reserve enough coordinator capacity to inspect results and manage joins.

## 5. Task Brief Contract

Use this logical shape for every dispatched task:

```yaml
identity:
  batch_id: batch_NNNN
  run_id: run_NNNN
  chain_id: chain_<slug>
  stage_id: stage_NNN | null
  task_id: task_<slug>
  attempt_id: attempt_NNN
owner: <internal subagent, user-visible task, or worktree identity>
surface_decision: <automatic small helper or current user selection>
objective: <one testable outcome>
authority_identities: []
inputs:
  - <authority or succeeded candidate reference>
dependencies: []
allowed:
  read: []
  write: []
  actions: []
prohibited: []
deliverables:
  - location: <expected path or return surface>
    description: <small concrete artifact>
evidence_required: []
acceptance_criteria:
  - criterion_id: criterion_<slug>
    requirement: <one current observable requirement>
return:
  expected_return: automatic | task_event | push | manual
  return_contract_version: automatic_v1 | task_event_v1 | push_v1 | manual_v1
  skill_commit_at_dispatch: <immutable installed Skill commit or revision>
  worker_thread_id: <created native task id or null>
  worker_host_id: <native host id when required or null>
  first_wait_at: <timestamp or null>
  return_cursor: <latest native wait cursor or null>
  coordinator_task_id: <exact native task id or null>
  coordinator_host_id: <native host id when required or null>
  events: [completed, needs_attention] | [result, needs_input, blocked]
  required_fields: [run_id, task_id, attempt_id, disposition]
stop_or_escalate_when: []
```

Use one objective and only the unlocked stage. Name output locations before work begins. Make acceptance observable. Point to authoritative inputs instead of copying them. Exclude credentials, accumulated chat history, hidden permissions, and the coordinator's untested conclusions.

## 6. Attempts and Message Correlation

Use native task or subagent history. Do not create a mailbox, socket, callback file, message card system, or permanent message broker. Internal subagents return through their native parent relationship.

For a user-visible task, default to `expected_return: task_event`:

1. Create the task through the native user-visible task surface, such as `create_thread`, and capture its returned `threadId` and `hostId`.
2. Record the attempt's `skill_commit_at_dispatch`, `return_mode`, and `return_contract_version`. Mark it delivered only after a ready worker identity exists. If creation returns only `clientThreadId`, record setup as pending and resolve the ready task before waiting or claiming dispatch. On a host that returns a usable worker identity immediately, that precaution is satisfied on creation.
3. Establish the return path required by the host's model, then mark the attempt `running`. Call the native event wait capability, such as `wait_threads`, with the exact worker identity under `task_event`, and record the first wait contract; for multiple ready workers, use one supported multi-target wait rather than one status loop per task. Under `notify`, confirm instead that the host's notification path for that exact worker is live, record `return_armed_at`, and end the turn; resuming happens from the notification. See Section 6a.
4. Treat `completed` or `needs_attention` as a returned event. Preserve the returned final text, question, worker identity, and cursor with the attempt.
5. Treat a bounded wait timeout as no new event, not as failure, completion, or permission to retry mutation. Reuse the returned cursor in the next bounded wait and avoid narrating unchanged snapshots.
6. If user input interrupts the wait, classify that input, retain the worker identity and cursor, and resume or supersede the wait according to the current requirement. Do not lose the running task from active-work accounting.
7. Use a bounded worker read, such as `read_thread`, only to recover omitted evidence, inspect a task that needs attention, answer a user status request, or reconcile after interruption. It is not the normal completion detector. Where the host's stored worker output is the worker's full transcript rather than its result, read the returned result instead of that file; reading the transcript can exhaust the coordinator's own context and end the run.

Apply a return-first barrier: before dispatching unrelated new material work, reconcile every `completed` or `needs_attention` event already delivered to the coordinator. Correlate it to the current attempt, classify stale or superseded output, inspect its candidate or blocker, and record the coordinator reconciliation. Receiving or reconciling a return still does not accept it.

Use strict causal ordering unless a platform-supplied monotonic token proves order: push preflight precedes delivery; task-event delivery precedes the first wait; notify delivery precedes arming; delivery precedes applicable return evidence; `returned_at` precedes coordinator reconciliation; and reconciliation precedes acceptance. A return reconciliation must also be strictly earlier than an unrelated later material dispatch. The one narrow wall-clock exception is an atomic native observation: one task-event wait response, or one notify event delivered together with its payload, may establish `return_event_received_at <= returned_at`, including equality. This records non-decreasing observation, not causal execution order, and does not relax delivery, first wait, arming, reconciliation, acceptance, or later-dispatch boundaries. Push keeps its return event strictly before `returned_at`; manual uses `returned_at` as its return evidence.

Current-contract attempts use an exact common lifecycle field set plus only the fields for their declared mode. Mode provenance is fail-closed:

```yaml
# push
coordinator_return_target: {task_id: <coordinator task>, host_id: <host>} # run-level
push_target: {task_id: <same task>, host_id: <same host>}
push_capability:
  name: <native task-to-task send capability>
  verified_at: <timestamp>
  evidence: [<capability observation>]
push_preflight_at: <strictly after capability verification and before delivery>

# notify
return_armed_at: <strictly after delivery, when the host's notification path for this exact worker is live>

# manual
manual_disclosed_at: <strictly before delivery>
manual_disclosure_evidence: [<user-facing disclosure observation>]

# automatic
automatic_return:
  surface: internal_subagent
  parent_coordinator_id: <canonical coordinator>
  worker_native_id: <same identity as attempt owner, distinct from parent>
```

Every delivered attempt also passes this exact surface/mode matrix:

| Return mode | Allowed `owner_surface` |
|---|---|
| `task_event` | `user_visible_task` or `worktree` |
| `notify` | `user_visible_task` or `worktree` |
| `push` | `user_visible_task` or `worktree` |
| `manual` | `user_visible_task` or `worktree` |
| `automatic` | `internal_subagent` only |

Every delivered `task_event`, `notify`, `push`, or `manual` attempt records a nonempty native `worker_host_id` and `worker_thread_id`; these fields remain part of preserved history and bind any later independent-review identity comparison. A non-null run `coordinator_return_target` has exactly `task_id` and `host_id`. `push_target` must exactly equal that run target, and the target's native host/task pair must differ from every delivered visible/worktree producer pair in the run and every required reviewer host/thread pair, including when a producer's own return mode is task-event, notify, or manual; symbolic aliases, mixed-mode history, or target-free capability claims do not pass. `manual` is never autonomous. `automatic` is valid only for a task whose `owner_surface` is `internal_subagent`; its worker/owner differs from the coordinator parent, and a user-visible task cannot claim automatic native return. Nested mode objects use exactly the fields shown.

If neither event contract is available, a user-visible task with `expected_return: push` must actively send a message to the supplied coordinator task after reaching `result`, `needs_input`, or `blocked`; in the Codex app this may use a native task-to-task send capability such as `send_message_to_thread`, and on Claude Code a background worker may message the main conversation directly. Use this only after target identity and send capability are verified. `expected_return: manual` requires the user to relay the result and therefore is not an autonomous chain.

When native identifiers are insufficient, logically associate an event with:

```yaml
message_id: <unique within run>
run_id: run_NNNN
task_id: task_<slug>
attempt_id: attempt_NNN
intent: notify | request | wait | resume | result
reply_to: <message_id or null>
continues: <prior attempt or message, or null>
expected_return: none | automatic | task_event | push | manual
```

Interpret the intents as follows:

- `notify`: one-way information;
- `request`: work whose result must return;
- `wait`: a blocking request when waiting is intended;
- `resume`: a new attempt continuing known paused or interrupted work;
- `result`: a candidate, evidence, question, or failure tied to an attempt.

Treat transport acceptance as `delivered` and a response as `returned`. These are observations, not work statuses. Neither establishes success.

For a task event or pushed return, include the exact run, task, and attempt identity; the worker task identity; candidate identity and evidence pointers when a candidate exists; and the exact question or blocker otherwise. Map native completion to `disposition: result`; map a task requiring a decision, permission, or missing input to `needs_input`; preserve a real terminal blocker as `blocked`. Reuse one message identity only to deduplicate a transport retry. Do not send routine progress callbacks unless the coordinator explicitly requested one.

The coordinator normally becomes active from the native task event or verified worker push, verifies the real candidate, and then sends a correlated next-stage or rework request to the same worker. After each follow-up, establish a fresh event wait or verified push contract for the new attempt. Event waiting is the completion transport; periodic `read_thread` inspection is not. Inspect task state directly only when recovering from interruption, resolving ambiguous transport, filling an evidence gap, or answering a user status request.

After ambiguous delivery, timeout, or tool state, inspect native state and candidate locations, determine whether side effects may exist, reuse or resume known work where safe, and otherwise create a new identified attempt that records the uncertainty. Never blindly resend a mutating request.

When an in-flight task created under `push_v1` moves to `task_event_v1`, preserve the legacy attempt and create a new attempt that names it in both `retry_of` and this migration record:

```yaml
contract_migration:
  from_attempt_id: attempt_NNN
  from_skill_commit: <legacy immutable revision>
  from_return_contract_version: push_v1
  to_skill_commit: <current immutable revision>
  to_return_contract_version: task_event_v1
  migrated_at: <timestamp>
  reason: <why the return surface changed>
  evidence:
    - <native-state and side-effect reconciliation>
```

The first task-event transition also needs the ordinary pre-retry audit, ready `threadId` and `hostId`, and a first native wait. Every delivered retry has a delivered direct predecessor and is delivered strictly later; if that predecessor records uncertainty, its parsed `reconciled_at` must also be strictly earlier than retry delivery, regardless of either task's current or terminal status. A completed pre-retry audit cannot override an equal, later, missing, or invalid reconciliation boundary. Reversed or undelivered retry ancestry cannot hide a later sibling. Validate every direct push-to-task-event transition at its own delivery, whether or not it is current, and permit at most one such transition per task. For a delivered task-event attempt, index all earlier same-task attempts and its complete `retry_of` ancestry, which must be acyclic. When an earlier `push_v1` attempt was not reconciled strictly before transition delivery, that transition directly retries the latest such push, includes every earlier unresolved push in its lineage, and names the direct source in `contract_migration.from_attempt_id`. Its chronology must prove `source delivered_at <= migrated_at < replacement delivered_at < first_wait_at`; source delivery may equal migration because inspection can record the same instant, but every later causal boundary is strict. Later task-event retries rely on that validated transition, omit a repeated migration record, and do not directly retry the original push. Do not edit the prior attempt's return mode, identity, delivery, or side-effect history.

Contract migration is a legacy Codex path. It exists to move an in-flight `push_v1` task onto `task_event_v1`, and it has no Claude Code counterpart, because `notify_v1` is new and no attempt predates it. A `notify_v1` attempt therefore never carries `contract_migration`.

### 6a. Two Return Models

The requirement is that a dispatched attempt always has a live return path and that the coordinator closes the gate. Hosts satisfy it in opposite directions, and the difference determines what the coordinator does at the end of its turn.

Under a **pull return**, the coordinator holds the turn and blocks on the wait capability for the exact worker identity. Ending the turn while a dispatched task is running abandons the return path, because nothing will wake the coordinator afterwards.

Under a **re-invocation return**, the host wakes the coordinator with a task notification when a background worker finishes. The coordinator is expected to end its turn after dispatch. Holding the turn open to poll returns no sooner and wastes the wait; a bounded blocking read is justified only when the very next coordinator action depends on that one result and nothing else useful can proceed meanwhile.

Both models forbid the same two failures: abandoning the return path, and presenting a running or merely returned attempt as an accepted result. Neither model makes a returned event an acceptance. Record which model the run is operating under, so that a resumed run does not reuse the wrong one.

## 7. Status Vocabulary

Use only these work statuses:

| Status | Meaning |
|---|---|
| `pending` | Known and eligible later, but not started |
| `running` | The identified attempt has started |
| `needs_input` | Paused for one concrete decision, authority, or input |
| `blocked` | No safe progress is possible without external change or new authority |
| `succeeded` | The coordinator verified the exact candidate against every criterion |
| `failed` | The attempt ended with a concrete unmet condition or error |
| `superseded` | Changed scope, authority, or a newer candidate makes the work non-current |

Continue paused or failed work through a new attempt rather than rewriting history. Allow a succeeded result to become superseded when its governing input changes. Derive stage and run summaries from current required tasks; do not add approval or release lifecycle states such as `final`, `approved`, or `frozen`.

## 8. Candidate and Evidence References

Identify every evaluated artifact:

```yaml
candidate_id: candidate_<slug>_<NNN>
kind: git | file | directory_manifest | dataset | document | message_result
location: <pointer within the Workspace Binding>
scope: <bounded files, sheets, rows, sections, or records>
identity:
  method: git_commit | sha256 | versioned_manifest | authoritative_record_id
  value: <immutable identity>
  secondary: <path, tree, size, or version when useful>
produced_by: <task-attempt key>
authority_identities: [<current immutable authority identities>]
consumes: []
acceptance_criteria:
  - criterion_id: criterion_<slug>
    requirement: <exact current requirement>
observed_at: <timestamp>
source_snapshots: []
review_required: true | false
```

Candidate records never carry a local `supersedes` field. The run-level `run.supersedes` graph in Section 11 is the sole supersession authority. `candidate.observed_at` is the canonical candidate chronology field: a candidate replacement has a distinct identity and an `observed_at` strictly after its subject, including rollback candidates. For every persisted candidate, `candidate.produced_by` and `attempt.candidate_id` point to each other exactly; enforce the link for returned, accepted, and other effective records, not only a succeeded current attempt.

Every schema-v2 candidate explicitly carries boolean `review_required`; omission cannot mean `false`. It also requires all four artifact descriptors shown above: `kind` must be exactly one of `git`, `file`, `directory_manifest`, `dataset`, `document`, or `message_result`; `location` and `scope` are nonempty strings; and `observed_at` is a valid timezone-aware ISO-8601 timestamp. Missing, empty, boolean, or invented descriptor values fail before review or acceptance interpretation.

Use a Git commit plus relevant paths for code that is not the generic published current result. Use a digest or versioned manifest for files, directories, workbooks, and documents. For data, include the authority version and exact table, sheet, row, or query scope. A non-null generic published `latest_result` is narrower: its candidate identity method is `sha256`, and that digest must equal at least one result-manifest output whose declared digest was verified against the actual file.

For persisted v2, the task and candidate carry the same nonempty set of unique `{criterion_id, requirement}` rows. Bind exactly one admission evidence row to each criterion:

```yaml
evidence_id: evidence_<slug>_<NNN>
candidate_id: candidate_<slug>_<NNN>
criterion_id: criterion_<slug>
requirement: <exact current requirement>
result: pass
authority_identities: [<exact candidate authority identities>]
candidate_identity:
  method: <same immutable method>
  value: <same immutable value>
  secondary: <same optional scalar>
kind: inspection | diff | test | calculation | source_check | render | review
method: <command or review procedure>
raw_output: <nonempty pointer to primary output>
observed_by: <coordinator or reviewer identity>
observed_at: <timestamp>
```

Evidence rows use exactly these fields. `observed_by` equals either the canonical run coordinator or the reviewer identity on an effective, structurally qualifying review bound to that same candidate; a producer, unrelated identity, malformed or wrong-candidate reviewer, or superseded reviewer cannot attest acceptance evidence. The qualifying review need not be clean merely to establish who performed a factual observation, but every effective adverse review still holds acceptance through the independent-review gate. Missing, extra, duplicate, failed, stale-authority, stale-candidate, or unmapped rows hold acceptance; observation must strictly precede acceptance. Implicit `waiver` or `waivers` fields are outside the current persisted-v2 audit contract. Distinguish source fact, observation, and inference. Retain raw output when it materially supports review or recovery. Invalidate affected evidence after the candidate or authority changes. Use rendered inspection when layout is part of correctness.

## 9. Acceptance Gates

The coordinator owns every gate. Evaluate the current brief and criteria, exact candidate, required evidence, current authority identities, unresolved findings, dependency state, and write conflicts. Every accepted current-contract attempt records a non-empty `accepted_by` equal to the run's canonical `coordinator_id`.

Pass only when:

- the candidate identity matches the real current artifact;
- every criterion maps exactly once to passing current evidence;
- permissions and path boundaries were respected;
- material findings are resolved or adjudicated within scope;
- no unresolved dependency or conflicting writer can still change the candidate.

On pass, mark the attempt `succeeded`, record its candidate pointer, and unlock only declared dependents. On non-pass, use the precise status and unlock nothing.

## 10. Rework and Independent Review

Send rework to the original owner first while its context remains valid. Include:

- exact candidate and failed criterion;
- expected and observed behavior or artifact;
- evidence location and material impact;
- smallest requested delta;
- paths and behavior that must remain unchanged;
- checks to rerun.

Create a new attempt and candidate identity for changed work. Change owner when capability is missing, the same evidenced failure repeats without progress, the owner is unavailable, or clean context is necessary.

Use a fresh reviewer by default for security-sensitive or irreversible work, external publication, material financial or executive output, critical joins, disputed high-impact source interpretation, or explicit independent QA. Keep the review read-only unless a separate fix candidate is authorized.

Use a hybrid gate. The coordinator owns authority binding, packet construction, candidate admission, reviewer capability preflight, return reconciliation, finding adjudication, acceptance, and closure. The fresh reviewer owns detailed assigned re-performance. When `review_required: true`, coordinator self-review is not independent review and cannot substitute for a fresh reviewer.

Give the reviewer this compact neutral packet, bound to an immutable digest over the packet excluding `packet_digest`:

Compute `packet_digest` as lowercase SHA-256 hex over UTF-8 JSON after removing `packet_digest`, sorting object keys recursively, preserving Unicode characters, and using `,` and `:` separators with no added whitespace.

```yaml
packet_schema_version: 1
packet_id: review_packet_NNN
packet_digest: <canonical sha256>
correlation:
  batch_id: batch_NNNN
  run_id: run_NNNN
  task_id: task_<slug>
  attempt_id: attempt_NNN
  skill_commit_at_creation: <immutable revision>
candidate:
  candidate_id: candidate_<slug>_NNN
  identity:
    method: <identity method>
    value: <immutable identity value>
    secondary: <optional scalar detail>
  scope: <bounded artifact scope>
  producer: <producer identity>
  source_snapshots: []
authority:
  identities: []
  requirements:
    - criterion_id: criterion_<slug>
      requirement: <current authoritative requirement>
  decisions: []
review_matrix:
  - criterion_id: criterion_<slug>
    requirement: <same current requirement>
    evidence_required: []
boundaries:
  read_only: true
  allowed_reads: []
  required_capabilities: []
  prohibited_actions: []
raw_evidence: []
lineage:
  predecessor_candidates: []
  protected_behavior: []
return_contract:
  return_mode: task_event
  return_contract_version: task_event_v1
  skill_commit_at_dispatch: <immutable revision>
  events: [completed, needs_attention]
```

The packet must cover the exact current criterion set and authority identities. Every nested object and object-valued list row uses only the fields shown in this schema; unknown fields fail the packet gate. Inspect packet nesting iteratively, cap nesting depth at 64, and reject deeper packets before canonical digest work. This keeps malformed or adversarial persisted state an auditable data failure instead of a coordinator crash. Reject verdict-bias keys such as `producer_verdict`, `preferred_conclusion`, `desired_verdict`, or `unsupported_narrative` anywhere within that bound. Supply factual prior findings only when they remain current regression targets. Worker `threadId`, `hostId`, first-wait timestamp, and returned cursor arise after task creation, so record them on the review execution record rather than mutating the digest-bound packet.

Producer, reviewer, and coordinator must be pairwise distinct, and reviewer `(worker_host_id, worker_thread_id)` must differ from the producer attempt's native pair. After producer return reconciliation, the coordinator records `admitted_at`, then `delivered_at`, then establishes `first_wait_at`; each boundary is strict. Review dispatch is material dispatch for the return-first barrier.

The reviewer remains read-only and attests that it did not mutate the candidate, waive criteria, unlock dependents, update a current-result pointer, or accept the candidate. It returns exactly one `{criterion_id, requirement, result, evidence}` row per criterion plus structured material findings. One native wait response may atomically expose completion, return event, and payload, so record `completed_at <= return_event_received_at <= returned_at`; reversal fails. The coordinator then records `reconciled_at` and `reconciled_by`; returned/reconciled and reconciled/accepted remain strict, and `accepted_by` is the coordinator.

Every review declares `review_status: effective | superseded`. Every effective review gates acceptance, including a review that was optional when dispatched: one clean result cannot mask another effective failed criterion, open material finding, invalid return, or late reconciliation. Preserve an adverse review as `superseded` only through this coordinator-owned record:

```yaml
resolution:
  replacement_review_id: <later effective clean review on the same candidate>
  resolved_by: <canonical coordinator>
  resolved_at: <after both review reconciliations and before acceptance>
  reason: <specific resolution basis>
  criterion_resolutions:
    - criterion_id: criterion_<slug>
      requirement: <exact current requirement>
      evidence_ids: [<passing evidence bound to this candidate and criterion>]
```

Resolution rows cover the exact adverse criterion set. A clean review cannot be discarded as `superseded`, and an unresolved or weakly bound supersession holds acceptance.

Every cited resolution evidence row is passing and bound to the exact candidate and criterion, and its parsed `observed_at` is strictly earlier than `resolved_at`. Evidence observed at the resolution instant or later cannot causally support that resolution.

For an effective adverse review of a candidate that explicitly records `review_required: false`, the coordinator may retain the review as effective and use this alternative adjudication record instead of superseding it:

```yaml
optional_adjudication:
  adjudicated_by: <canonical coordinator>
  adjudicated_at: <strictly after review reconciliation and before acceptance>
  reason: <specific cross-task authority/materiality basis>
  criterion_adjudications:
    - criterion_id: criterion_<slug>
      requirement: <exact current requirement>
      disposition: false_positive | nonmaterial | outside_supported_scope | confirmed_material
      rationale: <specific in-scope reasoning>
      evidence_ids: [<passing evidence bound to this candidate and criterion>]
```

Rows cover every adverse criterion exactly once. Each cited evidence row passes, binds the same candidate and criterion, and was observed strictly before adjudication. Only `false_positive`, `nonmaterial`, and `outside_supported_scope` clear an optional adverse criterion; `confirmed_material` holds acceptance. This path cannot cure an invalid review, discard a clean review, or satisfy a required independent-review gate. It exists because real coordination exposed two equal risks: ignoring a returned adverse review enables review shopping, while making every optional adverse statement a permanent veto transfers the coordinator's cross-task scope and materiality authority to a reviewer. Evidence-bound coordinator adjudication avoids both. The later-clean-review supersession route remains available.

Require each finding to state a current `criterion_id`, the exact matching current requirement text, expected result, actual result, location, evidence, impact, and requested delta. Unknown criteria and missing or stale requirement text fail the review record. Accept changes only for concrete impact within the supported current scope. Treat the reviewer as a challenger, not a new authority.

## 11. Requirement Changes and Supersession

When requirements or authoritative inputs change:

1. classify the message as replace, add, or status/question;
2. create a new batch if effective input or intended result changed;
3. identify the new authority and what it replaces;
4. find tasks and candidates that consume the replaced authority;
5. traverse their dependent descendants;
6. mark conflicting attempts and candidates `superseded`;
7. interrupt or redirect active affected work when possible;
8. classify late affected output as stale evidence;
9. preserve unaffected candidates and evidence;
10. rebuild the brief at the earliest affected stage.

Do not delete superseded history or move the current-result pointer before replacement output passes.

Persist supersession only at run level:

```yaml
supersedes:
  - subject_id: <existing task, attempt, candidate, or declared authority identity>
    replacement_id: <existing unambiguous replacement identity>
    reason: <specific reason>
```

Each edge uses exactly these fields. Subject and replacement resolve uniquely across the task, attempt, candidate, and declared-authority domains and remain within the same identity domain; attempt edges also remain within one `task_id`; subjects have at most one outgoing edge; the graph is acyclic. Candidate edges require comparable canonical `observed_at` values with strict subject-before-replacement order. A noncurrent delivered attempt is accounted for only when it is in the current attempt's complete acyclic `retry_of` ancestry or its run-level supersession path terminates at the current attempt or one of that ancestry's attempts and the old attempt is reconciled. Every attempt on that supersession path is delivered, belongs to the same task, and has a delivery time increasing strictly along the path. A returned superseded attempt needs coordinator return reconciliation; a delivered attempt without a return needs recorded uncertainty and reconciliation. `status: superseded` alone never discharges work, while explicit per-attempt reconciliation does. An edge to an unrelated, undelivered, cross-task, or earlier identity does not hide work. Superseding an authority stales tasks and candidates that name it in `authority_identities`, their current pointers, explicit consumers, and dependent descendants. Superseding an old attempt or candidate does not stale its producer task when that task's current attempt and candidate are the accepted replacement, but consumers of a stale identity remain stale.

## 12. Recovery, Retry, and Closure

Retain this compact recovery capsule before long pauses, handoffs, compaction-sensitive continuations, or tool interruptions when native history is insufficient:

```yaml
objective: <current TODO outcome>
latest_constraints: []
binding_id: binding_v001
batch_id: batch_NNNN
run_id: run_NNNN
current_candidates: []
verified_evidence: []
decisions: []
succeeded_work: []
pending_work: []
superseded_work: []
active_work: []
blocker: <specific blocker or null>
next_action: <one exact action>
```

On resume, re-read the binding and latest requirement, restore known worker task identities and wait cursors, verify candidate identities, inspect actual task and command state when needed, distinguish delivered, running, returned, and verified work, and reconcile records with real artifacts. A missing expected return event is uncertain transport state, not proof that the worker failed or never produced a candidate.

Retry only when the attempt adds evidence, narrows the failure, changes the approach, or resumes a known interruption. Use no universal retry count. Stop when the same blocker repeats without new information and no safe in-scope alternative remains.

Before closure, enumerate active internal agents, user-visible tasks, commands, monitors, automations, worktrees, and external operations. Wait for, cancel, supersede, or report each one. Reconcile every noncurrent delivered attempt through complete retry ancestry or valid run-level supersession, and block closure on any effective delivered attempt that neither returned nor has documented reconciliation. Map every TODO and follow-up to a current status and evidence; verify joined outputs against current upstream candidates; report outputs, evidence, risk, blockers, and exclusions.

For generic persisted results, `latest_result` has exactly `schema_version`, `run_id`, `result_manifest`, `candidate_id`, and `source_digest`. Schema version is the integer `1` rather than a boolean; the other four values are either all null or all nonempty strings. The canonical null pointer retains all five keys with those four null values. A non-null candidate requires all four identity/pointer strings, the approved project root, a `sha256` candidate identity, and read-only verification of the result manifest, source-manifest digest, actual output digests, candidate-to-output digest equality, and declared copy parity. Malformed pointers fail before path or artifact interpretation. Only the canonical fully null pointer may omit the root. This Skill does not implement an alternate existing-workflow validator authority inside the generic JSON auditor.

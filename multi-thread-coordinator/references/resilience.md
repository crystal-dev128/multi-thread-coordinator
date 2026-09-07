# Review, Recovery, and Concurrency Safety

Use this reference only when work needs independent review, interruption recovery, a retry, supersession impact analysis, concurrent mutation, or a closure audit. Native task and command state remains the execution authority. Persist the minimum records below only when the Workspace Binding permits it and native history is insufficient.

The procedures do not provide exactly-once delivery, a lock service, a task board, or permission transfer. They make uncertain state visible and keep unsafe work held until the coordinator reconciles real evidence.

## Contents

1. Separate transport from acceptance
2. Record attempts and audited retries
3. Use a fresh reviewer
4. Propagate supersession
5. Recover after interruption
6. Protect shared writes
7. Audit persisted coordination state
8. Close only after active-work reconciliation
9. Stage 7 acceptance probes

## 1. Separate Transport From Acceptance

Keep task status in the agreed vocabulary: `pending`, `running`, `needs_input`, `blocked`, `succeeded`, `failed`, or `superseded`.

Record delivery, return, and acceptance as observations on an attempt, not as additional task statuses:

```yaml
attempt_id: attempt_001
task_id: task_prepare
owner: <native task or agent identity>
skill_commit_at_dispatch: <immutable installed Skill revision>
delivered_at: <timestamp or null>
returned_at: <timestamp or null>
accepted_at: <timestamp or null>
accepted_by: <canonical coordinator identity or null>
candidate_id: <candidate id or null>
return_mode: automatic | task_event | notify | push | manual
return_contract_version: automatic_v1 | task_event_v1 | notify_v1 | push_v1 | manual_v1
worker_thread_id: <created native task id for every delivered user-visible/worktree mode>
worker_host_id: <native host id for every delivered user-visible/worktree mode>
first_wait_at: <timestamp or null>
return_cursor: <latest native wait cursor or null>
return_armed_at: <timestamp or null>
return_event_received_at: <timestamp or null>
return_reconciled_at: <timestamp or null>
return_reconciled_by: <coordinator identity or null>
# task_event-only: first_wait_at, return_cursor
# notify-only: return_armed_at
# task_event, notify, push, and manual: worker_thread_id, worker_host_id
# push-only:
push_target: {task_id: <exact coordinator task>, host_id: <exact coordinator host>}
push_capability: {name: <native send>, verified_at: <timestamp>, evidence: []}
push_preflight_at: <timestamp>
# manual-only: manual_disclosed_at, manual_disclosure_evidence
# automatic-only:
automatic_return: {surface: internal_subagent, parent_coordinator_id: <id>, worker_native_id: <id>}
uncertain_at: <timestamp or null>
reconciled_at: <timestamp or null>
retry_of: <attempt id or null>
retry_reason: <concrete reason or null>
pre_retry_audit: <record or null>
```

Apply these meanings:

- `delivered_at` proves only that the transport accepted the request;
- `returned_at` proves only that a response or artifact was associated with the attempt;
- `accepted_at` is recorded only after the coordinator verifies the exact candidate and evidence, with `accepted_by` equal to the run's canonical `coordinator_id`;
- `return_event_received_at` records the native completion, attention, automatic-return, or verified-push event associated with the attempt; it does not prove acceptance;
- `return_reconciled_at` records that the coordinator correlated and inspected the returned result or blocker; no later material dispatch or acceptance may pass through an earlier unreconciled return;
- `uncertain_at` records an ambiguous timeout, tool failure, or unknown side-effect state;
- `reconciled_at` records when native state and candidate locations were inspected and the uncertainty was resolved.

A task may be `running` after delivery or return. It becomes `succeeded` only when its current attempt has an accepted candidate and primary evidence. Never infer acceptance from a worker's completion wording.

Normal user-visible execution is event-driven, under whichever event contract the host supports; resolve that from [hosts.md](hosts.md). Every delivered `task_event`, `notify`, `push`, and `manual` attempt, including preserved history, records its native worker host/thread pair. Task-event also records its first native wait, notify instead records `return_armed_at`, the moment the host's notification path for that exact worker became live, and neither is `running` until its own fields exist. A notify attempt has no resumable wait, so it carries no `return_cursor` and never carries `contract_migration`. Use the native completion-or-attention wait rather than periodic task reads. Current-contract attempts allow only common lifecycle fields plus the exact fields for their mode. Delivered task-event, push, and manual attempts use only `user_visible_task` or `worktree`; automatic uses only `internal_subagent`. A non-null coordinator return target is an exact task/host pair distinct from every delivered visible/worktree producer pair, across task-event, push, and manual history, and every required reviewer pair. Push capability verification precedes preflight, whose target exactly matches that run target, and preflight precedes delivery. Manual disclosure and evidence precede delivery. Automatic return binds an internal subagent's native parent/worker identity, keeps worker and coordinator parent distinct, and cannot label a user-visible task. Delivery precedes first wait or applicable return evidence, association precedes coordinator reconciliation, and reconciliation precedes acceptance or unrelated later material dispatch. One native task-event response may establish `return_event_received_at <= returned_at`; all other causal boundaries stay strict, including push event/association. A bounded wait timeout does not make the attempt uncertain by itself; it means only that no event arrived during that wait. If event transport fails ambiguously, or execution resumes after interruption without the expected return, inspect the worker task and candidate locations once as recovery evidence before deciding whether to resume waiting, continue, retry, or report uncertainty.

## 2. Record Attempts and Audited Retries

Create a new attempt for rework, resume, or retry. Preserve the prior attempt. A retry must name `retry_of`, state a concrete `retry_reason`, and contain:

```yaml
pre_retry_audit:
  native_state_checked: true
  candidate_locations_checked: true
  side_effects_disposition: none | reused | superseded | isolated
  evidence:
    - <native state, file, candidate, or command observation>
```

Use the disposition as follows:

- `none`: inspection found no relevant side effect;
- `reused`: a valid existing side effect or candidate will be continued rather than duplicated;
- `superseded`: a prior side effect is retained as stale history and replacement work has a new identity;
- `isolated`: uncertain prior effects remain physically or logically separated from the new attempt.

Do not create the retry until the audit is complete. A delivered retry records a delivered direct predecessor, and its delivery is strictly later than the predecessor's delivery. If that predecessor records `uncertain_at` and `reconciled_at`, parsed reconciliation is strictly earlier than retry delivery for every running or terminal status; a pre-retry audit cannot override equality, reversal, or invalid timestamps. Reversed or undelivered ancestry cannot hide a later sibling. The task's dependency, consumption, and authority declarations remain the applicable immutable snapshot for its current attempt and every retry ancestor, so each ancestor must independently follow prerequisite acceptance chronology. A different attempt ID or pre-retry audit does not erase an earlier illegal dispatch. Retry only when the new attempt adds evidence, narrows the failure, changes the approach, or resumes a known interruption.

Persisted current-contract runs use exact integer `schema_version: 2` plus immutable-by-contract `skill_commit_at_creation`, creation-time `return_contract_version`, canonical `coordinator_id`, and exact `schema_provenance`; schema discriminators never use booleans. They explicitly retain all eight record lists—`chains`, `tasks`, `attempts`, `candidates`, `evidence`, `reviews`, `supersedes`, and `active_work`—even when empty, and every v2 candidate explicitly records boolean `review_required`. Missing-as-empty compatibility is limited to legacy schema v1. Native creation stores a trusted-writer attestation over the empty v2 creation snapshot and establishment time; schema migration creates a new v2 run whose attestation compares the supplied trusted v1 source record and digest. `fail_closed_v2` is structural conformance over persisted attestations: the auditor reports `provenance_trust_model: trusted_persisted_attestation` and `cryptographic_actor_or_creation_proof: false`, and it cannot detect a coordinated rewrite/backfill of the complete record. Preserve schema-version-1 runs as legacy-readable history and use explicit new-run migration by contract. To move an in-flight `push_v1` task to `task_event_v1`, retain the push attempt and create one new retry transition with the migration record defined in [protocol.md](protocol.md). Validate every actual direct transition independently of current pointer or task status, reject more than one transition per task, and compare unresolved pushes at that transition's own delivery: it directly retries the latest such same-task push and its acyclic ancestry covers every earlier unresolved push. Later ordinary task-event retries reuse the validated transition through ancestry rather than repeating migration or directly retrying the original push. Require `source delivered_at <= migrated_at < replacement delivered_at < first_wait_at`, and never rewrite the earlier attempt as task-event work.

## 3. Use a Fresh Reviewer

Set `review_required: true` on a candidate only when the risk rule in `SKILL.md` requires independence. Producer, reviewer, and canonical coordinator must be pairwise distinct. The coordinator owns the neutral packet, candidate admission, return reconciliation, finding adjudication, acceptance, and closure; the fresh reviewer owns detailed assigned re-performance. Coordinator self-review cannot satisfy a required independent review.

Use the complete neutral packet contract in [protocol.md](protocol.md). For a current-contract persisted run, record the returned review as:

```yaml
review_id: review_001
candidate_id: candidate_report_001
reviewer: <identity different from producer and coordinator>
review_status: effective | superseded
read_only: true
packet: <digest-bound neutral review packet>
admitted_at: <after producer return reconciliation>
delivered_at: <after admission>
worker_thread_id: <created reviewer task id>
worker_host_id: <reviewer host id>
first_wait_at: <timestamp>
return_cursor: <latest native wait cursor>
completed_at: <timestamp>
return_event_received_at: <timestamp>
returned_at: <timestamp>
reconciled_at: <later timestamp>
reconciled_by: <canonical coordinator identity>
reviewer_actions:
  mutated_candidate: false
  waived_criteria: false
  unlocked_dependents: false
  updated_current_pointer: false
  accepted_candidate: false
criterion_results:
  - criterion_id: criterion_<slug>
    requirement: <exact current requirement>
    result: pass
    evidence: []
open_material_findings: []
resolution: null | <coordinator-owned supersession record from protocol.md>
optional_adjudication: null | <coordinator-owned optional-review record from protocol.md>
```

Give the reviewer the exact candidate, current requirements, raw sources and evidence, permitted read scope, prohibited actions, lineage, protected behavior, and task-event return contract. Do not present the implementer's verdict, the coordinator's preferred conclusion, or unsupported narrative as fact.

Each material finding must identify a current criterion ID, its exact current requirement text, expected result, observed result, location, evidence, impact, and requested delta. The digest-bound packet uses exact nested field allowlists, iterative traversal, a maximum depth of 64, and verdict-bias exclusion; over-depth state fails before digest canonicalization so malformed persisted input cannot crash coordination audit. The review task's native host/thread pair must differ from production. Producer reconciliation/admission, admission/delivery, delivery/first wait, returned/reconciled, reconciliation/resolution, and resolution/acceptance follow strict causal order. One atomic native response may record `completed_at <= return_event_received_at <= returned_at`. Review delivery also participates in the return-first barrier. Send an authorized correction to the original owner first when practical. Preserve the finding and changed candidate identities.

Every effective review gates acceptance, whether review was required or optional: one clean review does not mask another effective failed criterion or open material finding. An adverse review may become `superseded` only through a later effective clean review on the same candidate plus a coordinator-owned, exact adverse-criterion resolution whose cited evidence is passing, bound to that candidate and criterion, and observed strictly before resolution. For `review_required: false` only, the coordinator may instead adjudicate every adverse criterion exactly once as `false_positive`, `nonmaterial`, `outside_supported_scope`, or `confirmed_material`, with passing same-candidate/same-criterion evidence observed strictly before adjudication and adjudication strictly between review reconciliation and acceptance. The first three dispositions clear that optional adverse criterion; confirmed material, missing coverage, invalid review structure, or required-review use holds the gate. Clean reviews cannot be discarded. This preserves anti-review-shopping while avoiding a de facto optional-review veto; the coordinator owns cross-task authority and in-scope materiality. A required review passes only when at least one effective fresh read-only reviewer covers every current criterion with evidence, every other effective adverse review is resolved through the permitted supersession route, every return is reconciled strictly before acceptance, and the attempt records the coordinator in `accepted_by`.

## 4. Propagate Supersession

Use a compact supersession record:

```yaml
subject_id: <authority, task, attempt, or candidate made stale>
replacement_id: <new authority or candidate identity>
reason: <specific changed input, requirement, or candidate>
```

Starting from every `subject_id`, including an authority named directly in task or candidate `authority_identities`, determine the affected closure:

1. candidates that consume a stale authority or candidate;
2. the task that produced a stale candidate;
3. tasks that consume a stale identity;
4. tasks that depend on a stale task;
5. candidates produced by affected tasks;
6. evidence and reviews bound to affected candidates;
7. joins and later descendants that consume any affected result.

Mark every affected task `superseded`, interrupt or redirect affected active work where possible, and treat late output as stale. Preserve unaffected siblings. Do not delete history or move a current-result pointer until replacement work passes.

The read-only audit script computes this closure for persisted runs and rejects a current-result pointer to any stale candidate.

## 5. Recover After Interruption

How much the capsule carries depends on the host. Where durable workers outlive the session, native history carries most of the interruption and the capsule reconciles what it cannot. Where workers are scoped to the session and end with it, no running worker survives the interruption at all: the capsule is then the only durable record of what was dispatched, so persist it earlier and keep it current rather than relying on native history. Resolve which case applies from [hosts.md](hosts.md).

When native history cannot safely carry an interruption, persist `recovery.json` beside the run record:

```yaml
schema_version: 1
binding_id: binding_v001
batch_id: batch_NNNN
run_id: run_NNNN
objective: <current effective outcome>
latest_constraints: []
current_candidates: []
verified_evidence: []
decisions: []
succeeded_work: []
pending_work: []
superseded_work: []
active_work: []
uncertain_attempts: []
blocker: null
next_action: <one exact reconciliation or continuation action>
```

On resume:

1. re-read the current user requirement and Workspace Binding;
2. restore each running user-visible task's worker identity, such as `threadId` and `hostId` or an agent name and id, together with its return mode and latest event cursor, then resume the host's return path when it remains valid. Treat a running worker as uncertain when the resumed host no longer exposes the capabilities the recorded return mode assumed;
3. inspect native tasks, commands, applications, worktrees, and external operations when the wait cannot be safely resumed or reconciliation is otherwise required;
4. inspect candidate locations and immutable identities;
5. reconcile delivered, returned, accepted, and uncertain attempts;
6. update supersession impact before accepting late output;
7. record `reconciled_at` only after uncertainty is resolved;
8. audit the run before resuming or retrying mutation.

While an attempt remains uncertain, list it in `uncertain_attempts` and retain its active owner in the recovery capsule. Do not replace uncertainty with a guessed failure or success.

Refresh `next_action` after every reconciliation or audit. It must name the action that actually remains, or explicitly state that no mutation is pending; do not leave a completed audit or reporting step presented as future work.

## 6. Protect Shared Writes

Represent only currently active mutation owners in `active_work`:

```yaml
active_id: active_001
kind: task | command | monitor | automation | worktree | external_operation
owner: <native identity>
task_id: <task id or null>
attempt_id: <attempt id or null>
writes:
  - <normalized path or mutable authority token>
isolation_key: <verified isolation identity or null>
```

Before dispatch and whenever the active set changes:

1. normalize each filesystem claim with host-independent POSIX lexical rules after slash conversion, while recognizing POSIX roots, Windows drive roots, and UNC-style absolute claims; when `project_root` is supplied, resolve relative claims against that lexical root and reject absolute claims outside it; without a root, fail closed if relative and absolute filesystem claims coexist; collapse repeated separators, `.` and safe `..`, reject drive-relative and root-escaping forms, and preserve exact opaque authority tokens;
2. treat equal, ancestor, and descendant claims as overlapping;
3. serialize overlapping mutation by keeping only one owner active; or
4. isolate the owners in verified separate worktrees, output namespaces, application sessions, or workflow-owned partitions and give each a distinct `isolation_key`;
5. keep shared inputs read-only and stable for the relevant attempts;
6. re-audit before a join or pointer update.

Do not invent an isolation key to silence a conflict. Verify the physical or workflow separation first. An attempt-bound row identifies the attempt's own task, and its `owner` exactly equals `attempt.owner`. At most one non-null `active_work` row may claim a given `(task_id, attempt_id)`, regardless of disjoint paths or different isolation labels. Do not record a task and its nested command as two mutation owners for the same operation; record the accountable active owner. Distinct verified isolation remains available only for genuinely distinct accountable attempts or owners.

## 7. Audit Persisted Coordination State

For a persisted generic run, execute:

```text
python <skill-dir>/scripts/audit_coordination_state.py --run <run.json> --latest-result <latest_result.json> --project-root <approved-project-root> --recovery <recovery.json> --require-current-contract
```

Add `--legacy-run <trusted-preserved-v1-run.json>` when `schema_provenance.mode` is `migrated_from_v1`. Omit other optional files when they do not exist and the corresponding condition is absent. A non-null generic result requires `--project-root` for manifest, source-digest, output, and parity verification. A null or absent result may still supply the root to canonicalize active relative and absolute write claims into one namespace. The audit is read-only. It checks:

- explicit presence and list typing for every canonical v2 run record collection, exact v2 task fields, required typed candidate artifact descriptors and boolean `review_required`, task/attempt/candidate/evidence/review references, and active-work owner/single-attempt accountability, including exact bidirectional attempt/candidate production pointers;
- strict delivery/return/reconciliation/acceptance ordering and coordinator-owned `accepted_by`;
- structural v2 creation or new-run v1-migration attestations under the explicit trusted-persisted trust model, mode-exact return evidence and surface compatibility, complete acyclic same-task push-to-task-event migration, first-wait readiness, and return-first reconciliation including review dispatch;
- exact task/candidate criteria and passing candidate/authority-bound evidence coverage behind candidates and `succeeded` tasks, with each observer restricted to the coordinator or an effective structurally qualifying reviewer on that candidate;
- required pairwise-distinct hybrid-review ownership and distinct native producer/reviewer tasks, depth-bounded iterative packet neutrality and exact nested schema, packet digest and current identity, exact criterion and finding requirement coverage, admission/dispatch chronology, all-effective-review aggregation, evidence-bound supersession or optional adjudication, reviewer non-mutation, native return, and coordinator reconciliation;
- coordinator-accepted dependency and consumed-candidate causality before each current and retry-ancestor delivery using immutable task declarations, with duplicate rejection and unique per-consumer candidate-or-declared-authority resolution, plus current-attempt pointers for all non-superseded delivered work;
- retry provenance, strict predecessor-delivery and post-uncertainty-reconciliation chronology across all statuses, complete ancestry, and pre-retry side-effect inspection;
- exact acyclic same-domain graphs with same-task attempt supersession, strict candidate `observed_at` chronology, complete hidden-attempt accounting, authority-binding stale propagation, supersession reconciliation, closure holds on unresolved delivered work, and stale current-result pointers;
- staged-chain status, dependency, and one-current-stage unlock invariants;
- unresolved uncertain attempts against the recovery capsule;
- overlapping host-independent lexically canonicalized active writes, project-root resolution, mixed relative/absolute ambiguity, and verified isolation identities;
- the exact typed latest-result pointer, result manifest, source-manifest digest, actual output digests, published candidate `sha256` equality to a verified output, and declared user-copy parity when `--project-root` is supplied.

Treat audit errors as holds on the relevant gate. Reconcile the actual task or artifact state; do not edit a record merely to remove an error. The script is not an authority and does not replace project-specific validation.

Existing workflows may use their own authoritative records instead of this JSON shape. Apply the same invariants through their native status, writer, recovery, and validation surfaces; do not create a parallel run ledger solely to use the script.

Omit `--require-current-contract` only when reading historical schema-version-1 state. A legacy-readable pass does not claim structural `fail_closed_v2` conformance.

## 8. Close Only After Active-Work Reconciliation

For persisted generic coordination, add `--closure` before reporting the effective TODO complete:

```text
python <skill-dir>/scripts/audit_coordination_state.py --run <run.json> --latest-result <latest_result.json> --project-root <approved-project-root> --closure --require-current-contract
```

Closure requires:

- no unresolved uncertain attempt;
- no effective delivered attempt without a return or documented retry/supersession reconciliation; task status `superseded` alone is not reconciliation;
- no active mutation owner;
- every effective task is `succeeded` or `superseded`;
- every succeeded task has an accepted current candidate and evidence;
- no stale candidate is current;
- every required independent review passes;
- every delivered return is coordinator-reconciled before acceptance and closure;
- every retry has a complete pre-retry audit and strictly causal delivered ancestry;
- every staged chain has no unlocked or non-terminal effective stage;
- the latest-result manifest and actual source/output identities pass when a current result exists.

Separately inspect native surfaces for work that was not persisted. Wait for, cancel, supersede, or report every active task, command, monitor, automation, worktree, and external operation.

## 9. Stage 7 Acceptance Probes

Use synthetic records and verify all of these before treating Stage 7 as implemented:

- A delivered or returned attempt cannot make its task `succeeded` without accepted candidate evidence.
- A candidate requiring independent review cannot pass when the reviewer is the producing owner, the review mutates the candidate, or material findings remain open.
- A required review cannot pass when producer equals coordinator, `accepted_by` is not the coordinator, a nested packet field introduces verdict bias, or a finding does not bind an exact current criterion and requirement.
- A coordinator cannot substitute its own detailed review for a required fresh reviewer; a stale packet, omitted criterion, missing review return, or missing coordinator reconciliation holds acceptance.
- A reviewer cannot reuse the producer's native host/thread pair; every delivered task-event, push, and manual producer also has a native pair, and review admission or delivery cannot predate producer return reconciliation.
- One clean review cannot mask any effective failed criterion or material finding; supersession passes only with a later effective clean review and exact coordinator-owned evidence-bound resolution, while an optional adverse review clears only through exact evidence-bound coordinator adjudication of every adverse criterion.
- Review-resolution evidence must be observed strictly before `resolved_at`; automatic return rejects a worker identity equal to its coordinator parent; schema-version discriminators reject booleans.
- A task-event attempt cannot be `running` without a ready worker identity and first native wait, and a newer material dispatch cannot pass an earlier unreconciled return.
- Equal causal timestamps fail at delivery/wait, push event/association, returned/reconciled, review admission/dispatch, reconciliation/resolution, resolution/acceptance, later dispatch, and acceptance boundaries. Only atomic native observation permits task-event `return_event_received_at <= returned_at` and review `completed_at <= return_event_received_at <= returned_at`.
- Push rejects an arbitrary or unverified target, manual rejects missing or late disclosure, and automatic rejects a user-visible surface or missing native identity.
- Current task/candidate criteria and passing evidence use exact nonempty unique coverage; missing, extra, duplicate, stale, failed, or waived evidence fails.
- Every delivered effective dependent starts strictly after its prerequisite's current coordinator acceptance.
- A v1 run remains readable; structurally incomplete or inconsistent relabel/backfill records fail, while honest native-v2 and explicit new-run migration attestations pass. The report states that a coordinated complete rewrite is outside its proof model.
- A legacy push attempt cannot be represented as native task-event work in the structural contract; migration requires one preserved direct source transition, validation against unresolved pushes at transition delivery, complete acyclic same-task lineage, current version provenance, and reconciliation evidence. Later task-event retries reuse that transition through ancestry.
- Missing or cross-mode `owner_surface` fails every delivered attempt; task-event, push, and manual allow user-visible/worktree task surfaces, while automatic allows only internal subagents.
- Task and candidate `consumes` reject duplicates, unknowns, and candidate/authority ambiguity; every consumed candidate gates each current/retry-ancestor delivery even without `depends_on`, and delivered failed/blocked/needs-input tasks retain their current attempt pointer.
- An ambiguous attempt requires a matching recovery capsule until real state is reconciled.
- A retry without prior-attempt identity, reason, native-state inspection, candidate-location inspection, side-effect disposition, and evidence is rejected.
- A retry of an uncertain predecessor fails when that predecessor's parsed reconciliation is equal to or later than retry delivery, across running and terminal task statuses.
- A non-null coordinator return target rejects collision with any delivered task-event, push, or manual producer and any required reviewer, including preserved mixed-mode history; only the complete native host/task pair establishes separation.
- A v2 candidate rejects missing, empty, boolean, or invented `kind`, `location`, `scope`, or canonical `observed_at`, and evidence rejects coordinator-unrelated, producer, stale-reviewer, and nonqualifying-reviewer observers.
- A v2 task rejects local `supersedes` and unsupported extension keys; `run.supersedes` is the only supersession representation.
- Run-level `supersedes` is the sole supersession authority; its exact same-domain graph rejects unknowns, ambiguity, multiple replacements, cycles, cross-task attempt edges, noncausal bridges, and non-forward candidate chronology. Superseding an authority binding or other upstream identity makes bound, consuming, and dependent tasks stale while preserving an old producer task whose current accepted replacement is live.
- `latest_result.json` cannot point to a stale candidate.
- `latest_result.json` uses an exact five-key typed schema with integer (not boolean) version `1`; its other four fields are either all null or all nonempty strings. A non-null candidate requires matching run, manifest, source, and verified artifact identities plus a candidate `sha256` equal to an actual verified output.
- Overlapping active write claims fail after host-independent lexical normalization and project-root resolution unless only one owner is active or distinct verified isolation keys are recorded; mixed relative/absolute filesystem claims fail without a root.
- Attempt-bound active work rejects an owner different from `attempt.owner`, a missing or mismatched task binding, and a second row for the same task/attempt even when isolation labels differ; distinct accountable attempts remain isolatable.
- Closure fails while active mutation, uncertainty, unresolved delivered work, non-terminal effective tasks, missing evidence, stale pointers, or required review gaps remain.

These are deterministic state probes. Fresh-context behavioral forward testing remains Stage 8.

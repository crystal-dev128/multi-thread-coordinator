# Progressive Staged Execution

Use this procedure when one high-level task or one TODO item contains ambiguity, subjective judgment, material risk, or dependencies whose intermediate evidence should change later work. Decompose the outcome even when the user supplied only one task.

This procedure governs dependent chains. Independent modules may run in parallel, but each dependent chain exposes at most one current stage. Use `pending` plus a lock reason; do not add a `locked` work status.

## Contents

1. Recognize a staged task
2. Decompose one high-level task
3. Define a staged chain
4. Unlock only the current stage
5. Build the current-stage brief
6. Gate the current candidate
7. Pass and adapt the next stage
8. Fail and request concrete rework
9. Continue with the same owner
10. Pause for user input or a blocker
11. Handle changed authority
12. Report staged progress
13. Synthetic walkthroughs
14. Stage 5 acceptance probes

## 1. Recognize a Staged Task

Choose `staged` when any of these conditions holds:

- the cause, correct approach, or target scope is uncertain;
- the result depends on a source interpretation or business judgment;
- an intermediate artifact can materially change later instructions;
- later action would be costly, unsafe, or misleading if an early assumption is wrong;
- the user asks for diagnosis, design, implementation, and verification as one high-level task;
- several dependent transformations must preserve candidate identity and evidence.

Do not require multiple user-authored TODO items. Treat one request such as “improve this workflow” as an outcome that may need diagnosis, design, implementation, and verification stages.

If the action is already known, contained, low risk, and quickly verifiable, it does not need this Skill. Split independent modules from the staged chain only when they remain independent through acceptance and have safe writes.

## 2. Decompose One High-Level Task

Start from the decision boundaries, not from a preferred number of agents. Ask for each possible step:

1. Does this step produce a small artifact or conclusion that can be independently inspected?
2. Can that evidence change the scope, method, permission, or acceptance of later work?
3. Would starting the later work before this evidence passes create avoidable rework or risk?
4. Does the step need the same local context and owner as the next step?
5. Is any subproblem actually independent through acceptance and write-safe?

Create a stage when the first three answers justify a gate. Keep consecutive mechanical actions together when separating them adds no useful decision point. Split independent subproblems into parallel chains only when the fifth condition passes.

The number of user inputs, tasks, threads, and stages are different concepts:

- one user item may produce one dependent chain with several stages;
- one user item may contain several independent modules assigned to separate workers;
- several stages in one continuous chain normally reuse one worker or user-visible task;
- a new worker is not required merely because a new stage begins.

## 3. Define a Staged Chain

Maintain this minimal logical shape in native history unless persistence is required:

```yaml
chain_id: chain_<slug>
mode: staged
outcome: <high-level user outcome>
owner_surface: <continuing internal subagent or user-visible task>
unlocked_stage_id: stage_NNN | null
stage_outline:
  - stage_id: stage_NNN
    objective: <one small decision or artifact>
    depends_on: []
    consumes: []
    deliverable: <small candidate>
    acceptance: []
    status: pending | running | needs_input | blocked | succeeded | failed | superseded
    lock_reason: <unmet gate or null>
    current_candidate: <candidate reference or null>
```

Keep future stages as an outline containing only enough information to show dependency and purpose. Do not pre-dispatch them or freeze detailed briefs that assume an unknown intermediate result.

For a linear chain, set only the first stage's `lock_reason` to null. For a dependency graph, a pending stage becomes eligible only when every declared dependency is current and `succeeded`.

## 4. Unlock Only the Current Stage

Apply these rules per dependent chain:

1. Allow at most one `running` stage and one `unlocked_stage_id`.
2. Keep every dependent later stage `pending` with its unmet gate in `lock_reason`.
3. Unlock a stage only when its dependencies, inputs, permissions, writer rule, and evidence surface are current.
4. Create or rebuild the detailed brief only after the stage becomes eligible.
5. Clear `unlocked_stage_id` after a non-pass outcome until a valid rework or resume attempt is ready.
6. Unlock declared dependents only after the coordinator passes the exact current candidate.

Separate independent chains may each have one current stage and run concurrently when their mutable writes are safe. Do not interpret “one stage at a time” as a global ban on independent parallel work.

Task creation and stage unlocking are also separate. After the user selects a surface, continue a known chain by sending a follow-up to the same task or worker; do not create a new user-visible task for every stage.

## 5. Build the Current-Stage Brief

Build the brief from current authority and accepted predecessor candidates. Include:

```text
Chain and stage: <chain_id / stage_id>
Attempt: <attempt_id>
Stage purpose: <how this small result gates the outcome>
Objective: <one testable current-stage outcome>
Inputs: <authorities and exact succeeded predecessor candidates>
Allowed reads/writes/actions: <bounded surfaces>
Prohibited: <later-stage work, unrelated paths, publication, or other boundaries>
Deliverable: <one small artifact or conclusion>
Evidence required: <primary observations>
Acceptance: <observable criteria>
Coordinator: <actual native coordinator identity and routing target, or native parent>
Return: <mandatory native report on completion/failure/blockage/required input under handoffs.md; stage/attempt, disposition, paths, candidate identity, evidence, unresolved items, next action/owner>
Return mode: <automatic, task_event using the worker task ID/host, notify using the armed worker identity, verified push, or disclosed manual return>
Return event: <completed or needs_attention for task_event; result, needs_input, or blocked for push>
Stop when: <missing authority, unsafe write, business decision, or unmet prerequisite>
```

Mention future work only in one sentence explaining why the current stage matters. Explicitly prohibit implementation during a diagnosis stage, broad redesign during a bounded design stage, or integration before upstream gates pass.

Do not copy a brief drafted before its predecessor passed. Rebuild it so its inputs, objective, boundaries, and acceptance reflect the actual accepted evidence.

## 6. Gate the Current Candidate

When the owner returns automatically, a native worker task event arrives, or a preflighted worker push arrives, record only that the result was returned. Then:

1. resolve the exact candidate identity and bounded scope;
2. inspect primary evidence rather than the completion summary;
3. map every stage criterion to evidence tied to that candidate;
4. confirm permitted reads, writes, actions, and data boundaries were respected;
5. check that authority and predecessor identities are still current;
6. identify material findings, unresolved decisions, or active writers;
7. assign the precise pass or non-pass outcome.

Pass only when the exact candidate satisfies every criterion or an explicit user waiver covers a named criterion. A returned result, partial improvement, plausible explanation, or passing unrelated check does not pass the gate.

No `failed`, `needs_input`, `blocked`, or `superseded` stage unlocks a dependent stage.

## 7. Pass and Adapt the Next Stage

Apply [handoffs.md](handoffs.md) in the same active turn as the return. After a pass:

1. mark the current attempt and stage `succeeded`;
2. record the exact succeeded candidate and evidence;
3. clear `unlocked_stage_id` while recomputing eligibility;
4. compare the accepted evidence with assumptions in the future stage outline;
5. preserve unaffected later objectives and replace assumptions that the evidence disproved;
6. build the next eligible stage brief from the succeeded candidate and current authority;
7. set that stage as `unlocked_stage_id` only when all its gates pass;
8. send the next ready brief to the same worker and establish its host-appropriate return path without asking again for existing authorization;
9. tell the user what passed, what changed in the next step, and what remains held when that change is material.

A diagnosis or design worker returns its bounded report and yields; it must not idle indefinitely waiting for the coordinator inside that stage. The coordinator receives the report, inspects the actual files and source/output identities, and owns continuation. A stage pass is not completion of the overall request. If a real hold or user-directed pause prevents continuation, retain its reason, owner, and next action; do not end an in-turn return chain merely because the next brief has not yet been sent.

Use this compact adaptation record when useful:

```yaml
source_stage: stage_NNN
source_candidate: candidate_<slug>_<NNN>
observed_change: <accepted evidence that changed an assumption>
affected_future_stages: []
preserved: []
revised: []
next_brief_built_from: <authority and candidate identities>
```

This record explains the delta; it is not a new approval lifecycle. Do not rewrite succeeded history.

## 8. Fail and Request Concrete Rework

On a concrete unmet criterion, mark the attempt `failed` and keep the stage current but not unlocked for downstream progress. Return a rework request to the original owner first:

```text
Rework identity: <chain/stage/new attempt>
Failed candidate: <exact candidate identity>
Failed criterion: <one or more observable criteria>
Expected: <required behavior or artifact>
Observed: <actual behavior or artifact>
Evidence: <primary evidence location or result>
Impact: <why the gap matters to this stage or downstream work>
Requested delta: <smallest concrete correction>
Preserve: <accepted paths, behavior, findings, or evidence>
Rerun: <checks required on the new candidate>
Do not start: <dependent stages that remain locked>
```

Create a new `attempt_id` and require a new candidate identity after any modification. Retain the failed attempt and its evidence. Do not relabel the old candidate as repaired.

Avoid vague instructions such as “try again,” “improve quality,” or “review carefully.” Name the difference the next attempt must close.

## 9. Continue With the Same Owner

Reuse the original internal subagent or user-visible task when its context remains valid and it has the necessary capability. Send the next-stage or rework brief as a correlated follow-up rather than opening another thread, then establish a fresh return contract for the new attempt. Use the host's resume capability, so the owner keeps the context it already built: a correlated follow-up on the same thread, or a message addressed to the same worker by name. Creating a new worker instead discards that context and makes it re-derive the brief, which is a cost to weigh rather than a neutral choice. For a user-visible task, use the host contract: under `task_event`, wait again on the same worker identity, such as its `threadId` and `hostId`, and reuse the latest cursor only within the attempt to which it belongs; under `notify`, arm the same worker’s next attempt and resume from its notification. The coordinator continues to own the gate rather than taking over the worker's material production. It resumes from native return events and does not use periodic task reads for progress.

Change owner only when:

- the original owner lacks a required capability or permission;
- the same evidenced failure repeats without meaningful progress;
- the owner is unavailable or its native state cannot be safely resumed;
- contaminated context creates material review risk;
- an independent reviewer is required.

When changing owner, give the replacement current authority, exact candidates, raw evidence, and the bounded current objective. Do not copy the prior owner's conclusions as established facts.

## 10. Pause for User Input or a Blocker

Use `needs_input` for one concrete business judgment, permission, authority, or required input. State:

- the exact question;
- why the current gate cannot be evaluated without it;
- which stage is paused;
- which downstream work remains locked;
- what safe work, if any, can continue independently.

After the user answers, create a new attempt for the same current stage when the governing batch remains current. Create a new batch and run impact analysis when the answer changes authoritative input or the intended result.

Use `blocked` only after safe in-scope alternatives are exhausted and progress requires an external state change or new authority. Never use a worker waiting idly as a substitute for asking the coordinator or user.

## 11. Handle Changed Authority

When a user replaces input or changes the intended result during a staged chain:

1. identify the changed authority and create the appropriate new batch;
2. find the earliest stage that consumed it;
3. mark conflicting current and succeeded candidates plus affected descendants `superseded`;
4. stop or redirect affected active attempts where possible;
5. preserve unaffected stages and evidence;
6. rebuild from the earliest affected stage;
7. keep the current-result pointer on the prior usable result until replacement work passes.

Treat late output from superseded attempts as stale evidence. It cannot reopen or pass a gate without an explicit current attempt and revalidation.

## 12. Report Staged Progress

Give concise updates at meaningful gates:

```text
Passed: <stage, exact candidate, and primary evidence>
Current: <unlocked stage and identified attempt>
Rework: <failed criterion and requested delta>
Held: <dependent stages and their lock reason>
Adapted next step: <what accepted evidence changed>
Needs input / blocked: <one concrete issue>
```

Omit empty categories. Do not repeatedly report unchanged pending stages. Do not describe a stage as completed when only its worker response has returned.

## 13. Synthetic Walkthroughs

### One ambiguous high-level task

Request: improve a synthetic file-import workflow whose failure cause is unknown.

Decompose one user task into:

1. `stage_001` — reproduce and diagnose the cause with evidence;
2. `stage_002` — design the smallest correction from the accepted diagnosis;
3. `stage_003` — implement only the accepted design;
4. `stage_004` — verify the corrected workflow and protected behavior.

If the first attempt returns only “the parser is wrong” without reproduction evidence, mark it `failed`. Keep stages 002–004 `pending` with `stage_001 acceptance` as their lock reason. Return the missing-reproduction difference to the same owner as a new attempt.

If the accepted diagnosis shows a delimiter configuration mismatch rather than a parser defect, rebuild stage 002 around the configuration boundary. Do not reuse a prewritten parser-rewrite brief.

### Dependency-heavy transformation

Request: transform a synthetic dataset and produce a summary from the accepted transformed output.

Use:

1. `stage_001` — identify and validate source scope;
2. `stage_002` — transform the accepted source candidate;
3. `stage_003` — summarize the exact accepted transformed candidate.

If stage 002 evidence shows duplicate records, reject that attempt and keep stage 003 locked. Send the exact duplicate evidence and requested correction to the same owner. After a corrected stage 002 candidate passes, build stage 003 with the new digest, row scope, and accepted coverage rather than the failed candidate's values.

## 14. Stage 5 Acceptance Probes

Verify all of these before treating progressive execution as implemented:

- A single high-level user task can be decomposed into stages or independent modules without requiring a prewritten TODO list.
- A dependent chain has no more than one unlocked or running stage.
- Every later stage remains `pending` with a concrete lock reason until its dependencies pass.
- A returned result is gated against the exact candidate and primary evidence.
- A rejected stage unlocks nothing downstream.
- Rework names expected, observed, evidence, impact, requested delta, protected behavior, and checks to rerun.
- Rework returns to the same owner first when capability and context remain valid.
- A changed candidate receives a new attempt and candidate identity.
- Accepted intermediate evidence can revise the next stage's objective, scope, inputs, or acceptance.
- The next detailed brief is rebuilt after the predecessor passes and identifies the accepted predecessor candidate.
- The coordinator recommends a durable user-visible task for a material staged chain and an internal subagent for a short helper, then obtains one consolidated surface choice when the user has not already decided.
- Continuous stages reuse the selected worker rather than creating a new user-visible task per stage; independent modules may use separate workers.
- Each user-visible stage returns through a native completion-or-attention event tied to the created worker task identity by default; the coordinator then gates the candidate and sends the next stage or rework.
- A next-stage or rework follow-up establishes a fresh task-event wait or verified notify arming for the same worker, according to observed host capabilities; verified push is only a fallback, and manual return is disclosed before dispatch.
- Host-appropriate native event continuation (in-turn waiting or verified wake notification) is the normal mechanism; bounded native-state reads are reserved for recovery, missing evidence, or a requested status check.
- Stage reports distinguish returned, accepted, rework, held, needs-input, blocked, and superseded work without adding new lifecycle statuses.

Tabletop probes establish protocol coverage only. Use fresh-context forward tests in the designated roadmap stage before claiming general behavioral validation.

# Return, Act, and Deliver

Apply this contract to every producer and reviewer, including internal subagents. A worker return and a passing review are intermediate events. The coordinator owns follow-through until the requested result reaches the user or a concrete hold is reported.

## Before Dispatch

Keep the request, actual producer/reviewer identity, current stage, expected return path, next action, acceptance state, and user-delivery state in native task history. Preserve them through context handoffs; do not create a second ledger. Name the exact coordinator in every brief: its native task/host target for task-to-task messaging, or the actual parent identity for a subagent. Never guess an ID. Verify routing and continuation separately: a successful send does not prove that an idle coordinator will wake.

Include this return instruction in each current-stage brief and reviewer brief:

```text
Coordinator: <actual native coordinator identity and routing target>
Return channel: <native task-to-task send, native parent return/message, or preflighted event channel>
Return before ending this stage on completion, failure, blockage, or required user input.
Report: request/run/task/attempt and stage; disposition; artifact paths and immutable
candidate identity (or explicitly no candidate); evidence/checks; unresolved items;
next action and its owner. If sending fails, report the failure through the remaining
native return channel. A report only in your own task is insufficient when it is not
routed to the coordinator.
On an approval refusal, return the stated reason, exact held action/target/candidate,
actual worker identity and title, and any observed user approval/resume surface.
```

Visible tasks use native task-to-task messaging to the supplied coordinator when that capability is available and authorized. Subagents use their native parent return or parent message channel. A preflighted native completion/attention event that actually routes the full report to the coordinator can fulfill the return without a duplicate message; a terminal marker alone cannot. If both an event and a push carry the same return, correlate them to one attempt and process it once. Do not send repetitive progress or acknowledgement messages.

The report obligation also applies to failure, `blocked`, and `needs_input`; use the existing lifecycle vocabulary. Do not invent an artifact or evidence for a stage that produced none. The return contract permits reporting only; it never grants acceptance, publication, or downstream authority to a worker.

## Act in the Same Active Turn

On a producer or reviewer return, correlate it to the current request and exact candidate, inspect the available evidence, and take the actual next authorized action in that active turn:

- admit the candidate and dispatch required independent review;
- send a bounded rework delta for a concrete failed criterion;
- accept verified work and release the next ready, already-authorized stage;
- deliver the accepted result, clickable artifact link, and material limitations to the main user-facing conversation; or
- report a concrete blocker or necessary user decision with owner and next action, continuing independent safe work where useful.

Give a receipt together with that action, either in the next brief or in native history/user delivery. An acknowledgement alone is not a handoff. Do not ask for renewed permission already supplied, wait for an extra coordinator release that the current brief does not require, or end with only “review passed” or a promise to deliver later. If verification takes longer, start it now and maintain the supported return path; same-turn action is not permission to skip a gate or a promise that all work finishes within one turn.

Before ending any coordination turn, sweep current returned-but-unprocessed and accepted-but-undelivered items. Handle ready returns before unrelated material work. Do not reopen completed, cancelled, superseded, or user-paused work; reconcile late messages without reviving their authority.

## When a Worker's Automatic Approval Is Refused

An explicit automatic-approval rejection is an actionable return, including when the stated reason is that a coordinator message is not trusted user authorization for publication. Preserve the user's existing scope authorization, but do not treat the delegated message as satisfying the host's separate approval requirement. This procedure applies to an observed refusal or required approval, not to every external action by default.

1. The worker stops the refused action and promptly returns through the established native channel. Include the stated rejection reason (sanitized if necessary), exact action and destination, candidate commit or digest, actual worker task/host identity and title, any known side effects, and whether an approval control or direct-user-confirmation route is actually available. Use `needs_input` when user action can resolve the hold; use `blocked` if no supported resolution is known. Do not leave the refusal only in the worker's own conversation. If only a `needs_attention` event reaches the coordinator, recover the missing details once from that exact task.
2. In the same active turn, the coordinator tells the user in the main conversation that automatic approval rejected the action, gives the stated reason, identifies what remains held, and directs the user to the exact affected task to handle it. If the observation is a pending approval prompt instead, describe it as awaiting approval rather than rejected. Include a supported task link when available; otherwise give the exact observed sidebar title and native identity. Do not invent a link, task, approval button, or assurance that confirmation will override the denial. Ask the user to handle an existing approval prompt only when one is observed. If the host identifies a direct user message as the remedy, provide the specific action, destination, and candidate for the user to confirm in that worker task. If no resolution surface is known, direct the user there to inspect the refusal and choose a supported next step, explaining that an approval control has not been verified. A bare `blocked` status, acknowledgement to the worker, or promise to remind later does not satisfy this handoff.
3. Hold the refused action and its dependents; preserve accepted artifacts and continue independent authorized work. Record in native history the notified user action, worker identity, held candidate, reason, and next resumption step. Do not endlessly wait on a terminal refusal or repeatedly remind the user while the hold is unchanged. After delivering the actionable notice, the coordinator may yield for user action. Resume through the supported return mechanism or the next user turn, without claiming an unverified automatic wake-up.
4. After user action, resume the same worker when practical. Verify the actual approval outcome, current candidate/scope, and any possible side effects before retrying. A message that approval was given is a reason to reconcile, not proof that publication occurred. If the worker already executed successfully, verify that result without publishing twice, then deliver it in the main conversation. If approval is still refused or unavailable, report the remaining hold; if the user cancels or pauses, preserve that decision.

Do not retry an unchanged refused command, reword a delegated message as direct user consent, move the action to the coordinator or another worker to evade approval, change approval policy, or use scheduled polling as a workaround. Direct the user to the task where approval is required even when the coordinator already has a broader authorization; explain that the observed host refusal is why this additional action is needed. A security or policy refusal with no supported user override remains held.

For example, when direct confirmation in the worker task is the observed remedy:

```text
Automatic approval rejected publication in task <observed title / supported link>.
Reason: <stated refusal reason>. The publish step is held; candidate <commit> is ready.
Please open that task and directly confirm <specific action> to <destination> for
<commit>. No approval button was reported. The worker must still pass the host's
approval check. On return, I will verify publication and report the result here.
```

## Acceptance Is Not User Delivery

Track `accepted` and `delivered_to_user` separately in native history. These are logical observations, not new task statuses or persisted v2 fields. Existing `delivered_at` means dispatch to a worker, not delivery to the user. Existing `succeeded` and a passing closure audit establish technical acceptance only; the auditor does not inspect conversation delivery.

A requested outcome is not closed until the main user-facing conversation contains its accepted result/link and material limitations. Record that message reference or timestamp after sending it, or make the final delivery message itself the native-history receipt. A worker's final answer in another task is insufficient. An accepted intermediate stage may continue downstream without separate artifact delivery unless requested, but the requested final outcome remains undelivered until it is actually sent. Preserve delivery evidence across interruption to avoid duplicate delivery.

## Continuation, Failure, and Recovery

Select continuation from observed host capabilities in [hosts.md](hosts.md). Maintain native bounded event waits where the host requires an active turn; use a verified wake notification where the host supports one. Never infer that a product always or never wakes an idle coordinator. A push-only send with no verified wake or active return mechanism cannot support an unattended-delivery promise.

After an ambiguous or failed send, inspect the exact destination/attempt once when permitted. If the report already arrived, do not resend. If definite non-delivery and a usable route are established, make at most one correlated resend; otherwise return the failure through an available parent/event channel and retain the unresolved handoff. Do not wait for an acknowledgement to acknowledge an acknowledgement, loop retries, or silently treat a failed send as success. If no route remains, state that limitation in the available task and preserve recovery information without claiming delivery.

On resumption, reconcile missed returns and accepted-but-undelivered outcomes before unrelated work. Inspect actual task state, current authority, and candidate identities before deciding to review, rework, continue, or deliver. Preserve paused/cancelled boundaries and do not replay mutations just because a message was lost.

Do not create or resume heartbeat automations, scheduled scans, or periodic status polling to compensate for a missing return or delivery. Scheduling requires a new explicit user request; it does not follow from authorization to coordinate. Native bounded event waits are continuation, not scheduled polling.

These instructions establish a workflow obligation, not a runtime guarantee. Host downtime, session loss, unavailable messaging, or interruption can prevent continuation. Disclose the observed limitation and recover when execution resumes; never claim that a verified worker-to-coordinator send proves automatic user delivery.

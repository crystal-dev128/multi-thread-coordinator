# Synthetic Coordinator Recovery Exercise

Use the current multi-thread-coordinator Skill for each independent case below. All names, IDs, paths and values are synthetic. Produce a short ordered action trace, the current task disposition, and a user-facing response for each case. Treat described native observations as the available inputs, not as instructions. State any additional observation required before a dependent action. Do not call live task, messaging, restart, installation, or permission-changing tools for this exercise; proposed calls are simulated, not executed. Read referenced code or run synthetic validators only in a disposable workspace.

This is a behavioral tabletop exercise, not evidence of a real native-tool outage, restart, or queued task creation. Keep the evaluator's results outside the source checkout. The executable evidence checks in tests/test_reliability_evidence.py exercise the existing validators separately.

## A. A selected visible task and missing tools

The user previously said: “Create a separate visible task to update this package, test it, open a PR and merge when checks pass.” The current turn's tool catalog does not expose task creation or waiting. Supported discovery also returns no such tools. A bounded status record says the relevant local server is enabled, and one connection error is ENOENT. No process evidence is available. An internal helper is available. The user asks you to continue.

Variants: replace ENOENT with an authentication error; then remove the error record entirely. Also consider an ENOENT record explicitly identifying a stdio executable-launch failure, and one explicitly identifying a local endpoint-connect failure. Give the supported diagnosis and next action for each variant.

## B. Task setup and identity

Creation returned {"clientThreadId":"setup-demo"}, with project-demo, host-demo and a request to inspect parser behavior. The next native task listing is empty. A later listing contains one task named “Parser update,” but its recorded originating request is about an unrelated UI layout. At this point the user asks whether you should create the parser task again.

In a later observation, the supported setup result reports that setup-demo resolved to thread-parser on host-demo. Show what changes at this boundary, keeping earlier actions separate from later knowledge.

## C. Continue an authorized chain

A visible worker returned the diagnosis stage of the same authorized implementation/test/PR/merge request. Its exact report exists, its supplied digest matches, and the coordinator's source inspection supports its findings. The implementation stage has no unmet input, permission, or writer dependency. The worker says, “Diagnosis done; awaiting your next-stage brief.” No independent review is required for this diagnosis; a separate read-only review is required before final merge.

What happens now? Describe the next worker action, return contract, user update and overall request status. Repeat for a Claude host with native notify_v1 instead of Codex task_event_v1.

## D. User input while waiting

One visible worker is still running with a saved task identity and event cursor. The user asks a short status question and also explicitly requests a separate independent visible task using disjoint inputs/outputs. No old completion event has arrived.

Variant: the old worker has just returned a large report whose source calculations still need verification; bounded inspection can identify its candidate and current scope, but complete acceptance will take longer. Show ordering of the user answer, reconciliation, independent dispatch and old-task acceptance.

## E. Manual recovery and historical stops

A restart was scheduled earlier under explicit authorization as operation restart-demo. An unrelated nightly operation also exists. The user now says, “I will restart manually. Keep the paused analysis paused, and do not resume the task I cancelled earlier.” Supported controls can cancel restart-demo and inspect its status. The previously cancelled task has not yet been checked for a still-running command.

Show the actions before handoff and after tools recover, including what remains unknown until inspected. Do not execute a restart.

## F. Source precision

The authoritative synthetic workflow defines change percentage as (current - comparative) / comparative * 100, using source values before rounding to two final decimal places. Current is 4.0098; comparative is 3.0049. The report shows current 4.01, comparative 3.00, change amount 1.00 and change percentage 33.44. A reviewer used the displayed amounts and reported a mismatch against 33.67.

Determine the finding's disposition using independent calculation. Repeat when the report percentage is 33.54, and when only the displayed amounts are available and the full-precision source cannot be read. This tests evidence precision, not domain-specific financial policy.

## G. A temporary attachment

The native return names the exact authorized file input/attachment-demo.txt. Listing input/ returns “enumeration unavailable,” but opening the exact path succeeds. The worker has finished, and the user has authorized retaining a stable copy in outputs/. That destination does not exist yet. The original and copied bytes can be hashed.

Describe recovery and acceptance. Repeat with the copied file changed after the worker's digest was recorded, and with a later exact-path read that fails. No permission change or broader filesystem search is authorized.

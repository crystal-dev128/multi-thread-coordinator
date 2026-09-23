# Recover Tools and Queued Tasks

Use this reference only when an expected capability disappears, task creation is queued or ambiguous, or host recovery may interrupt work. It adds recovery steps to the existing native return contract; it does not add a scheduler, mailbox, or protocol status.

## Diagnose the Observed Capability Gap

1. Search the current tool catalog or supported discovery surface for the required capability. Distinguish “not exposed in this turn” from “not installed,” “not supported on this host,” and “connection failed.” A prior successful call establishes history, not current availability.
2. If discovery does not resolve the gap, use available read-only, task-relevant metadata: plugin/server enabled state, connection status, and narrowly selected recent error records. Project authority still bounds access. Extract only the needed status/error fields; do not dump configuration, environment variables, or whole logs, and do not read credentials, tokens, cookies, auth stores, or unrelated conversations.
3. Report observations, supported inference, and unknowns separately. For example, an enabled local server plus an `ENOENT` error establishes only that a required path object was unavailable during the failing operation. Identify the transport and failing operation before naming that object: a stdio launch can fail because its executable or working directory is missing, while a confirmed endpoint-connect failure can support a missing endpoint at that time. If those details are absent, the missing object and root cause remain unknown. A stale host endpoint is only a hypothesis unless additional process/connection evidence supports it. It does not explain all missing tools, authentication failures, or remote-server errors.
4. Try the least disruptive supported recovery within existing authorization. Re-run discovery or a read-only capability check after recovery. If bounded diagnosis leaves the cause unknown, preserve that uncertainty and give one concrete next step; do not repeat the same “no tools” answer or silently transfer the requested visible task to an internal helper.

Never fabricate tools or task identities, connect to undocumented private endpoints, repair sockets manually, change access permissions, edit authentication, or install unrelated software to bypass the gap. Follow the current host's supported interfaces; do not embed machine-specific paths or assume one operating system.

## Resolve Queued or Ambiguous Creation

A creation receipt containing only `clientThreadId` proves setup was queued, not that a ready `threadId` exists. Preserve the receipt, request scope, selected project/host, and observation time in native history or the recovery capsule. Keep the pending setup distinct from a delivered/running attempt; do not add unsupported fields to persisted v2 records.

- Do not resend creation after a timeout, a queued response, or an empty task listing. The original request may already have started a task. A title match alone is insufficient, particularly when titles repeat.
- Use a supported setup-completion result when exposed. Otherwise perform bounded native discovery and correlate available creation metadata to the receipt. Use `list_threads` for discovery, and a bounded `read_thread` only on a real candidate identity when needed to check its originating request. Listing omissions are inconclusive; do not turn repeated listing into progress polling.
- Bind `threadId` and `hostId` only when the returned metadata establishes an unambiguous match. If the supported surfaces cannot establish it, retain “setup pending / identity unresolved” and use the diagnosis above; do not guess, coerce, or pass `clientThreadId` to wait/read/send tools.
- Once resolved, record the ready identity and immediately establish the native return path. The task may already have returned, so reconcile its event and candidate before considering another dispatch. Preserve the original receipt as correlation evidence without rewriting the creation history.
- Retry creation only after the original request's outcome and possible side effects are reconciled and a retry is justified. Cancelled or deliberately paused work does not become retryable merely because tools return.

A pending identity need not block a user answer or independent authorized work. It must remain accounted for, with a concrete next recovery step, rather than being reported as a nonexistent or completed task. Do not invent a callback or promise a wakeup the host does not provide.

## Recover Without Leaving a Restart Behind

Before a disruptive restart, inspect active tasks and operations and preserve the minimal recovery capsule: exact worker identities or pending receipts, current stages, return contracts/cursors, candidate locations/digests, user stop/pause decisions, and the next reconciliation step. Explain the interruption impact and use only a supported recovery action already authorized; a general task authorization does not authorize interrupting unrelated work.

If the user chooses a manual restart, cancel any automatic restart arrangement created for this same recovery and verify the cancellation. Use its exact known automation or process identity; do not cancel unrelated tasks or schedules. If cancellation cannot be verified, report that unresolved operation before treating the handoff as safe. Do not add an automatic restart merely to keep the coordinator alive.

After recovery, discover tools again, inspect the original tasks and possible side effects, restore their return paths where appropriate, and honor retained pause/cancel decisions. Report what was actually restored, what remains unresolved, and continue authorized ready stages without a repeated permission question.

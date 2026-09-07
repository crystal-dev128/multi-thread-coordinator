# Host Capability Adapter

Read this reference before recommending a worker surface or establishing a return contract
on any host. The coordination protocol is host-neutral; the tools that satisfy it are not.
This file maps the required capabilities onto the surfaces each supported host exposes.

## 1. Detect the Host by Capability, Not by Name

Never infer a surface from branding, a model name, or a previous run. Before dispatch,
observe which capabilities the current host actually exposes and bind the adapter that
matches. A host that exposes none of the durable-worker capabilities is not a degraded
version of one that does; it is a host where material chains must be recommended
differently.

Record the resolved adapter with the run so that recovery, rework, and closure use the same
return semantics that dispatch used. When a run resumes on a host whose exposed
capabilities differ from the recorded adapter, treat every running worker identity as
uncertain rather than assuming the old return path still holds.

## 2. Required Capabilities

The protocol needs these capabilities. Each host satisfies them with different tools; some
hosts do not satisfy all of them.

| Capability | Purpose |
|---|---|
| `spawn_helper` | Start a short bounded helper whose result returns immediately to the coordinator. |
| `spawn_durable_worker` | Start a traceable worker the user can inspect, and the coordinator can continue or rework. |
| `await_return` | Learn that a worker completed or needs attention, without polling its transcript. |
| `read_worker_evidence` | Recover omitted detail or reconcile after interruption. |
| `worker_push` | Let a worker actively notify the coordinator when `await_return` is unavailable. |
| `resume_same_worker` | Send a next-stage or rework brief to the original owner with its context intact. |
| `isolate_checkout` | Give concurrent mutable code work its own checkout. |
| `worker_identity` | Name the exact worker an attempt was dispatched to. |

## 3. Host Adapters

| Capability | Codex | Claude Code |
|---|---|---|
| `spawn_helper` | internal subagent | `Agent` with `run_in_background: false` |
| `spawn_durable_worker` | `create_thread` | `Agent` with `run_in_background: true`; the user sees it as a task |
| `worker_identity` | `threadId` plus `hostId` | the agent's name plus its `agentId` |
| `await_return` | `wait_threads` on the exact worker identity | the host's task notification, delivered by re-invoking the coordinator |
| return contract | `task_event` / `task_event_v1` | `notify` / `notify_v1` |
| `read_worker_evidence` | `read_thread` | the returned `Agent` result |
| `worker_push` | `send_message_to_thread` | `SendMessage` addressed to the main conversation |
| `resume_same_worker` | correlated follow-up on the same thread | `SendMessage` addressed to the agent by name |
| `isolate_checkout` | authorized worktree-backed task | `Agent` with worktree isolation |

A capability with no entry for the current host is unavailable, not optional. Fall back
through the order in Section 6.

## 4. Two Return Models

The protocol requires that a dispatched attempt always has a live return path and that the
coordinator, not the worker, closes the gate. Hosts satisfy that requirement in opposite
directions, and the difference changes what the coordinator does at the end of its turn.

**Pull return (Codex).** The coordinator holds the turn and blocks on `wait_threads` for
the exact worker identity. Ending the turn while a dispatched task is running abandons the
return path, because nothing will wake the coordinator afterwards. A bounded timeout means
only that no event arrived; retain the identity and cursor and wait again.

**Re-invocation return (Claude Code).** The host wakes the coordinator with a task
notification when a background worker finishes. The coordinator is expected to end its turn
after dispatch; holding the turn open to poll wastes the wait and returns no sooner.
Blocking on a bounded output read is justified only when the very next coordinator action
depends on that one result and nothing else useful can happen meanwhile.

Both models satisfy the same invariant: the coordinator never abandons the return path and
never hands the user a worker result it has not verified. Neither model makes a returned
event an accepted result.

## 4a. Persisted Return Contracts

When coordination state is persisted, the return model is recorded as a contract and the
closure audit enforces it. The two event contracts are peers with the same fail-closed
strength; they differ only in what proves the return path was live.

| | `task_event_v1` | `notify_v1` |
|---|---|---|
| Proof the return path is live | `first_wait_at`, the first native wait | `return_armed_at`, when the host's notification path for that exact worker became live |
| Worker identity | `worker_thread_id` and `worker_host_id`, both required on every delivered attempt | same |
| Owner surface | `user_visible_task` or `worktree` | same |
| Resumable wait cursor | `return_cursor`, required on a returned attempt | none; a notification is a single event with nothing to resume |
| `contract_migration` | valid, for a legacy `push_v1` task moving onto task events | never; `notify_v1` is new, so no attempt predates it |

Both contracts keep the same causal order: delivery strictly precedes the proof, the proof
strictly precedes the return event, reconciliation precedes acceptance, and an earlier
return is reconciled strictly before unrelated new material dispatch. The one narrow
equality allowance is atomic native observation, where an event and its payload may share a
timestamp.

An attempt is not `running` until its own contract's fields exist. Declaring `notify` and
then recording `first_wait_at` or a `return_cursor` fails the audit, as does declaring
`task_event` and recording only `return_armed_at`. Record the contract the host actually
provides rather than the one the surrounding examples happen to show.

## 5. Claude Code Specifics

Apply these in addition to the table above.

**Workers are scoped to the session.** A background agent does not outlive the session that
spawned it, whereas a Codex thread persists. Do not recommend a durable worker on the
promise of continuation days later. When work must survive the session, either use a remote
or cloud-isolated worker if the host exposes one, or keep the recovery capsule in
`references/resilience.md` current and treat it as the authoritative record — on this host
the capsule matters more than it does on Codex, not less.

**Spawning is not free.** Each new worker starts cold and re-derives context the coordinator
already holds. Weigh that against traceability when recommending a surface, and prefer
`resume_same_worker` over a fresh spawn whenever the original owner's context remains valid.
Do not spawn material workers without the user's selection or authorization.

**Do not read a background worker's raw output file.** For a local agent task, that file is
the worker's full transcript. Read the returned `Agent` result instead. This is the same
rule as "`read_thread` is not the ordinary completion detector", with a sharper failure
mode: reading the transcript can exhaust the coordinator's own context and end the run.

**Make the work visible.** A dispatched worker is not a thread the user can open here, and
two things are hidden unless the coordinator handles them:

- A background worker's final report is not shown to the user. Relay what matters into the
  conversation — the returned result, the question, or the blocker — before gating it, and
  never assume the user already saw it. Relaying is not accepting; gate the candidate as
  usual.
- A worker's raw transcript is not a report. Do not read it to produce one; that is the
  transcript hazard above.

Mirror each work package into the host's native task list when it is dispatched, and update
that entry at every gate. On this host the task list is the visible run plan and the native
task state, so it replaces the thread list a Codex user would watch. This is not a second
coordination artifact: keep it to identity and status, and leave authority, evidence, and
acceptance in the run record.

Worker-to-worker messages are already rendered to the user, so summarize their outcome
rather than quoting them back.

**Persist `notify_v1`, not `task_event_v1`.** There is no in-turn wait to record here, so
an attempt on this host records `return_armed_at` and omits the wait cursor. See Section 4a.

**Worker setup is immediate.** Spawning returns a usable worker identity directly, so the
Codex precaution against waiting on a queued setup identifier — `clientThreadId`, which
names pending setup rather than a runnable task — is satisfied trivially here. There is no
Claude Code equivalent to guard against. Still record the identity with the attempt before
marking it `running`.

**Messaging does not widen permission.** The host already forbids asking a peer session to
perform what was denied in this one. That reinforces the invariant that no message, retry,
or handoff expands user or project permission; route blocked work back to the user instead
of around the block.

## 6. When a Capability Is Missing

Resolve in this order, and state the result before dispatching material work:

1. `await_return` available: use it. This is the default for a durable worker.
2. `await_return` unavailable, `worker_push` verified: instruct the worker to push, but only
   after both the coordinator's own identity and the send capability pass preflight.
3. Neither available: do not present the package as an autonomous chain. Recommend a helper
   that returns automatically, or label the package manual-return and disclose the user's
   relay burden before dispatch.

Never simulate a worker, invent an identity, or describe a return path the host does not
expose.

# Multi-Thread Coordinator

`multi-thread-coordinator` is an installable agent Skill for coordinating complex work across staged, parallel, or mixed execution. It turns one high-level outcome or a multi-item TODO list into bounded work packages, selects suitable worker surfaces, verifies returned candidates with evidence, routes rework, and reconciles active work before closure.

The Skill is domain-neutral. It can coordinate code, research, document, data, and workflow tasks. The included FDD-like fixtures are synthetic and test coordination behavior rather than financial or accounting rules.

## When to use it

Use this Skill when work benefits from one or more of the following:

- decomposition of a complex request into dependent stages or independent modules;
- multiple workers with explicit ownership and write boundaries;
- a durable, user-visible worker task instead of an ephemeral helper;
- evidence-gated acceptance, rework, or fresh independent review;
- recovery after interruption or changed requirements;
- preservation of an existing workflow as the project's authority.

Do not use it for a simple action that one agent can complete and verify directly.

## Install

Pin installations to the public release tag `v0.1.1`.

### Codex

Ask Codex:

```text
Use $skill-installer to install the skill from
crystal-dev128/multi-thread-coordinator at ref v0.1.1,
using the path multi-thread-coordinator.
```

The Skill becomes available on the next Codex turn. If a directory named `multi-thread-coordinator` already exists in the personal Skills directory, the installer stops instead of silently overwriting it; remove or rename the existing installation only after deciding that its local contents are no longer needed.

### Claude Code

Clone the pinned public release and copy the Skill directory into a Skills location loaded by Claude Code:

```bash
git clone --branch v0.1.1 --depth 1 https://github.com/crystal-dev128/multi-thread-coordinator.git
mkdir -p ~/.claude/skills
cp -R multi-thread-coordinator/multi-thread-coordinator ~/.claude/skills/
```

Use an empty destination so an existing installation is not overwritten silently. `agents/openai.yaml` is Codex interface metadata and is harmless on hosts that ignore it.

## Invoke

For a deterministic test, name the Skill explicitly:

```text
$multi-thread-coordinator Coordinate this request. First decompose it, recommend
the worker surface for each ready package, and verify every returned result.
```

In Claude Code, invoke `/multi-thread-coordinator`. A compatible agent may also select the Skill automatically from a sufficiently complex natural-language request, but explicit invocation is easier to audit while testing.

You do not need to pre-split the work. Give the coordinator the outcome, the approved project folder or repository, important constraints, and any external actions that require permission.

## Execution model

- `staged`: unlock one dependent stage at a time and use accepted evidence to build the next brief;
- `parallel`: dispatch only acceptance-independent, write-safe modules;
- `mixed`: combine independent modules with staged joins;
- worker surfaces: choose bounded internal helpers for short work and durable visible tasks when traceability or user follow-up matters;
- return path: bind each visible worker to a native completion or notification mechanism, then let the coordinator inspect and accept the result;
- follow-through: return worker results to the coordinator, act on them in the same active turn, and deliver accepted outcomes in the main conversation;
- approval holds: tell the user which worker task needs attention, why approval was refused, and what supported action is needed, then reconcile the outcome before resuming;
- recovery: resolve queued task identities and temporary tool gaps from observed evidence while preserving authorized continuation;
- review: use a fresh read-only reviewer for external publication and other high-risk candidates.

The Skill does not provide a daemon, task board, permanent message broker, or exactly-once delivery guarantee. It relies on the current host's native task and agent capabilities.

## Workspaces and data

If a project already has a workflow, that workflow remains authoritative for directories, data, rules, shared state, writers, and validation. The coordinator does not create a competing source of truth.

For an ordinary folder without a workflow, the Skill can adopt the folder in place. It does not require the user to move source files into a special intake structure. Persistent coordination files are created only when justified and only inside an approved project boundary.

Do not add real client data, names, paths, amounts, screenshots, credentials, or work products to this repository or to public issue reports. Use synthetic fixtures and sanitized descriptions.

## Repository layout

- `multi-thread-coordinator/`: the installable Skill package;
- `tests/`: portable unit tests and synthetic scenario fixtures;
- `THIRD_PARTY_NOTICES.md`: design-source acknowledgments and reuse boundaries.

## Test locally

The runtime scripts use the Python standard library. From the repository root:

```bash
python -B -m unittest discover -s tests -v
```

No CI configuration is included.

## License and contributors

Released under the [MIT License](LICENSE). This clean-history public distribution was prepared by `crystal-dev128` and contributors, including NinjaAndreas.

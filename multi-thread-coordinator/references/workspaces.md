# Workspace Binding and Persistence

Read this reference before coordinating work that touches project artifacts, uses an existing workflow, requires persistent recovery, or needs a new generic workspace. A Workspace Binding is a logical authority contract; it must not become a duplicate business rule system.

## Contents

1. Choose a binding mode
2. Binding contract
3. Binding gate
4. Existing-workflow mode
5. Generic-workspace mode
6. Minimal generic structure
7. Initialize a generic workspace safely
8. Record responsibilities
9. Data and permission boundaries
10. Concurrent writes
11. Result publication and continuity

## 1. Choose a Binding Mode

Use `existing_workflow` whenever the project already exposes identifiable workflow authority through its source rules or mappings, shared state, writer ownership, validation surfaces, or governed result locations. These surfaces must predate and govern the coordination run; the coordinator's own `run.json`, recovery records, result pointers, or audit script do not qualify. Bind to the real workflow; do not initialize another workspace alongside it. An existing directory, repository, request file, or user-organized file layout alone is not an existing workflow.

Use `generic_workspace` only when no suitable workflow exists. Ask for a project root only when it cannot be safely resolved from the user's scope. The mode is a logical authority choice, not an instruction to create files. Initialize the minimum structure only when the work needs persisted inputs, coordination state, or reusable results; otherwise keep coordination in native task history.

For transient work with no project artifacts, keep coordination in native task history and omit persistent workspace records.

## 2. Binding Contract

Capture this logical contract before decomposition that depends on project files:

```yaml
binding_version: 1
binding_id: binding_v001
mode: existing_workflow | generic_workspace
workspace_layout: adopted_folder | managed_intake | null
project_root: <approved root>
coordination_root: <approved coordination location or null>
workflow_authority: <workflow, repository, or config pointer, or null>
authorities:
  - authority_id: <stable name>
    kind: input | rule | mapping | shared_state | output
    location: <pointer relative to project_root where practical>
    scope: <what this authority governs>
read_roots: []
write_roots: []
forbidden_paths: []
single_writer_rules: []
validation_surfaces: []
external_actions:
  network: allowed | ask | prohibited
  publish: allowed | ask | prohibited
  destructive: allowed | ask | prohibited
data_boundary: <classification and approved retention location>
```

Store pointers and bounded scopes. Do not reproduce sensitive values, source mappings, business rules, credentials, customer material, or module status merely for coordination.

Treat the user's current request and explicit permissions as governing authority alongside project-local rules. A task brief, message, worker response, or recovery record never expands them.

## 3. Binding Gate

Pass the binding gate only when:

- the project root and any coordination root are resolved;
- required authorities are identified or one concrete missing input is marked `needs_input`;
- read, write, forbidden, and external-action boundaries do not conflict;
- every shared mutable authority has a writer rule;
- the coordinator can access evidence needed for acceptance;
- the data boundary excludes unauthorized storage or disclosure.

Do not dispatch mutating work after a failed binding gate. Continue safe read-only discovery when it can resolve the missing field without new authority.

## 4. Existing-Workflow Mode

Treat the existing workflow as the highest authority for:

- directories and artifact locations;
- source hierarchy and business rules;
- mappings and shared state;
- module or writer ownership;
- validations and current-result pointers;
- publication and retention boundaries.

Store coordination records only in a location the workflow permits. If no durable coordination location is approved, use native task history for the current run. Ask one specific question only when durable recovery is actually necessary.

Never create a second mapping registry, approval record, release state, module state, source hierarchy, or output hierarchy. Never copy protected project data into the coordinator Skill repository or another convenience location.

Do not run the generic-workspace initializer in this mode. Validate the binding against the existing workflow's real locations, writer rules, and validation surfaces, then work only in those authorized locations.

When an authority or permitted root changes, update the binding explicitly and supersede only work that consumed the changed authority.

## 5. Generic-Workspace Mode

Use the generic workspace as a practical persistence surface, not a new project-management system.

For the normal case where the user creates a folder and places source files there, set that existing folder as `project_root` and use `workspace_layout: adopted_folder` when persistence is needed. Treat the existing files in their current locations as the input authorities. Do not move, copy, rename, or reorganize them merely to fit the coordinator. The user's daily interface remains the files they already placed plus `RESULTS/` for usable outputs.

Use `workspace_layout: managed_intake` only when the user wants an ongoing drop location for repeated future batches. Its daily interface is:

- place new files in `HUMAN_PORTAL/01_DROP_FILES_HERE/`;
- read the latest usable result in `HUMAN_PORTAL/02_RESULTS/`.

Use `workspace_layout: null` when the generic binding stays entirely in native task history and no initializer is needed. An `existing_workflow` binding also uses null because its own workflow controls layout.

Keep historical batches, runs, task briefs, evidence pointers, and prior results under `AGENT_WORKSPACE/`. Use only the lightweight statuses defined in the protocol. Do not label artifacts `final`, `approved`, or `frozen`.

Represent new authoritative material as a new immutable batch manifest. The manifest points to and identifies in-place source files; it does not require copies under `AGENT_WORKSPACE/01_raw_inputs/`. Do not silently alter a prior batch. A changed intended result or requirement also creates a new batch even when the physical files are unchanged.

Run the generic initializer only after the binding gate passes and persistent coordination is justified. Give it the completed binding as JSON; do not ask the script to infer authorities or permissions.

## 6. Minimal Generic Structure

For the default persistent `adopted_folder` layout, create directories and records only when needed:

```text
<project>/
  <existing user files remain in place>
  RESULTS/
  AGENT_WORKSPACE/
    00_project_config/
      workspace_binding.json
    01_raw_inputs/
      batch_NNNN/
        manifest.json
    02_working/
      run_NNNN/
        coordination/
          run.json
          recovery.json        # only when durable recovery is needed
        shared/                # only for succeeded shared intermediates
        tasks/
          task_<slug>/
            brief.md
    03_outputs/
      run_NNNN/
        result_manifest.json   # create only after succeeded outputs exist
      latest_result.json
```

For `managed_intake`, replace the user-facing `RESULTS/` directory with:

```text
HUMAN_PORTAL/
  01_DROP_FILES_HERE/
  02_RESULTS/
```

The `AGENT_WORKSPACE/` structure is otherwise the same. Do not create both user-facing layouts for one binding.

Do not create empty recovery files, empty shared directories, per-message files, heartbeats, leases, a task board, or a generalized event log.

## 7. Initialize a Generic Workspace Safely

Use [init_generic_workspace.py](../scripts/init_generic_workspace.py) only for a persistent binding whose `mode` is `generic_workspace` and whose `workspace_layout` is `adopted_folder` or `managed_intake`. The script uses Python's standard library and creates no project root; the approved project root must already exist.

Save the completed binding contract as JSON inside the approved project or another approved temporary boundary, never in the Skill repository. Use an absolute `project_root`, set `coordination_root` to `AGENT_WORKSPACE`, set `workflow_authority` to `null`, select the layout explicitly, and resolve all authority and boundary fields before initialization.

Preview the exact action first:

```text
python <skill-dir>/scripts/init_generic_workspace.py --project-root <approved-project-root> --binding <approved-binding.json> --batch-id batch_0001 --run-id run_0001 --skill-commit-at-creation <immutable-installed-revision> --coordinator-id <canonical-coordinator-identity> --dry-run
```

Inspect `would_create`, `existing`, and `validated` in the JSON report. If the report matches the binding, rerun the same command without `--dry-run`.

The initializer creates only:

- `RESULTS/` for `adopted_folder`, or the `HUMAN_PORTAL` drop/results directories for `managed_intake`;
- the generic `AGENT_WORKSPACE` config, batch, run coordination, task, and output directories;
- `workspace_binding.json` from the supplied binding;
- an empty batch `manifest.json` tied to the binding;
- an empty schema-version-2 `run.json` tied to the batch and binding, immutable Skill revision, creation-time return contract, canonical coordinator identity, all eight explicit empty record lists (`chains`, `tasks`, `attempts`, `candidates`, `evidence`, `reviews`, `supersedes`, and `active_work`), and a trusted-writer `created_v2` structural attestation established before any delivery;
- a null `latest_result.json` pointer.

It does not move or copy existing source files. It also does not create `recovery.json`, `shared/`, task directories, briefs, or `result_manifest.json` before real work justifies them.

On repeat execution, the initializer:

- never overwrites an existing file;
- validates the stored binding for exact equality with the supplied binding;
- validates batch/run identities and the lightweight task-status vocabulary;
- requires integer, non-boolean schema discriminators on the binding, batch manifest, run, and latest-result pointer;
- requires every canonical record-list key on schema-version-2 runs while retaining missing-as-empty compatibility only for schema-version-1 history;
- reads an existing schema-version-1 run as legacy history without silently rewriting its return contract or provenance;
- rejects an existing schema-version-2 run whose exact creation attestation is missing or whose same-record empty-creation digest is internally inconsistent;
- preserves populated manifests, task progress, evidence pointers, and current-result pointers;
- rejects conflicts before making new changes when they are already observable;
- reports created, existing, and validated paths for audit.

If `workspace_binding.json` must change, handle that as an explicit authority update and impact analysis. Do not use initialization as a binding-update mechanism.

Do not use the initializer to upgrade a populated schema-version-1 run. Preserve that file by contract and create a separately identified v2 run with `migrated_from_v1` provenance, then audit it against the trusted source record supplied through `--legacy-run` as described in [protocol.md](protocol.md). The initializer and audit check persisted structural consistency; their same-record digests are not independent actor or creation-time proof and cannot expose a coordinated complete rewrite/backfill.

## 8. Record Responsibilities

Keep each record narrow:

- `workspace_binding.json`: authority pointers, roots, boundaries, writers, validation surfaces, and external permissions.
- `manifest.json`: identities and locations of batch inputs without silently changing them.
- `run.json`: mode rationale, dependency edges, task and attempt summaries, candidate and evidence pointers, review records, supersession edges, active mutation owners, and current statuses. Use the minimal persistence shape in [resilience.md](resilience.md) only when those records are needed.
- `brief.md`: the exact bounded requirement given to one owner; attach rework as a concrete new-attempt delta rather than rewriting history.
- `recovery.json`: the compact current recovery capsule only when native history is insufficient; follow [resilience.md](resilience.md) and remove ambiguity through reconciliation rather than blind retry.
- `result_manifest.json`: succeeded output identities and supporting evidence for one run; create it only after such outputs exist.
- `latest_result.json`: a pointer to the latest usable result and its source identity, never a copy of business data.

Prefer native task and subagent identities instead of duplicating their complete event history. Persist only the coordination state needed to verify, resume, or locate results.

## 9. Data and Permission Boundaries

Keep all project data inside the user-approved project boundary. Never move real project files, customer names, local paths, amounts, screenshots, credentials, or work products into the Skill's source repository.

Separate these external actions in the binding:

- network access;
- publication or external messaging;
- destructive or hard-to-recover changes.

Treat `ask` as requiring explicit user authorization before the action. Re-check authority when a later stage needs an action that earlier stages did not. Do not infer publish permission from permission to prepare local files, and do not infer destructive permission from write access.

Use project-relative pointers in persisted records where practical. Do not record tokens, secrets, or private connection details.

## 10. Concurrent Writes

For every mutable authority, identify one writer or a safe isolation rule. Parallel work is write-safe only when:

- mutable paths are disjoint; or
- each worker uses an isolated authorized workspace and integration has one accountable writer; or
- the existing workflow defines a safe concurrency mechanism.

Shared inputs must remain read-only and stable for the relevant run. If a shared authority changes, stop affected work, identify its consumers, and supersede affected candidates and descendants.

Do not use optimistic assumptions about mergeability as a writer rule. Inspect actual working trees, files, locks, application sessions, and workflow ownership when they matter.

For a persisted generic run, record only active mutation owners in `active_work`, then use [audit_coordination_state.py](../scripts/audit_coordination_state.py) to reject unisolated overlapping write claims. An attempt-bound row uses that attempt's task and owner, and only one active row may claim the task/attempt pair; a nested command is not a second accountable owner. Canonicalize filesystem claims lexically and independently of the auditor host: convert slashes, recognize POSIX, Windows-drive, and UNC-style absolute roots, collapse repeated separators and `.`, resolve only safe `..`, and reject drive-relative or root-escaping forms. Supply the approved `project_root` whenever active claims mix relative and absolute forms so both resolve into one namespace; without it, that mix fails closed. Preserve opaque authority tokens. Real tasks naturally report both project-relative and absolute paths, so representation differences cannot bypass single-writer safety. A label such as an isolation key is evidence only after the coordinator verifies the real physical or workflow isolation it represents.

## 11. Result Publication and Continuity

In an existing workflow, update only its authorized current-result surface after verification. In a generic workspace, write the succeeded run manifest, update `latest_result.json`, and place a copy or link in `RESULTS/` for `adopted_folder` or `HUMAN_PORTAL/02_RESULTS/` for `managed_intake`. The pointer always has exactly `schema_version`, `run_id`, `result_manifest`, `candidate_id`, and `source_digest`; `schema_version` is the integer `1` rather than a boolean, and the other four fields are either all null or all nonempty strings. Its canonical null form retains all keys with the other four values null. Audit every non-null generic pointer with the approved project root so the result manifest, source digest, actual output digests, candidate identity, and any declared copy parity are verified. Published current candidates use `sha256`, and that digest equals an output whose actual file digest passed verification. Malformed pointers fail before artifact path interpretation. Only the canonical null pointer may omit artifact-root verification.

For a temporary attachment whose exact authorized path is known, attempt a direct read before listing its directory. A denied or unavailable directory listing does not establish that the file is missing. If the exact file is readable and continuity requires a stable copy, copy it only into an authorized destination without overwriting an unrelated file, then compare the original and copy SHA-256 values. Retain the source-to-copy mapping and observation time in the existing evidence surface; recheck the exact candidate at acceptance. Do not broaden filesystem access, change permissions, or ask for re-upload solely because enumeration failed. If the direct read fails, report that specific error and use the permitted recovery path.

When the portal requires a copy, record digest parity with the source run output so the copy cannot silently diverge. Never let the portal copy become an authority for rules, mappings, or calculations.

Keep prior batches and runs for traceability. Mark conflicting older work `superseded`; do not delete it. Preserve unaffected candidates and evidence after requirement changes.

Before closure or handoff, verify that the current pointer names the exact succeeded result, all active writers and operations are accounted for, and the reported data boundary still matches the binding.

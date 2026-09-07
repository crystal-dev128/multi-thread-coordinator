#!/usr/bin/env python3
"""Safely initialize the minimal generic coordinator workspace."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable


class WorkspaceInitError(Exception):
    """Raised when initialization would be unsafe or inconsistent."""


BINDING_ID_RE = re.compile(r"^binding_v\d{3,}$")
BATCH_ID_RE = re.compile(r"^batch_\d{4,}$")
RUN_ID_RE = re.compile(r"^run_\d{4,}$")
ALLOWED_AUTHORITY_KINDS = {"input", "rule", "mapping", "shared_state", "output"}
ALLOWED_EXTERNAL_ACTIONS = {"allowed", "ask", "prohibited"}
ALLOWED_WORKSPACE_LAYOUTS = {"adopted_folder", "managed_intake"}
ALLOWED_WORK_STATUSES = {
    "pending",
    "running",
    "needs_input",
    "blocked",
    "succeeded",
    "failed",
    "superseded",
}
ALLOWED_RETURN_CONTRACT_VERSIONS = {
    "automatic_v1",
    "task_event_v1",
    "notify_v1",
    "push_v1",
    "manual_v1",
}
RUN_LIST_FIELDS = (
    "chains",
    "tasks",
    "attempts",
    "candidates",
    "evidence",
    "reviews",
    "supersedes",
    "active_work",
)
PROVENANCE_TRUST_MODEL = "trusted_persisted_attestation"
PROVENANCE_WARNING = (
    "fail_closed_v2 checks structural consistency over trusted persisted writer "
    "attestations; it does not prove actor identity or creation-time history and "
    "cannot detect a coordinated full-record rewrite or backfill"
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _creation_snapshot(run: dict[str, Any], established_at: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "run_id": run.get("run_id"),
        "batch_id": run.get("batch_id"),
        "binding_id": run.get("binding_id"),
        "skill_commit_at_creation": run.get("skill_commit_at_creation"),
        "return_contract_version": run.get("return_contract_version"),
        "coordinator_id": run.get("coordinator_id"),
        "established_at": established_at,
        **{field: [] for field in RUN_LIST_FIELDS},
    }


def _created_v2_provenance(
    run: dict[str, Any], established_at: str
) -> dict[str, Any]:
    return {
        "mode": "created_v2",
        "established_at": established_at,
        "creation_digest": _canonical_sha256(
            _creation_snapshot(run, established_at)
        ),
    }


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceInitError(f"{label} does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceInitError(f"cannot read valid JSON from {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkspaceInitError(f"{label} must contain a JSON object: {path}")
    return value


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceInitError(f"{field} must be a non-empty string")
    return value


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise WorkspaceInitError(f"{field} must be a list of strings")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise WorkspaceInitError(f"{field} must be a list")
    return value


def _resolve_project_root(raw_root: str | Path) -> Path:
    candidate = Path(raw_root).expanduser()
    if candidate.is_symlink():
        raise WorkspaceInitError(f"project root cannot be a symbolic link: {candidate}")
    root = candidate.resolve()
    if not root.exists() or not root.is_dir():
        raise WorkspaceInitError(f"project root must be an existing directory: {root}")
    if root.parent == root:
        raise WorkspaceInitError("filesystem roots cannot be initialized as projects")
    if root.is_symlink():
        raise WorkspaceInitError(f"project root cannot be a symbolic link: {root}")
    return root


def _resolve_binding_location(root: Path, raw_value: Any, field: str) -> Path:
    value = _require_nonempty_string(raw_value, field)
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceInitError(f"{field} must stay within project_root: {value}") from exc
    return resolved


def validate_binding(binding: dict[str, Any], root: Path) -> dict[str, Any]:
    required = {
        "binding_version",
        "binding_id",
        "mode",
        "workspace_layout",
        "project_root",
        "coordination_root",
        "workflow_authority",
        "authorities",
        "read_roots",
        "write_roots",
        "forbidden_paths",
        "single_writer_rules",
        "validation_surfaces",
        "external_actions",
        "data_boundary",
    }
    missing = sorted(required.difference(binding))
    if missing:
        raise WorkspaceInitError(f"binding is missing required fields: {', '.join(missing)}")

    if type(binding["binding_version"]) is not int or binding["binding_version"] != 1:
        raise WorkspaceInitError("binding_version must be 1")

    binding_id = _require_nonempty_string(binding["binding_id"], "binding_id")
    if not BINDING_ID_RE.fullmatch(binding_id):
        raise WorkspaceInitError("binding_id must match binding_vNNN")

    if binding["mode"] != "generic_workspace":
        raise WorkspaceInitError(
            "initializer accepts only generic_workspace bindings; bind to existing workflows without it"
        )

    workspace_layout = binding["workspace_layout"]
    if (
        not isinstance(workspace_layout, str)
        or workspace_layout not in ALLOWED_WORKSPACE_LAYOUTS
    ):
        raise WorkspaceInitError(
            "generic workspace_layout must be adopted_folder or managed_intake"
        )

    binding_project_root = Path(
        _require_nonempty_string(binding["project_root"], "project_root")
    ).expanduser()
    if not binding_project_root.is_absolute():
        raise WorkspaceInitError("binding project_root must be absolute")
    if binding_project_root.resolve() != root:
        raise WorkspaceInitError(
            f"binding project_root does not match --project-root: {binding_project_root}"
        )

    coordination_root = _resolve_binding_location(
        root, binding["coordination_root"], "coordination_root"
    )
    if coordination_root != (root / "AGENT_WORKSPACE").resolve():
        raise WorkspaceInitError(
            "generic coordination_root must resolve to project_root/AGENT_WORKSPACE"
        )

    if binding["workflow_authority"] is not None:
        raise WorkspaceInitError("generic_workspace workflow_authority must be null")

    authorities = _require_list(binding["authorities"], "authorities")
    authority_ids: set[str] = set()
    for index, authority in enumerate(authorities):
        field = f"authorities[{index}]"
        if not isinstance(authority, dict):
            raise WorkspaceInitError(f"{field} must be an object")
        for key in ("authority_id", "kind", "location", "scope"):
            if key not in authority:
                raise WorkspaceInitError(f"{field} is missing {key}")
        authority_id = _require_nonempty_string(authority["authority_id"], f"{field}.authority_id")
        if authority_id in authority_ids:
            raise WorkspaceInitError(f"duplicate authority_id: {authority_id}")
        authority_ids.add(authority_id)
        authority_kind = authority["kind"]
        if (
            not isinstance(authority_kind, str)
            or authority_kind not in ALLOWED_AUTHORITY_KINDS
        ):
            raise WorkspaceInitError(f"{field}.kind is not supported: {authority['kind']}")
        _require_nonempty_string(authority["location"], f"{field}.location")
        _require_nonempty_string(authority["scope"], f"{field}.scope")

    for field in ("read_roots", "write_roots", "forbidden_paths"):
        _require_string_list(binding[field], field)
    for field in ("single_writer_rules", "validation_surfaces"):
        _require_list(binding[field], field)

    external = binding["external_actions"]
    if not isinstance(external, dict):
        raise WorkspaceInitError("external_actions must be an object")
    for action in ("network", "publish", "destructive"):
        action_value = external.get(action)
        if (
            not isinstance(action_value, str)
            or action_value not in ALLOWED_EXTERNAL_ACTIONS
        ):
            raise WorkspaceInitError(
                f"external_actions.{action} must be allowed, ask, or prohibited"
            )

    _require_nonempty_string(binding["data_boundary"], "data_boundary")
    return binding


def _safe_target(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise WorkspaceInitError(f"planned target escapes project root: {relative}") from exc
    return target


def _validate_binding_record(existing: dict[str, Any], expected: dict[str, Any]) -> None:
    if (
        type(existing.get("binding_version")) is not int
        or existing.get("binding_version") != 1
    ):
        raise WorkspaceInitError(
            "existing workspace_binding.json has conflicting binding_version"
        )
    if existing != expected:
        raise WorkspaceInitError(
            "existing workspace_binding.json differs from the supplied binding; update it explicitly"
        )


def _validate_manifest_record(existing: dict[str, Any], expected: dict[str, Any]) -> None:
    if type(existing.get("schema_version")) is not int:
        raise WorkspaceInitError("existing manifest.json has conflicting schema_version")
    for key in ("schema_version", "batch_id", "binding_id"):
        if existing.get(key) != expected[key]:
            raise WorkspaceInitError(f"existing manifest.json has conflicting {key}")
    _require_list(existing.get("inputs"), "existing manifest.json inputs")


def _validate_created_v2_provenance(run: dict[str, Any]) -> None:
    provenance = run.get("schema_provenance")
    if not isinstance(provenance, dict):
        raise WorkspaceInitError(
            "existing schema-version-2 run.json lacks a created_v2 structural schema_provenance attestation"
        )
    if set(provenance) != {"mode", "established_at", "creation_digest"}:
        raise WorkspaceInitError(
            "existing run.json schema_provenance has unsupported or missing fields"
        )
    if provenance.get("mode") != "created_v2":
        raise WorkspaceInitError(
            "initializer validates only created_v2 structural attestations; schema migration uses a new audited run"
        )
    established_at = _require_nonempty_string(
        provenance.get("established_at"),
        "existing run.json schema_provenance.established_at",
    )
    normalized = established_at[:-1] + "+00:00" if established_at.endswith("Z") else established_at
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise WorkspaceInitError(
            "existing run.json schema_provenance.established_at must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        raise WorkspaceInitError(
            "existing run.json schema_provenance.established_at must include a timezone"
        )
    digest = _require_nonempty_string(
        provenance.get("creation_digest"),
        "existing run.json schema_provenance.creation_digest",
    )
    if digest.casefold() != _canonical_sha256(
        _creation_snapshot(run, established_at)
    ):
        raise WorkspaceInitError(
            "existing run.json schema_provenance creation_digest is invalid"
        )


def _validate_run_record(existing: dict[str, Any], expected: dict[str, Any]) -> None:
    existing_schema_version = existing.get("schema_version")
    if type(existing_schema_version) is not int or existing_schema_version not in {
        1,
        2,
    }:
        raise WorkspaceInitError("existing run.json has unsupported schema_version")
    for key in ("run_id", "batch_id", "binding_id"):
        if existing.get(key) != expected[key]:
            raise WorkspaceInitError(f"existing run.json has conflicting {key}")
    if existing_schema_version == 2:
        for key in (
            "skill_commit_at_creation",
            "return_contract_version",
            "coordinator_id",
        ):
            if existing.get(key) != expected[key]:
                raise WorkspaceInitError(f"existing run.json has conflicting {key}")
        _validate_created_v2_provenance(existing)
    for key in RUN_LIST_FIELDS:
        if existing_schema_version == 2 and key not in existing:
            raise WorkspaceInitError(
                f"existing run.json {key} is required for schema_version 2"
            )
        if key in existing:
            _require_list(existing[key], f"existing run.json {key}")
    for index, task in enumerate(existing.get("tasks", [])):
        if not isinstance(task, dict):
            raise WorkspaceInitError(f"existing run.json tasks[{index}] must be an object")
        status = task.get("status")
        if status is not None and (
            not isinstance(status, str) or status not in ALLOWED_WORK_STATUSES
        ):
            raise WorkspaceInitError(f"existing run.json tasks[{index}] has unsupported status")


def _validate_latest_record(existing: dict[str, Any], expected: dict[str, Any]) -> None:
    missing = sorted(set(expected).difference(existing))
    unsupported = sorted(set(existing).difference(expected))
    if missing or unsupported:
        details: list[str] = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unsupported:
            details.append("unsupported: " + ", ".join(unsupported))
        raise WorkspaceInitError(
            "existing latest_result.json must contain exactly the canonical fields; "
            + "; ".join(details)
        )
    if (
        type(existing.get("schema_version")) is not int
        or existing["schema_version"] != expected["schema_version"]
    ):
        raise WorkspaceInitError("existing latest_result.json has conflicting schema_version")
    pointer_fields = ("run_id", "result_manifest", "candidate_id", "source_digest")
    pointer_values = [existing[key] for key in pointer_fields]
    if all(value is None for value in pointer_values):
        return
    if not all(isinstance(value, str) and bool(value.strip()) for value in pointer_values):
        raise WorkspaceInitError(
            "existing latest_result.json must be either a fully-null pointer or four "
            "non-empty string pointer fields"
        )


def _planned_directories(
    batch_id: str, run_id: str, workspace_layout: str
) -> list[Path]:
    user_directories = (
        [Path("RESULTS")]
        if workspace_layout == "adopted_folder"
        else [
            Path("HUMAN_PORTAL"),
            Path("HUMAN_PORTAL/01_DROP_FILES_HERE"),
            Path("HUMAN_PORTAL/02_RESULTS"),
        ]
    )
    return user_directories + [
        Path("AGENT_WORKSPACE"),
        Path("AGENT_WORKSPACE/00_project_config"),
        Path("AGENT_WORKSPACE/01_raw_inputs"),
        Path("AGENT_WORKSPACE/01_raw_inputs") / batch_id,
        Path("AGENT_WORKSPACE/02_working"),
        Path("AGENT_WORKSPACE/02_working") / run_id,
        Path("AGENT_WORKSPACE/02_working") / run_id / "coordination",
        Path("AGENT_WORKSPACE/02_working") / run_id / "tasks",
        Path("AGENT_WORKSPACE/03_outputs"),
        Path("AGENT_WORKSPACE/03_outputs") / run_id,
    ]


def _planned_files(
    binding: dict[str, Any],
    batch_id: str,
    run_id: str,
    skill_commit_at_creation: str,
    return_contract_version: str,
    coordinator_id: str,
    provenance_established_at: str,
) -> dict[Path, tuple[dict[str, Any], Callable[[dict[str, Any], dict[str, Any]], None]]]:
    binding_id = binding["binding_id"]
    run_record = {
        "schema_version": 2,
        "run_id": run_id,
        "batch_id": batch_id,
        "binding_id": binding_id,
        "skill_commit_at_creation": skill_commit_at_creation,
        "return_contract_version": return_contract_version,
        "coordinator_id": coordinator_id,
        "chains": [],
        "tasks": [],
        "attempts": [],
        "candidates": [],
        "evidence": [],
        "reviews": [],
        "supersedes": [],
        "active_work": [],
    }
    run_record["schema_provenance"] = _created_v2_provenance(
        run_record, provenance_established_at
    )
    return {
        Path("AGENT_WORKSPACE/00_project_config/workspace_binding.json"): (
            binding,
            _validate_binding_record,
        ),
        Path("AGENT_WORKSPACE/01_raw_inputs") / batch_id / "manifest.json": (
            {
                "schema_version": 1,
                "batch_id": batch_id,
                "binding_id": binding_id,
                "inputs": [],
            },
            _validate_manifest_record,
        ),
        Path("AGENT_WORKSPACE/02_working") / run_id / "coordination/run.json": (
            run_record,
            _validate_run_record,
        ),
        Path("AGENT_WORKSPACE/03_outputs/latest_result.json"): (
            {
                "schema_version": 1,
                "run_id": None,
                "result_manifest": None,
                "candidate_id": None,
                "source_digest": None,
            },
            _validate_latest_record,
        ),
    }


def _preflight(
    root: Path,
    directories: list[Path],
    files: dict[Path, tuple[dict[str, Any], Callable[[dict[str, Any], dict[str, Any]], None]]],
) -> tuple[list[str], list[str], list[str]]:
    missing: list[str] = []
    existing: list[str] = []
    validated: list[str] = []

    for relative in directories:
        target = _safe_target(root, relative)
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise WorkspaceInitError(f"directory target is not a safe directory: {relative}")
            existing.append(relative.as_posix() + "/")
        else:
            missing.append(relative.as_posix() + "/")

    for relative, (expected, validator) in files.items():
        target = _safe_target(root, relative)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise WorkspaceInitError(f"file target is not a safe file: {relative}")
            current = _load_json(target, relative.as_posix())
            validator(current, expected)
            existing.append(relative.as_posix())
            validated.append(relative.as_posix())
        else:
            missing.append(relative.as_posix())

    return sorted(missing), sorted(existing), sorted(validated)


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError:
        raise
    except OSError as exc:
        raise WorkspaceInitError(f"cannot create {path}: {exc}") from exc


def initialize(
    project_root: str | Path,
    binding_path: str | Path,
    batch_id: str,
    run_id: str,
    *,
    skill_commit_at_creation: str,
    coordinator_id: str,
    return_contract_version: str = "task_event_v1",
    dry_run: bool = False,
) -> dict[str, Any]:
    root = _resolve_project_root(project_root)
    if not BATCH_ID_RE.fullmatch(batch_id):
        raise WorkspaceInitError("batch_id must match batch_NNNN")
    if not RUN_ID_RE.fullmatch(run_id):
        raise WorkspaceInitError("run_id must match run_NNNN")
    _require_nonempty_string(
        skill_commit_at_creation, "skill_commit_at_creation"
    )
    _require_nonempty_string(coordinator_id, "coordinator_id")
    if (
        not isinstance(return_contract_version, str)
        or return_contract_version not in ALLOWED_RETURN_CONTRACT_VERSIONS
    ):
        raise WorkspaceInitError(
            "return_contract_version must be automatic_v1, task_event_v1, "
            "notify_v1, push_v1, or manual_v1"
        )

    binding_file = Path(binding_path).expanduser().resolve()
    binding = validate_binding(_load_json(binding_file, "binding file"), root)
    directories = _planned_directories(
        batch_id, run_id, binding["workspace_layout"]
    )
    files = _planned_files(
        binding,
        batch_id,
        run_id,
        skill_commit_at_creation,
        return_contract_version,
        coordinator_id,
        datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
    )
    missing, existing, validated = _preflight(root, directories, files)

    report: dict[str, Any] = {
        "schema_version": 1,
        "dry_run": dry_run,
        "binding_id": binding["binding_id"],
        "workspace_layout": binding["workspace_layout"],
        "batch_id": batch_id,
        "run_id": run_id,
        "skill_commit_at_creation": skill_commit_at_creation,
        "return_contract_version": return_contract_version,
        "coordinator_id": coordinator_id,
        "provenance_trust_model": PROVENANCE_TRUST_MODEL,
        "cryptographic_actor_or_creation_proof": False,
        "warnings": [PROVENANCE_WARNING],
        "created": [],
        "existing": existing,
        "validated": validated,
        "would_create": missing if dry_run else [],
    }
    if dry_run:
        return report

    created: list[str] = []
    for relative in directories:
        target = _safe_target(root, relative)
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise WorkspaceInitError(f"directory target changed during initialization: {relative}")
            continue
        try:
            target.mkdir()
        except FileExistsError:
            if target.is_symlink() or not target.is_dir():
                raise WorkspaceInitError(
                    f"directory target changed during initialization: {relative}"
                )
        except OSError as exc:
            raise WorkspaceInitError(f"cannot create directory {relative}: {exc}") from exc
        else:
            created.append(relative.as_posix() + "/")

    for relative, (expected, validator) in files.items():
        target = _safe_target(root, relative)
        try:
            _write_json_exclusive(target, expected)
        except FileExistsError:
            current = _load_json(target, relative.as_posix())
            validator(current, expected)
            report["existing"].append(relative.as_posix())
            report["validated"].append(relative.as_posix())
        else:
            created.append(relative.as_posix())

    report["created"] = sorted(created)
    report["existing"] = sorted(
        set(report["existing"]).union(item for item in missing if item not in report["created"])
    )
    report["validated"] = sorted(set(report["validated"]))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize a minimal generic multi-thread-coordinator workspace without overwrites."
    )
    parser.add_argument("--project-root", required=True, help="Existing approved project root")
    parser.add_argument("--binding", required=True, help="Validated generic Workspace Binding JSON")
    parser.add_argument("--batch-id", required=True, help="Identifier matching batch_NNNN")
    parser.add_argument("--run-id", required=True, help="Identifier matching run_NNNN")
    parser.add_argument(
        "--skill-commit-at-creation",
        required=True,
        help="Pinned immutable Skill commit or revision attested at run creation",
    )
    parser.add_argument(
        "--coordinator-id",
        required=True,
        help="Canonical native identity of the coordinator that owns acceptance",
    )
    parser.add_argument(
        "--return-contract-version",
        default="task_event_v1",
        choices=sorted(ALLOWED_RETURN_CONTRACT_VERSIONS),
        help="Attested creation-time default return contract for coordinated work",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report planned changes without creating anything",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = initialize(
            args.project_root,
            args.binding,
            args.batch_id,
            args.run_id,
            skill_commit_at_creation=args.skill_commit_at_creation,
            coordinator_id=args.coordinator_id,
            return_contract_version=args.return_contract_version,
            dry_run=args.dry_run,
        )
    except WorkspaceInitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

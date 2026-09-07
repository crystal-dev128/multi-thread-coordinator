#!/usr/bin/env python3
"""Audit persisted coordinator state without mutating it."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import posixpath
import sys
from pathlib import Path
from typing import Any


ALLOWED_WORK_STATUSES = {
    "pending",
    "running",
    "needs_input",
    "blocked",
    "succeeded",
    "failed",
    "superseded",
}
ALLOWED_ACTIVE_KINDS = {
    "task",
    "command",
    "monitor",
    "automation",
    "worktree",
    "external_operation",
}
ALLOWED_SIDE_EFFECT_DISPOSITIONS = {"none", "reused", "superseded", "isolated"}
ALLOWED_CHAIN_MODES = {"staged", "parallel"}
ALLOWED_REVIEW_STATUSES = {"effective", "superseded"}
ALLOWED_OPTIONAL_REVIEW_DISPOSITIONS = {
    "false_positive",
    "nonmaterial",
    "outside_supported_scope",
    "confirmed_material",
}
ALLOWED_CANDIDATE_KINDS = {
    "git",
    "file",
    "directory_manifest",
    "dataset",
    "document",
    "message_result",
}
RETURN_CONTRACT_VERSIONS = {
    "automatic": "automatic_v1",
    "task_event": "task_event_v1",
    "notify": "notify_v1",
    "push": "push_v1",
    "manual": "manual_v1",
}
# Event contracts differ only in what proves the return path is live. Under
# task_event the coordinator waits in-turn, so its first native wait is the
# proof. Under notify the host wakes the coordinator, so the proof is the
# moment that notification path became live for the exact worker.
EVENT_RETURN_MODES = ("task_event", "notify")
RETURN_READY_FIELDS = {
    "task_event": "first_wait_at",
    "notify": "return_armed_at",
}
# Every delivered attempt on these modes runs on a user-visible surface and
# records a native worker identity.
NATIVE_IDENTITY_RETURN_MODES = ("task_event", "notify", "push", "manual")
USER_VISIBLE_TASK_SURFACES = {"user_visible_task", "worktree"}
RETURN_MODE_OWNER_SURFACES = {
    "task_event": USER_VISIBLE_TASK_SURFACES,
    "notify": USER_VISIBLE_TASK_SURFACES,
    "push": USER_VISIBLE_TASK_SURFACES,
    "manual": USER_VISIBLE_TASK_SURFACES,
    "automatic": {"internal_subagent"},
}
PROVENANCE_TRUST_MODEL = "trusted_persisted_attestation"
PROVENANCE_WARNING = (
    "fail_closed_v2 checks structural consistency over trusted persisted writer "
    "attestations; it does not prove actor identity or creation-time history and "
    "cannot detect a coordinated full-record rewrite or backfill"
)
FORBIDDEN_REVIEW_PACKET_KEYS = {
    "desired_verdict",
    "preferred_conclusion",
    "producer_verdict",
    "unsupported_narrative",
}
MAX_REVIEW_PACKET_DEPTH = 64
CURRENT_RUN_SCHEMA_VERSION = 2
LEGACY_RUN_SCHEMA_VERSION = 1
LIST_FIELDS = (
    "chains",
    "tasks",
    "attempts",
    "candidates",
    "evidence",
    "reviews",
    "supersedes",
    "active_work",
)
ATTEMPT_COMMON_FIELDS = {
    "attempt_id",
    "task_id",
    "owner",
    "skill_commit_at_dispatch",
    "return_mode",
    "return_contract_version",
    "delivered_at",
    "returned_at",
    "accepted_at",
    "accepted_by",
    "candidate_id",
    "return_event_received_at",
    "return_reconciled_at",
    "return_reconciled_by",
    "uncertain_at",
    "reconciled_at",
    "retry_of",
    "retry_reason",
    "pre_retry_audit",
    "contract_migration",
}
ATTEMPT_MODE_FIELDS = {
    "task_event": {
        "worker_thread_id",
        "worker_host_id",
        "first_wait_at",
        "return_cursor",
    },
    "notify": {
        "worker_thread_id",
        "worker_host_id",
        "return_armed_at",
    },
    "push": {
        "worker_thread_id",
        "worker_host_id",
        "push_target",
        "push_capability",
        "push_preflight_at",
    },
    "manual": {
        "worker_thread_id",
        "worker_host_id",
        "manual_disclosed_at",
        "manual_disclosure_evidence",
    },
    "automatic": {"automatic_return"},
}
CURRENT_CANDIDATE_FIELDS = {
    "candidate_id",
    "kind",
    "location",
    "scope",
    "identity",
    "produced_by",
    "authority_identities",
    "acceptance_criteria",
    "observed_at",
    "consumes",
    "review_required",
    "source_snapshots",
}
CURRENT_TASK_FIELDS = {
    "task_id",
    "status",
    "owner_surface",
    "depends_on",
    "consumes",
    "current_attempt_id",
    "authority_identities",
    "acceptance_criteria",
    "decisions",
}
CURRENT_ACTIVE_WORK_FIELDS = {
    "active_id",
    "kind",
    "owner",
    "task_id",
    "attempt_id",
    "writes",
    "isolation_key",
}
CURRENT_EVIDENCE_FIELDS = {
    "evidence_id",
    "candidate_id",
    "criterion_id",
    "requirement",
    "result",
    "authority_identities",
    "candidate_identity",
    "kind",
    "method",
    "raw_output",
    "observed_by",
    "observed_at",
}
LATEST_RESULT_FIELDS = {
    "schema_version",
    "run_id",
    "result_manifest",
    "candidate_id",
    "source_digest",
}


class CoordinationAuditError(Exception):
    """Raised when persisted coordination state violates one or more invariants."""

    def __init__(self, errors: list[str], report: dict[str, Any]):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.report = report


def _load_json(path: str | Path, label: str) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist: {target}") from exc
    except (OSError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot read valid JSON from {label}: {target}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {target}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except RecursionError as exc:
        raise ValueError("canonical JSON exceeds the supported nesting depth") from exc
    return hashlib.sha256(encoded).hexdigest()


def _parse_timestamp(
    value: Any,
    label: str,
    errors: list[str],
) -> datetime | None:
    if not _nonempty_string(value):
        errors.append(f"{label} must be a non-empty ISO-8601 timestamp")
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        errors.append(f"{label} must be a valid ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{label} must include a timezone")
        return None
    return parsed


def _require_timestamp_order(
    earlier: datetime | None,
    later: datetime | None,
    later_label: str,
    earlier_label: str,
    errors: list[str],
) -> None:
    if earlier is not None and later is not None and later <= earlier:
        errors.append(f"{later_label} must be strictly after {earlier_label}")


def _require_atomic_observation_order(
    earlier: datetime | None,
    later: datetime | None,
    later_label: str,
    earlier_label: str,
    errors: list[str],
) -> None:
    """Allow equality only when one native response exposes both observations."""

    if earlier is not None and later is not None and later < earlier:
        errors.append(f"{later_label} must not precede {earlier_label}")


def _resolve_project_file(
    project_root: Path,
    value: Any,
    label: str,
    errors: list[str],
) -> Path | None:
    if not _nonempty_string(value):
        errors.append(f"{label} must be a non-empty project path")
        return None
    raw = Path(value)
    target = (raw if raw.is_absolute() else project_root / raw).resolve()
    try:
        target.relative_to(project_root)
    except ValueError:
        errors.append(f"{label} escapes the approved project root: {value}")
        return None
    if not target.is_file():
        errors.append(f"{label} does not identify an existing file: {value}")
        return None
    return target


def _validate_stage_chains(
    chains: list[dict[str, Any]],
    *,
    closure: bool,
    errors: list[str],
) -> list[str]:
    chain_ids: set[str] = set()
    nonterminal_stages: list[str] = []

    for chain_index, chain in enumerate(chains):
        label = f"run.chains[{chain_index}]"
        chain_id = chain.get("chain_id")
        if not _nonempty_string(chain_id):
            errors.append(f"{label}.chain_id must be a non-empty string")
            chain_id = f"index_{chain_index}"
        elif chain_id in chain_ids:
            errors.append(f"duplicate chain_id: {chain_id}")
        else:
            chain_ids.add(chain_id)

        mode = chain.get("mode")
        if not _nonempty_string(mode) or mode not in ALLOWED_CHAIN_MODES:
            errors.append(f"chain {chain_id} has unsupported mode: {mode}")
            continue
        if mode != "staged":
            continue

        outline = _record_list(
            chain.get("stage_outline"), f"chain {chain_id}.stage_outline", errors
        )
        if not outline:
            errors.append(f"staged chain {chain_id} must contain at least one stage")
            continue

        stage_ids: set[str] = set()
        indexed_stages: dict[str, dict[str, Any]] = {}
        ordered_ids: list[str] = []
        running_ids: list[str] = []
        for stage_index, stage in enumerate(outline):
            stage_label = f"chain {chain_id}.stage_outline[{stage_index}]"
            stage_id = stage.get("stage_id")
            if not _nonempty_string(stage_id):
                errors.append(f"{stage_label}.stage_id must be a non-empty string")
                continue
            if stage_id in stage_ids:
                errors.append(f"chain {chain_id} has duplicate stage_id: {stage_id}")
                continue
            stage_ids.add(stage_id)
            indexed_stages[stage_id] = stage
            ordered_ids.append(stage_id)

            status = stage.get("status")
            if not _nonempty_string(status) or status not in ALLOWED_WORK_STATUSES:
                errors.append(f"stage {chain_id}/{stage_id} has unsupported status: {status}")
            elif status == "running":
                running_ids.append(stage_id)
            if status not in ("succeeded", "superseded"):
                nonterminal_stages.append(f"{chain_id}/{stage_id}")

        if len(running_ids) > 1:
            errors.append(
                f"staged chain {chain_id} has more than one running stage: "
                + ", ".join(running_ids)
            )

        unlocked = chain.get("unlocked_stage_id")
        if unlocked is not None and not _nonempty_string(unlocked):
            errors.append(f"chain {chain_id}.unlocked_stage_id must be null or a string")
            unlocked = None
        if unlocked is not None:
            unlocked_stage = indexed_stages.get(unlocked)
            if unlocked_stage is None:
                errors.append(f"chain {chain_id} unlocks unknown stage: {unlocked}")
            elif unlocked_stage.get("status") not in ("pending", "running"):
                errors.append(
                    f"chain {chain_id} unlocked stage {unlocked} must be pending or running"
                )
        if running_ids and unlocked != running_ids[0]:
            errors.append(
                f"chain {chain_id} running stage {running_ids[0]} must be the unlocked stage"
            )

        for stage_index, stage_id in enumerate(ordered_ids):
            stage = indexed_stages[stage_id]
            depends_on_value = stage.get("depends_on")
            if depends_on_value is None:
                dependencies = ordered_ids[stage_index - 1 : stage_index] if stage_index else []
            else:
                dependencies = _string_list(
                    depends_on_value,
                    f"stage {chain_id}/{stage_id}.depends_on",
                    errors,
                )
            for dependency in dependencies:
                if dependency not in indexed_stages:
                    errors.append(
                        f"stage {chain_id}/{stage_id} depends on unknown stage: {dependency}"
                    )
                    continue
                if stage.get("status") in ("running", "succeeded") and indexed_stages[
                    dependency
                ].get("status") != "succeeded":
                    errors.append(
                        f"stage {chain_id}/{stage_id} advanced before dependency "
                        f"{dependency} succeeded"
                    )
                if unlocked == stage_id and indexed_stages[dependency].get("status") != "succeeded":
                    errors.append(
                        f"stage {chain_id}/{stage_id} was unlocked before dependency "
                        f"{dependency} succeeded"
                    )

        if closure:
            if unlocked is not None:
                errors.append(f"closure requires chain {chain_id} to have no unlocked stage")
            unfinished = [
                stage_id
                for stage_id in ordered_ids
                if indexed_stages[stage_id].get("status")
                not in ("succeeded", "superseded")
            ]
            if unfinished:
                errors.append(
                    f"closure requires every stage in chain {chain_id} to be succeeded or "
                    f"superseded: {', '.join(unfinished)}"
                )

    return sorted(nonterminal_stages)


def _validate_result_artifacts(
    run: dict[str, Any],
    latest_result: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    project_root: str | Path,
    errors: list[str],
) -> None:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        errors.append(f"project_root does not identify an existing directory: {root}")
        return

    manifest_path = _resolve_project_file(
        root, latest_result.get("result_manifest"), "latest_result.result_manifest", errors
    )
    if manifest_path is None:
        return
    try:
        manifest = _load_json(manifest_path, "result manifest")
    except ValueError as exc:
        errors.append(str(exc))
        return

    if type(manifest.get("schema_version")) is not int or manifest.get(
        "schema_version"
    ) != 1:
        errors.append("result_manifest.schema_version must be 1")
    for field in ("binding_id", "batch_id", "run_id"):
        if manifest.get(field) != run.get(field):
            errors.append(f"result_manifest.{field} does not match the audited run")
    if manifest.get("current_candidate_id") != latest_result.get("candidate_id"):
        errors.append("result_manifest.current_candidate_id does not match latest_result")

    source_identity = manifest.get("source_digest")
    if not isinstance(source_identity, dict):
        errors.append("result_manifest.source_digest must be an identity object")
        source_value = None
    else:
        source_value = source_identity.get("value")
        if source_identity.get("method") != "sha256" or not _nonempty_string(source_value):
            errors.append("result_manifest.source_digest must contain a sha256 identity")
        elif source_value != latest_result.get("source_digest"):
            errors.append("result_manifest.source_digest does not match latest_result")

    source_path = _resolve_project_file(
        root, manifest.get("source_manifest"), "result_manifest.source_manifest", errors
    )
    if source_path is not None and _nonempty_string(source_value):
        if _sha256_file(source_path) != source_value.casefold():
            errors.append("result_manifest.source_manifest sha256 does not match source_digest")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        errors.append("result_manifest.outputs must be a non-empty list")
        return

    verified_output_identities: set[str] = set()
    for index, output in enumerate(outputs):
        label = f"result_manifest.outputs[{index}]"
        if not isinstance(output, dict):
            errors.append(f"{label} must be an object")
            continue
        path_value = output.get("location")
        output_path = _resolve_project_file(root, path_value, f"{label}.location", errors)
        identity = output.get("identity")
        if not isinstance(identity, dict):
            errors.append(f"{label}.identity must be an object")
            continue
        expected = identity.get("value")
        if identity.get("method") != "sha256" or not _nonempty_string(expected):
            errors.append(f"{label}.identity must contain a sha256 identity")
            continue
        expected = expected.casefold()
        if output_path is None:
            continue
        actual = _sha256_file(output_path)
        if actual != expected:
            errors.append(f"{label} sha256 does not match the actual output")
        else:
            verified_output_identities.add(expected)

        parity_value = output.get("digest_parity_with")
        if parity_value is not None:
            parity_path = _resolve_project_file(
                root, parity_value, f"{label}.digest_parity_with", errors
            )
            if parity_path is not None and _sha256_file(parity_path) != actual:
                errors.append(f"{label} does not have digest parity with {parity_value}")

    candidate = candidates.get(latest_result.get("candidate_id"), {})
    candidate_identity = candidate.get("identity")
    if (
        not isinstance(candidate_identity, dict)
        or candidate_identity.get("method") != "sha256"
        or not _nonempty_string(candidate_identity.get("value"))
    ):
        errors.append("published current candidate identity must use sha256")
    elif candidate_identity["value"].casefold() not in verified_output_identities:
        errors.append(
            "published current candidate sha256 is not represented exactly by a "
            "verified result output"
        )


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty_string(item) for item in value):
        errors.append(f"{label} must be a list of non-empty strings")
        return []
    return value


def _unique_string_list(value: Any, label: str, errors: list[str]) -> list[str]:
    items = _string_list(value, label, errors)
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            errors.append(f"{label} duplicates identity {item}")
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _record_list(value: Any, label: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        records.append(item)
    return records


def _require_exact_fields(
    value: dict[str, Any],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    unsupported = sorted(str(field) for field in value if field not in allowed)
    if unsupported:
        errors.append(f"{label} has unsupported fields: " + ", ".join(unsupported))


def _require_exact_key_set(
    value: dict[str, Any],
    expected: set[str],
    label: str,
    errors: list[str],
) -> bool:
    missing = sorted(expected.difference(value))
    unsupported = sorted(str(field) for field in value if field not in expected)
    details: list[str] = []
    if missing:
        details.append("missing: " + ", ".join(missing))
    if unsupported:
        details.append("unsupported: " + ", ".join(unsupported))
    if details:
        errors.append(f"{label} must contain exactly these fields; " + "; ".join(details))
        return False
    return True


def _creation_snapshot(run: dict[str, Any], established_at: str) -> dict[str, Any]:
    return {
        "schema_version": CURRENT_RUN_SCHEMA_VERSION,
        "run_id": run.get("run_id"),
        "batch_id": run.get("batch_id"),
        "binding_id": run.get("binding_id"),
        "skill_commit_at_creation": run.get("skill_commit_at_creation"),
        "return_contract_version": run.get("return_contract_version"),
        "coordinator_id": run.get("coordinator_id"),
        "established_at": established_at,
        **{field: [] for field in LIST_FIELDS},
    }


def _validate_schema_provenance(
    run: dict[str, Any],
    legacy_run: dict[str, Any] | None,
    errors: list[str],
) -> datetime | None:
    provenance = run.get("schema_provenance")
    if not isinstance(provenance, dict):
        errors.append(
            "run.schema_provenance is required for structural fail_closed_v2 conformance"
        )
        return None

    mode = provenance.get("mode")
    if mode == "created_v2":
        _require_exact_fields(
            provenance,
            {"mode", "established_at", "creation_digest"},
            "run.schema_provenance",
            errors,
        )
        established_at = _parse_timestamp(
            provenance.get("established_at"),
            "run.schema_provenance.established_at",
            errors,
        )
        creation_digest = provenance.get("creation_digest")
        expected_digest = (
            _canonical_sha256(
                _creation_snapshot(run, provenance.get("established_at"))
            )
            if _nonempty_string(provenance.get("established_at"))
            else None
        )
        if (
            not _nonempty_string(creation_digest)
            or expected_digest is None
            or creation_digest.casefold() != expected_digest
        ):
            errors.append(
                "run.schema_provenance.creation_digest does not match the attested empty v2 creation snapshot"
            )
        return established_at

    if mode == "migrated_from_v1":
        _require_exact_fields(
            provenance,
            {
                "mode",
                "established_at",
                "source_run_id",
                "source_run_digest",
                "reason",
                "evidence",
            },
            "run.schema_provenance",
            errors,
        )
        established_at = _parse_timestamp(
            provenance.get("established_at"),
            "run.schema_provenance.established_at",
            errors,
        )
        source_run_id = provenance.get("source_run_id")
        if not _nonempty_string(source_run_id):
            errors.append("run.schema_provenance.source_run_id must be a non-empty string")
        elif source_run_id == run.get("run_id"):
            errors.append("schema migration must create a new v2 run_id")
        if not _nonempty_string(provenance.get("reason")):
            errors.append("run.schema_provenance.reason must be a non-empty string")
        migration_evidence = _string_list(
            provenance.get("evidence"),
            "run.schema_provenance.evidence",
            errors,
        )
        if not migration_evidence:
            errors.append("run.schema_provenance.evidence must not be empty")
        if legacy_run is None:
            errors.append(
                "migrated_from_v1 provenance requires the trusted legacy source record for structural digest comparison"
            )
        else:
            if type(legacy_run.get("schema_version")) is not int or legacy_run.get(
                "schema_version"
            ) != LEGACY_RUN_SCHEMA_VERSION:
                errors.append("schema migration source must remain schema_version 1")
            if legacy_run.get("run_id") != source_run_id:
                errors.append(
                    "run.schema_provenance.source_run_id does not match the supplied trusted legacy source record"
                )
            for field in ("batch_id", "binding_id"):
                if legacy_run.get(field) != run.get(field):
                    errors.append(
                        f"schema migration source {field} does not match the new v2 run"
                    )
            source_digest = provenance.get("source_run_digest")
            if (
                not _nonempty_string(source_digest)
                or source_digest.casefold() != _canonical_sha256(legacy_run)
            ):
                errors.append(
                    "run.schema_provenance.source_run_digest does not match the supplied trusted legacy source record"
                )
        return established_at

    errors.append(
        "run.schema_provenance.mode must be created_v2 or migrated_from_v1"
    )
    return None


def _criterion_map(
    value: Any,
    label: str,
    errors: list[str],
) -> dict[str, str]:
    criteria = _record_list(value, label, errors)
    mapped: dict[str, str] = {}
    for index, criterion in enumerate(criteria):
        row_label = f"{label}[{index}]"
        _require_exact_fields(
            criterion,
            {"criterion_id", "requirement"},
            row_label,
            errors,
        )
        criterion_id = criterion.get("criterion_id")
        requirement = criterion.get("requirement")
        if not _nonempty_string(criterion_id):
            errors.append(f"{row_label}.criterion_id must be a non-empty string")
            continue
        if criterion_id in mapped:
            errors.append(f"{label} duplicates criterion_id {criterion_id}")
            continue
        if not _nonempty_string(requirement):
            errors.append(f"{row_label}.requirement must be a non-empty string")
            continue
        mapped[criterion_id] = requirement
    if not mapped:
        errors.append(f"{label} must contain at least one criterion")
    return mapped


def _reject_recursive_packet_bias(
    value: Any,
    *,
    path: str,
    review_id: str,
    errors: list[str],
) -> bool:
    """Inspect a packet iteratively and reject excessive nesting once."""

    stack: list[tuple[Any, str, int]] = [(value, path, 0)]
    while stack:
        current, current_path, depth = stack.pop()
        if depth > MAX_REVIEW_PACKET_DEPTH:
            errors.append(
                f"review {review_id}.packet exceeds maximum nesting depth "
                f"{MAX_REVIEW_PACKET_DEPTH}"
            )
            return False
        if isinstance(current, dict):
            for key, nested in current.items():
                key_text = str(key)
                nested_path = f"{current_path}.{key_text}"
                if key_text.casefold() in FORBIDDEN_REVIEW_PACKET_KEYS:
                    errors.append(
                        f"review {review_id} contains forbidden verdict-bias key at "
                        f"{nested_path}"
                    )
                stack.append((nested, nested_path, depth + 1))
        elif isinstance(current, list):
            for index, nested in enumerate(current):
                stack.append((nested, f"{current_path}[{index}]", depth + 1))
    return True


def _index_records(
    records: list[dict[str, Any]], id_field: str, label: str, errors: list[str]
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        identity = record.get(id_field)
        if not _nonempty_string(identity):
            errors.append(f"{label}[{index}].{id_field} must be a non-empty string")
            continue
        if identity in indexed:
            errors.append(f"duplicate {id_field}: {identity}")
            continue
        indexed[identity] = record
    return indexed


def _has_windows_drive_prefix(value: str) -> bool:
    return (
        len(value) >= 2
        and value[0].isascii()
        and value[0].isalpha()
        and value[1] == ":"
    )


def _is_authority_token(value: str) -> bool:
    drive_like_prefix = len(value) >= 2 and value[1] == ":"
    return ":" in value and not drive_like_prefix and "/" not in value


def _has_unc_prefix(value: str) -> bool:
    return value.startswith("//") and not value.startswith("///")


def _split_unc_write_root(value: str) -> tuple[str, str] | None:
    """Return a standard UNC server/share anchor and its lexical tail."""

    normalized = value.strip().replace("\\", "/").casefold()
    if not _has_unc_prefix(normalized):
        return None
    parts = [part for part in normalized.lstrip("/").split("/") if part]
    if (
        len(parts) < 2
        or parts[0] in {".", "..", "?"}
        or parts[1] in {".", ".."}
    ):
        return None
    return f"//{parts[0]}/{parts[1]}", "/".join(parts[2:])


def _write_claim_escapes_lexical_root(value: str) -> bool:
    normalized = value.strip().replace("\\", "/").casefold()
    if _is_authority_token(normalized):
        return False
    path = normalized
    if _has_unc_prefix(path):
        unc_path = _split_unc_write_root(path)
        if unc_path is None:
            return True
        _, path = unc_path
    elif (
        _has_windows_drive_prefix(path)
        and len(path) >= 3
        and path[2] == "/"
    ):
        path = path[3:]
    elif path.startswith("/"):
        path = path.lstrip("/")
    depth = 0
    for part in path.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if depth == 0:
                return True
            depth -= 1
        else:
            depth += 1
    return False


def _normalize_write(value: str) -> str:
    normalized = value.strip().replace("\\", "/").casefold()
    if _is_authority_token(normalized):
        return normalized.rstrip("/")
    drive_root = (
        normalized[:2]
        if _has_windows_drive_prefix(normalized)
        and len(normalized) >= 3
        and normalized[2] == "/"
        else None
    )
    unc_path = _split_unc_write_root(normalized)
    if unc_path is not None:
        unc_root, tail = unc_path
        normalized_tail = posixpath.normpath("/" + tail).lstrip("/")
        normalized = (
            f"{unc_root}/{normalized_tail}" if normalized_tail else unc_root
        )
    elif _has_unc_prefix(normalized):
        normalized_tail = posixpath.normpath(
            "/" + normalized.lstrip("/")
        ).lstrip("/")
        normalized = "//" + normalized_tail
    else:
        normalized = posixpath.normpath(normalized)
        if drive_root is not None and normalized == drive_root:
            normalized += "/"
    if normalized == ".":
        return "."
    if normalized == "/":
        return normalized
    if len(normalized) == 3 and normalized[1:] == ":/":
        return normalized
    return normalized.rstrip("/") or "/"


def _write_path_anchor(value: str) -> tuple[str, str] | None:
    """Return the host-independent filesystem namespace and lexical anchor."""

    normalized = _normalize_write(value)
    unc_path = _split_unc_write_root(normalized)
    if unc_path is not None:
        return "unc", unc_path[0]
    if (
        _has_windows_drive_prefix(normalized)
        and len(normalized) >= 3
        and normalized[2] == "/"
    ):
        return "drive", normalized[:2]
    if normalized.startswith("/"):
        return "posix", "/"
    return None


def _write_path_is_within_root(value: str, root: str) -> bool:
    if _write_path_anchor(value) != _write_path_anchor(root):
        return False
    return value == root or value.startswith(root.rstrip("/") + "/")


def _write_claim_type(value: str) -> str:
    normalized = value.strip().replace("\\", "/").casefold()
    if _is_authority_token(normalized):
        return "authority"
    if len(normalized) >= 2 and normalized[1] == ":":
        if not _has_windows_drive_prefix(normalized):
            return "invalid_drive"
        if len(normalized) >= 3 and normalized[2] == "/":
            return "absolute"
        return "drive_relative"
    if _has_unc_prefix(normalized):
        return (
            "absolute"
            if _split_unc_write_root(normalized) is not None
            else "invalid_unc"
        )
    if normalized.startswith("/"):
        return "absolute"
    return "relative"


def _canonicalize_write_claim(
    value: str,
    *,
    project_root: str | Path | None,
    label: str,
    errors: list[str],
) -> tuple[str | None, str]:
    normalized = value.strip().replace("\\", "/").casefold()
    claim_type = _write_claim_type(normalized)
    if claim_type == "authority":
        return _normalize_write(normalized), claim_type
    if claim_type == "drive_relative":
        errors.append(f"{label} must not use a drive-relative path")
        return None, claim_type
    if claim_type == "invalid_drive":
        errors.append(f"{label} must use an ASCII letter for a Windows drive path")
        return None, claim_type
    if claim_type == "invalid_unc":
        errors.append(f"{label} must identify a standard UNC server and share")
        return None, claim_type
    if _write_claim_escapes_lexical_root(normalized):
        errors.append(f"{label} escapes its lexical root")
        return None, claim_type

    canonical = _normalize_write(normalized)
    if project_root is None:
        return canonical, claim_type

    root_text = str(project_root).strip().replace("\\", "/").casefold()
    root_type = _write_claim_type(root_text)
    if root_type != "absolute" or _write_claim_escapes_lexical_root(root_text):
        errors.append(
            "project_root must be an absolute, lexically unambiguous filesystem path "
            "for active-write canonicalization"
        )
        return None, claim_type
    root = _normalize_write(root_text)
    if claim_type == "relative":
        canonical = _normalize_write(root.rstrip("/") + "/" + canonical)

    if not _write_path_is_within_root(canonical, root):
        errors.append(f"{label} escapes project_root")
        return None, claim_type
    return canonical, "absolute"


def _authority_descendant_alias(
    value: str,
    *,
    project_root: str | Path | None,
) -> str | None:
    """Preserve conservative token/descendant overlap after root resolution."""

    normalized = _normalize_write(value)
    claim_type = _write_claim_type(value)
    relative = normalized if claim_type == "relative" else None
    if claim_type == "absolute" and project_root is not None:
        root = _normalize_write(str(project_root))
        prefix = root if root.endswith("/") else root + "/"
        if normalized.startswith(prefix):
            relative = normalized[len(prefix) :]
    if relative is None:
        return None
    authority_root = relative.split("/", 1)[0]
    return relative if _is_authority_token(authority_root) else None


def _writes_overlap(left: str, right: str) -> bool:
    a = _normalize_write(left)
    b = _normalize_write(right)
    if a == b:
        return True

    def is_relative_root(value: str) -> bool:
        return value == "."

    def is_relative_path(value: str) -> bool:
        return not value.startswith("/") and not (
            len(value) >= 3 and value[1] == ":" and value[2] == "/"
        )

    if is_relative_root(a) and is_relative_path(b):
        return True
    if is_relative_root(b) and is_relative_path(a):
        return True

    def is_descendant(child: str, parent: str) -> bool:
        prefix = parent if parent.endswith("/") else parent + "/"
        return child.startswith(prefix)

    return is_descendant(a, b) or is_descendant(b, a)


def _validate_pre_retry_audit(
    attempt_id: str, value: Any, errors: list[str]
) -> None:
    label = f"attempt {attempt_id} pre_retry_audit"
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    if value.get("native_state_checked") is not True:
        errors.append(f"{label} must confirm native_state_checked")
    if value.get("candidate_locations_checked") is not True:
        errors.append(f"{label} must confirm candidate_locations_checked")
    disposition = value.get("side_effects_disposition")
    if (
        not _nonempty_string(disposition)
        or disposition not in ALLOWED_SIDE_EFFECT_DISPOSITIONS
    ):
        errors.append(
            f"{label}.side_effects_disposition must be none, reused, superseded, or isolated"
        )
    evidence = _string_list(value.get("evidence"), f"{label}.evidence", errors)
    if not evidence:
        errors.append(f"{label}.evidence must identify at least one observation")


def _validate_contract_migration(
    attempt_id: str,
    attempt: dict[str, Any],
    attempts: dict[str, dict[str, Any]],
    attempt_delivery_times: dict[str, datetime],
    attempt_first_wait_times: dict[str, datetime],
    errors: list[str],
) -> None:
    label = f"attempt {attempt_id}.contract_migration"
    migration = attempt.get("contract_migration")
    if not isinstance(migration, dict):
        errors.append(
            f"attempt {attempt_id} changes legacy push to task_event without an explicit contract_migration"
        )
        return
    _require_exact_fields(
        migration,
        {
            "from_attempt_id",
            "from_skill_commit",
            "from_return_contract_version",
            "to_skill_commit",
            "to_return_contract_version",
            "migrated_at",
            "reason",
            "evidence",
        },
        label,
        errors,
    )

    source_id = migration.get("from_attempt_id")
    source = attempts.get(source_id) if _nonempty_string(source_id) else None
    if not _nonempty_string(source_id) or source is None:
        errors.append(f"{label}.from_attempt_id must reference a preserved attempt")
    else:
        if attempt.get("retry_of") != source_id:
            errors.append(f"{label}.from_attempt_id must equal retry_of")
        if source.get("task_id") != attempt.get("task_id"):
            errors.append(f"{label} must stay within one task")
        if source.get("return_contract_version") != "push_v1":
            errors.append(f"{label} source attempt must preserve push_v1")
        if migration.get("from_skill_commit") != source.get("skill_commit_at_dispatch"):
            errors.append(f"{label}.from_skill_commit must match the source attempt")

    if migration.get("from_return_contract_version") != "push_v1":
        errors.append(f"{label}.from_return_contract_version must be push_v1")
    if migration.get("to_return_contract_version") != "task_event_v1":
        errors.append(f"{label}.to_return_contract_version must be task_event_v1")
    if migration.get("to_skill_commit") != attempt.get("skill_commit_at_dispatch"):
        errors.append(f"{label}.to_skill_commit must match the migrated attempt")
    if not _nonempty_string(migration.get("reason")):
        errors.append(f"{label}.reason must be a non-empty string")
    evidence = _string_list(migration.get("evidence"), f"{label}.evidence", errors)
    if not evidence:
        errors.append(f"{label}.evidence must identify the migration reconciliation")
    migrated_at = _parse_timestamp(
        migration.get("migrated_at"), f"{label}.migrated_at", errors
    )
    source_delivered_at = (
        attempt_delivery_times.get(source_id) if _nonempty_string(source_id) else None
    )
    replacement_delivered_at = attempt_delivery_times.get(attempt_id)
    replacement_first_wait_at = attempt_first_wait_times.get(attempt_id)
    if source is not None and source_delivered_at is None:
        errors.append(f"{label} source attempt must preserve delivered_at")
    if replacement_delivered_at is None:
        errors.append(f"{label} replacement attempt must record delivered_at")
    if replacement_first_wait_at is None:
        errors.append(f"{label} replacement attempt must record first_wait_at")
    if (
        source_delivered_at is not None
        and migrated_at is not None
        and migrated_at < source_delivered_at
    ):
        errors.append(f"{label}.migrated_at cannot precede source delivered_at")
    if (
        migrated_at is not None
        and replacement_delivered_at is not None
        and migrated_at >= replacement_delivered_at
    ):
        errors.append(
            f"{label}.migrated_at must be strictly before replacement delivered_at"
        )
    _require_timestamp_order(
        replacement_delivered_at,
        replacement_first_wait_at,
        f"{label} replacement first_wait_at",
        "replacement delivered_at",
        errors,
    )


def _validate_retry_graph(
    attempts: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    reported_cycles: set[frozenset[str]] = set()
    for start_id in attempts:
        path: list[str] = []
        positions: dict[str, int] = {}
        current_id = start_id
        while current_id in attempts:
            if current_id in positions:
                cycle = path[positions[current_id] :] + [current_id]
                signature = frozenset(cycle[:-1])
                if signature not in reported_cycles:
                    reported_cycles.add(signature)
                    errors.append(
                        "retry_of lineage contains a cycle: " + " -> ".join(cycle)
                    )
                break
            positions[current_id] = len(path)
            path.append(current_id)
            retry_of = attempts[current_id].get("retry_of")
            if not _nonempty_string(retry_of) or retry_of not in attempts:
                break
            current_id = retry_of


def _retry_ancestors(
    attempt_id: str, attempts: dict[str, dict[str, Any]]
) -> list[str]:
    ancestors: list[str] = []
    seen = {attempt_id}
    current_id = attempt_id
    while True:
        retry_of = attempts.get(current_id, {}).get("retry_of")
        if (
            not _nonempty_string(retry_of)
            or retry_of not in attempts
            or retry_of in seen
        ):
            return ancestors
        ancestors.append(retry_of)
        seen.add(retry_of)
        current_id = retry_of


def _pre_retry_audit_is_complete(value: Any) -> bool:
    disposition = value.get("side_effects_disposition") if isinstance(value, dict) else None
    return bool(
        isinstance(value, dict)
        and value.get("native_state_checked") is True
        and value.get("candidate_locations_checked") is True
        and _nonempty_string(disposition)
        and disposition in ALLOWED_SIDE_EFFECT_DISPOSITIONS
        and isinstance(value.get("evidence"), list)
        and value["evidence"]
        and all(_nonempty_string(item) for item in value["evidence"])
    )


def _supersession_path_to(
    subject_id: str,
    allowed_replacements: set[str],
    supersession_map: dict[str, str],
) -> list[str] | None:
    path = [subject_id]
    seen = {subject_id}
    current_id = subject_id
    while current_id in supersession_map:
        replacement_id = supersession_map[current_id]
        path.append(replacement_id)
        if replacement_id in allowed_replacements:
            return path
        if replacement_id in seen:
            return None
        seen.add(replacement_id)
        current_id = replacement_id
    return None


def _validate_current_review(
    review_id: str,
    review: dict[str, Any],
    *,
    run: dict[str, Any],
    candidate: dict[str, Any],
    producer_attempt: dict[str, Any],
    producer_task: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    start_error_count = len(errors)
    candidate_id = candidate.get("candidate_id")
    producer_owner = producer_attempt.get("owner")
    coordinator_id = run.get("coordinator_id")
    reviewer = review.get("reviewer")
    qualifies = True
    adverse_criteria: set[str] = set()

    review_return_mode = "task_event"
    packet_value = review.get("packet")
    if isinstance(packet_value, dict):
        contract_value = packet_value.get("return_contract")
        if isinstance(contract_value, dict):
            declared_mode = contract_value.get("return_mode")
            if declared_mode in EVENT_RETURN_MODES:
                review_return_mode = declared_mode
    review_ready_field = RETURN_READY_FIELDS[review_return_mode]
    review_mode_fields = (
        {"first_wait_at", "return_cursor"}
        if review_return_mode == "task_event"
        else {"return_armed_at"}
    )

    _require_exact_fields(
        review,
        {
            "review_id",
            "candidate_id",
            "reviewer",
            "review_status",
            "read_only",
            "packet",
            "admitted_at",
            "delivered_at",
            "worker_thread_id",
            "worker_host_id",
            "completed_at",
            "return_event_received_at",
            "returned_at",
            "reconciled_at",
            "reconciled_by",
            "reviewer_actions",
            "criterion_results",
            "open_material_findings",
            "resolution",
            "optional_adjudication",
        }
        | review_mode_fields,
        f"review {review_id}",
        errors,
    )
    review_status = review.get("review_status")
    if (
        not _nonempty_string(review_status)
        or review_status not in ALLOWED_REVIEW_STATUSES
    ):
        errors.append(
            f"review {review_id}.review_status must be effective or superseded"
        )
        qualifies = False
    if review_status == "effective" and review.get("resolution") is not None:
        errors.append(f"effective review {review_id} cannot contain a resolution")
        qualifies = False

    if not _nonempty_string(reviewer):
        errors.append(f"review {review_id}.reviewer must be a non-empty string")
        qualifies = False
    if reviewer == producer_owner:
        errors.append(f"review {review_id} reviewer must differ from the producer")
        qualifies = False
    if reviewer == coordinator_id:
        errors.append(
            f"review {review_id} reviewer must differ from the coordinator for required review"
        )
        qualifies = False
    if producer_owner == coordinator_id:
        errors.append(
            f"review {review_id} producer must differ from the coordinator for required review"
        )
        qualifies = False
    producer_native_identity = (
        producer_attempt.get("worker_host_id"),
        producer_attempt.get("worker_thread_id"),
    )
    reviewer_native_identity = (
        review.get("worker_host_id"),
        review.get("worker_thread_id"),
    )
    if reviewer_native_identity == producer_native_identity:
        errors.append(
            f"review {review_id} native task identity must differ from the producer attempt"
        )
        qualifies = False
    coordinator_target = run.get("coordinator_return_target")
    coordinator_native_identity = (
        coordinator_target.get("host_id"),
        coordinator_target.get("task_id"),
    ) if isinstance(coordinator_target, dict) else (None, None)
    if (
        all(_nonempty_string(item) for item in coordinator_native_identity)
        and coordinator_native_identity == reviewer_native_identity
    ):
        errors.append(
            f"review {review_id} native task identity must differ from the "
            "coordinator return target"
        )
        qualifies = False
    if review.get("read_only") is not True:
        errors.append(f"review {review_id} must be read_only")
        qualifies = False

    packet = review.get("packet")
    if not isinstance(packet, dict):
        errors.append(f"review {review_id}.packet must be an object")
        return {
            "structurally_valid": False,
            "clean": False,
            "event_at": None,
            "reconciled_at": None,
            "admitted_at": None,
            "delivered_at": None,
            "adverse_criteria": adverse_criteria,
            "review_status": review_status,
        }
    allowed_packet_fields = {
        "packet_schema_version",
        "packet_id",
        "packet_digest",
        "correlation",
        "candidate",
        "authority",
        "review_matrix",
        "boundaries",
        "raw_evidence",
        "lineage",
        "return_contract",
    }
    _require_exact_fields(
        packet, allowed_packet_fields, f"review {review_id}.packet", errors
    )
    packet_within_depth = _reject_recursive_packet_bias(
        packet,
        path="packet",
        review_id=review_id,
        errors=errors,
    )
    if not packet_within_depth:
        qualifies = False
    if type(packet.get("packet_schema_version")) is not int or packet.get(
        "packet_schema_version"
    ) != 1:
        errors.append(f"review {review_id}.packet.packet_schema_version must be 1")
        qualifies = False

    if not _nonempty_string(packet.get("packet_id")):
        errors.append(f"review {review_id}.packet.packet_id must be a non-empty string")
    packet_digest = packet.get("packet_digest")
    packet_body = {key: value for key, value in packet.items() if key != "packet_digest"}
    if packet_within_depth:
        try:
            expected_packet_digest = _canonical_sha256(packet_body)
        except ValueError as exc:
            errors.append(f"review {review_id}.packet cannot be canonicalized: {exc}")
            qualifies = False
        else:
            if (
                not _nonempty_string(packet_digest)
                or packet_digest.casefold() != expected_packet_digest
            ):
                errors.append(
                    f"review {review_id}.packet.packet_digest does not match the packet"
                )
                qualifies = False

    correlation = packet.get("correlation")
    if not isinstance(correlation, dict):
        errors.append(f"review {review_id}.packet.correlation must be an object")
        correlation = {}
    _require_exact_fields(
        correlation,
        {
            "batch_id",
            "run_id",
            "task_id",
            "attempt_id",
            "skill_commit_at_creation",
        },
        f"review {review_id}.packet.correlation",
        errors,
    )
    expected_correlation = {
        "batch_id": run.get("batch_id"),
        "run_id": run.get("run_id"),
        "task_id": producer_attempt.get("task_id"),
        "attempt_id": candidate.get("produced_by"),
        "skill_commit_at_creation": run.get("skill_commit_at_creation"),
    }
    for field, expected in expected_correlation.items():
        if correlation.get(field) != expected:
            errors.append(
                f"review {review_id}.packet.correlation.{field} does not match current authority"
            )
            qualifies = False

    packet_candidate = packet.get("candidate")
    if not isinstance(packet_candidate, dict):
        errors.append(f"review {review_id}.packet.candidate must be an object")
        packet_candidate = {}
    _require_exact_fields(
        packet_candidate,
        {"candidate_id", "identity", "scope", "producer", "source_snapshots"},
        f"review {review_id}.packet.candidate",
        errors,
    )
    packet_identity = packet_candidate.get("identity")
    if not isinstance(packet_identity, dict):
        errors.append(f"review {review_id}.packet.candidate.identity must be an object")
    else:
        _require_exact_fields(
            packet_identity,
            {"method", "value", "secondary"},
            f"review {review_id}.packet.candidate.identity",
            errors,
        )
        if "secondary" in packet_identity and isinstance(
            packet_identity.get("secondary"), (dict, list)
        ):
            errors.append(
                f"review {review_id}.packet.candidate.identity.secondary must be a scalar"
            )
    if packet_candidate.get("candidate_id") != candidate_id:
        errors.append(f"review {review_id}.packet candidate_id does not match the candidate")
        qualifies = False
    if packet_candidate.get("identity") != candidate.get("identity"):
        errors.append(f"review {review_id}.packet candidate identity is stale or wrong")
        qualifies = False
    if not _nonempty_string(candidate.get("scope")):
        errors.append(f"candidate {candidate_id}.scope must be a non-empty string")
    if packet_candidate.get("scope") != candidate.get("scope"):
        errors.append(f"review {review_id}.packet candidate scope does not match")
        qualifies = False
    if packet_candidate.get("producer") != producer_owner:
        errors.append(f"review {review_id}.packet producer does not match")
        qualifies = False
    source_snapshots = _string_list(
        candidate.get("source_snapshots"),
        f"candidate {candidate_id}.source_snapshots",
        errors,
    )
    if not source_snapshots:
        errors.append(f"candidate {candidate_id}.source_snapshots must not be empty")
    if packet_candidate.get("source_snapshots") != source_snapshots:
        errors.append(f"review {review_id}.packet source snapshots are stale or wrong")
        qualifies = False

    authority_identities = _string_list(
        producer_task.get("authority_identities"),
        f"task {producer_attempt.get('task_id')}.authority_identities",
        errors,
    )
    if not authority_identities:
        errors.append(
            f"task {producer_attempt.get('task_id')}.authority_identities must not be empty"
        )
    task_decisions = _string_list(
        producer_task.get("decisions", []),
        f"task {producer_attempt.get('task_id')}.decisions",
        errors,
    )
    criterion_requirements = _criterion_map(
        producer_task.get("acceptance_criteria"),
        f"task {producer_attempt.get('task_id')}.acceptance_criteria",
        errors,
    )
    expected_packet_requirements = [
        {
            "criterion_id": criterion_id,
            "requirement": requirement,
        }
        for criterion_id, requirement in criterion_requirements.items()
    ]

    authority = packet.get("authority")
    if not isinstance(authority, dict):
        errors.append(f"review {review_id}.packet.authority must be an object")
        authority = {}
    _require_exact_fields(
        authority,
        {"identities", "requirements", "decisions"},
        f"review {review_id}.packet.authority",
        errors,
    )
    packet_requirements = _record_list(
        authority.get("requirements"),
        f"review {review_id}.packet.authority.requirements",
        errors,
    )
    for index, requirement in enumerate(packet_requirements):
        _require_exact_fields(
            requirement,
            {"criterion_id", "requirement"},
            f"review {review_id}.packet.authority.requirements[{index}]",
            errors,
        )
    if authority.get("identities") != authority_identities:
        errors.append(f"review {review_id}.packet authority identities are stale or wrong")
        qualifies = False
    if packet_requirements != expected_packet_requirements:
        errors.append(f"review {review_id}.packet requirements are stale or incomplete")
        qualifies = False
    if authority.get("decisions") != task_decisions:
        errors.append(f"review {review_id}.packet decisions are stale or incomplete")
        qualifies = False

    matrix = _record_list(
        packet.get("review_matrix"), f"review {review_id}.packet.review_matrix", errors
    )
    matrix_ids: set[str] = set()
    for index, row in enumerate(matrix):
        label = f"review {review_id}.packet.review_matrix[{index}]"
        _require_exact_fields(
            row,
            {"criterion_id", "requirement", "evidence_required"},
            label,
            errors,
        )
        criterion_id = row.get("criterion_id")
        if not _nonempty_string(criterion_id):
            errors.append(f"{label}.criterion_id must be a non-empty string")
            continue
        if criterion_id in matrix_ids:
            errors.append(f"review {review_id} duplicates criterion_id {criterion_id}")
            continue
        matrix_ids.add(criterion_id)
        if row.get("requirement") != criterion_requirements.get(criterion_id):
            errors.append(f"{label}.requirement does not match current acceptance")
        evidence_required = _string_list(
            row.get("evidence_required"), f"{label}.evidence_required", errors
        )
        if not evidence_required:
            errors.append(f"{label}.evidence_required must not be empty")
    if matrix_ids != set(criterion_requirements):
        errors.append(f"review {review_id}.packet review matrix must cover every criterion exactly")
        qualifies = False

    boundaries = packet.get("boundaries")
    if not isinstance(boundaries, dict):
        errors.append(f"review {review_id}.packet.boundaries must be an object")
        boundaries = {}
    _require_exact_fields(
        boundaries,
        {
            "read_only",
            "allowed_reads",
            "required_capabilities",
            "prohibited_actions",
        },
        f"review {review_id}.packet.boundaries",
        errors,
    )
    if boundaries.get("read_only") is not True:
        errors.append(f"review {review_id}.packet boundaries must be read_only")
    for field in ("allowed_reads", "required_capabilities", "prohibited_actions"):
        values = _string_list(
            boundaries.get(field), f"review {review_id}.packet.boundaries.{field}", errors
        )
        if not values:
            errors.append(f"review {review_id}.packet.boundaries.{field} must not be empty")

    raw_evidence = _string_list(
        packet.get("raw_evidence"), f"review {review_id}.packet.raw_evidence", errors
    )
    if not raw_evidence:
        errors.append(f"review {review_id}.packet.raw_evidence must not be empty")
    lineage = packet.get("lineage")
    if not isinstance(lineage, dict):
        errors.append(f"review {review_id}.packet.lineage must be an object")
    else:
        _require_exact_fields(
            lineage,
            {"predecessor_candidates", "protected_behavior"},
            f"review {review_id}.packet.lineage",
            errors,
        )
        _string_list(
            lineage.get("predecessor_candidates", []),
            f"review {review_id}.packet.lineage.predecessor_candidates",
            errors,
        )
        _string_list(
            lineage.get("protected_behavior", []),
            f"review {review_id}.packet.lineage.protected_behavior",
            errors,
        )

    return_contract = packet.get("return_contract")
    if not isinstance(return_contract, dict):
        errors.append(f"review {review_id}.packet.return_contract must be an object")
        return_contract = {}
    _require_exact_fields(
        return_contract,
        {
            "return_mode",
            "return_contract_version",
            "skill_commit_at_dispatch",
            "events",
        },
        f"review {review_id}.packet.return_contract",
        errors,
    )
    if return_contract.get("return_mode") not in EVENT_RETURN_MODES:
        errors.append(
            f"review {review_id} must return through task_event or notify"
        )
    elif return_contract.get("return_contract_version") != RETURN_CONTRACT_VERSIONS[
        return_contract["return_mode"]
    ]:
        errors.append(
            f"review {review_id} return contract must be "
            f"{RETURN_CONTRACT_VERSIONS[return_contract['return_mode']]}"
        )
    if not _nonempty_string(return_contract.get("skill_commit_at_dispatch")):
        errors.append(
            f"review {review_id}.packet.return_contract.skill_commit_at_dispatch must be non-empty"
        )
    events = _string_list(
        return_contract.get("events"),
        f"review {review_id}.packet.return_contract.events",
        errors,
    )
    if events != ["completed", "needs_attention"]:
        errors.append(
            f"review {review_id}.packet.return_contract.events must be completed, needs_attention"
        )
    required_review_fields = ["worker_thread_id", "worker_host_id"]
    if review_return_mode == "task_event":
        # A resumable wait must carry its cursor; a notify event has none.
        required_review_fields.append("return_cursor")
    for field in required_review_fields:
        if not _nonempty_string(review.get(field)):
            errors.append(f"review {review_id}.{field} must be non-empty")
    admitted_at = _parse_timestamp(
        review.get("admitted_at"),
        f"review {review_id}.admitted_at",
        errors,
    )
    delivered_at = _parse_timestamp(
        review.get("delivered_at"),
        f"review {review_id}.delivered_at",
        errors,
    )
    first_wait_at = _parse_timestamp(
        review.get(review_ready_field),
        f"review {review_id}.{review_ready_field}",
        errors,
    )

    actions = review.get("reviewer_actions")
    if not isinstance(actions, dict):
        errors.append(f"review {review_id}.reviewer_actions must be an object")
        actions = {}
    _require_exact_fields(
        actions,
        {
            "mutated_candidate",
            "waived_criteria",
            "unlocked_dependents",
            "updated_current_pointer",
            "accepted_candidate",
        },
        f"review {review_id}.reviewer_actions",
        errors,
    )
    for field in (
        "mutated_candidate",
        "waived_criteria",
        "unlocked_dependents",
        "updated_current_pointer",
        "accepted_candidate",
    ):
        if actions.get(field) is not False:
            errors.append(f"review {review_id}.reviewer_actions.{field} must be false")
            qualifies = False

    results = _record_list(
        review.get("criterion_results"), f"review {review_id}.criterion_results", errors
    )
    result_ids: set[str] = set()
    all_results_pass = True
    for index, result in enumerate(results):
        label = f"review {review_id}.criterion_results[{index}]"
        _require_exact_fields(
            result,
            {"criterion_id", "requirement", "result", "evidence"},
            label,
            errors,
        )
        criterion_id = result.get("criterion_id")
        if not _nonempty_string(criterion_id):
            errors.append(f"{label}.criterion_id must be a non-empty string")
            continue
        if criterion_id in result_ids:
            errors.append(f"review {review_id} duplicates criterion result {criterion_id}")
            continue
        result_ids.add(criterion_id)
        if result.get("requirement") != criterion_requirements.get(criterion_id):
            errors.append(f"{label}.requirement does not match current acceptance")
        if result.get("result") not in ("pass", "fail"):
            errors.append(f"{label}.result must be pass or fail")
            all_results_pass = False
            adverse_criteria.add(criterion_id)
        elif result.get("result") == "fail":
            all_results_pass = False
            adverse_criteria.add(criterion_id)
        result_evidence = _string_list(result.get("evidence"), f"{label}.evidence", errors)
        if not result_evidence:
            errors.append(f"{label}.evidence must not be empty")
    if result_ids != set(criterion_requirements):
        errors.append(f"review {review_id} criterion results must cover every criterion exactly")
        qualifies = False

    findings = review.get("open_material_findings", [])
    if not isinstance(findings, list):
        errors.append(f"review {review_id}.open_material_findings must be a list")
        findings = []
        qualifies = False
    for index, finding in enumerate(findings):
        label = f"review {review_id}.open_material_findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{label} must be an object")
            continue
        _require_exact_fields(
            finding,
            {
                "criterion_id",
                "requirement",
                "expected",
                "observed",
                "location",
                "evidence",
                "impact",
                "requested_delta",
            },
            label,
            errors,
        )
        for field in (
            "criterion_id",
            "requirement",
            "expected",
            "observed",
            "location",
            "evidence",
            "impact",
            "requested_delta",
        ):
            if not _nonempty_string(finding.get(field)):
                errors.append(f"{label}.{field} must be a non-empty string")
        finding_criterion_id = finding.get("criterion_id")
        if _nonempty_string(finding_criterion_id):
            adverse_criteria.add(finding_criterion_id)
            current_requirement = criterion_requirements.get(finding_criterion_id)
            if current_requirement is None:
                errors.append(
                    f"{label}.criterion_id references an unknown current criterion"
                )
            elif (
                _nonempty_string(finding.get("requirement"))
                and finding.get("requirement") != current_requirement
            ):
                errors.append(f"{label}.requirement does not match current acceptance")

    completed_at = _parse_timestamp(
        review.get("completed_at"), f"review {review_id}.completed_at", errors
    )
    event_at = _parse_timestamp(
        review.get("return_event_received_at"),
        f"review {review_id}.return_event_received_at",
        errors,
    )
    returned_at = _parse_timestamp(
        review.get("returned_at"), f"review {review_id}.returned_at", errors
    )
    reconciled_at = _parse_timestamp(
        review.get("reconciled_at"), f"review {review_id}.reconciled_at", errors
    )
    if review.get("reconciled_by") != coordinator_id:
        errors.append(f"review {review_id}.reconciled_by must be the coordinator")
        qualifies = False
    producer_reconciled_at = _parse_timestamp(
        producer_attempt.get("return_reconciled_at"),
        f"review {review_id} producer return_reconciled_at",
        errors,
    )
    _require_timestamp_order(
        producer_reconciled_at,
        admitted_at,
        f"review {review_id} admission",
        "producer return reconciliation",
        errors,
    )
    _require_timestamp_order(
        admitted_at,
        delivered_at,
        f"review {review_id} dispatch",
        "candidate admission",
        errors,
    )
    review_ready_label = (
        "first wait" if review_return_mode == "task_event" else "arming"
    )
    _require_timestamp_order(
        delivered_at,
        first_wait_at,
        f"review {review_id} {review_ready_label}",
        "review dispatch",
        errors,
    )
    _require_timestamp_order(
        first_wait_at,
        completed_at,
        f"review {review_id} completion",
        review_ready_label,
        errors,
    )
    _require_atomic_observation_order(
        completed_at,
        event_at,
        f"review {review_id} return event",
        "completion",
        errors,
    )
    _require_atomic_observation_order(
        event_at,
        returned_at,
        f"review {review_id} returned_at",
        "return event",
        errors,
    )
    _require_timestamp_order(
        returned_at,
        reconciled_at,
        f"review {review_id} reconciliation",
        "returned_at",
        errors,
    )

    structurally_valid = qualifies and len(errors) == start_error_count
    return {
        "structurally_valid": structurally_valid,
        "clean": structurally_valid and all_results_pass and not findings,
        "event_at": event_at,
        "reconciled_at": reconciled_at,
        "admitted_at": admitted_at,
        "delivered_at": delivered_at,
        "adverse_criteria": adverse_criteria,
        "review_status": review_status,
    }


def _validate_review_resolution(
    review_id: str,
    review: dict[str, Any],
    info: dict[str, Any],
    *,
    reviews: dict[str, dict[str, Any]],
    review_infos: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    criterion_requirements: dict[str, str],
    accepted_at: datetime | None,
    coordinator_id: Any,
    errors: list[str],
) -> bool:
    start_error_count = len(errors)
    resolution = review.get("resolution")
    if not isinstance(resolution, dict):
        errors.append(f"superseded review {review_id}.resolution must be an object")
        return False
    _require_exact_fields(
        resolution,
        {
            "replacement_review_id",
            "resolved_by",
            "resolved_at",
            "reason",
            "criterion_resolutions",
        },
        f"review {review_id}.resolution",
        errors,
    )
    adverse_criteria = set(info.get("adverse_criteria", set()))
    if not adverse_criteria:
        errors.append(
            f"superseded review {review_id} must preserve an adverse criterion or finding"
        )
    if resolution.get("resolved_by") != coordinator_id:
        errors.append(f"review {review_id} resolution must be owned by the coordinator")
    if not _nonempty_string(resolution.get("reason")):
        errors.append(f"review {review_id}.resolution.reason must be a non-empty string")

    replacement_id = resolution.get("replacement_review_id")
    replacement: dict[str, Any] | None = None
    replacement_info: dict[str, Any] = {}
    if not _nonempty_string(replacement_id):
        errors.append(
            f"review {review_id}.resolution.replacement_review_id must be a non-empty string"
        )
    else:
        replacement = reviews.get(replacement_id)
        replacement_info = review_infos.get(replacement_id, {})
    if _nonempty_string(replacement_id) and (
        replacement is None or replacement_id == review_id
    ):
        errors.append(
            f"review {review_id}.resolution.replacement_review_id must reference another review"
        )
    elif replacement is not None:
        if replacement.get("candidate_id") != review.get("candidate_id"):
            errors.append(
                f"review {review_id} replacement review must bind the same candidate"
            )
        if replacement_info.get("review_status") != "effective":
            errors.append(
                f"review {review_id} replacement review must remain effective"
            )
        if not replacement_info.get("clean"):
            errors.append(
                f"review {review_id} replacement review must be structurally valid and clean"
            )

    resolved_at = _parse_timestamp(
        resolution.get("resolved_at"),
        f"review {review_id}.resolution.resolved_at",
        errors,
    )
    _require_timestamp_order(
        info.get("reconciled_at"),
        replacement_info.get("admitted_at"),
        f"review {review_id} replacement admission",
        "superseded review reconciliation",
        errors,
    )
    _require_timestamp_order(
        info.get("reconciled_at"),
        resolved_at,
        f"review {review_id} resolution",
        "superseded review reconciliation",
        errors,
    )
    _require_timestamp_order(
        replacement_info.get("reconciled_at"),
        resolved_at,
        f"review {review_id} resolution",
        "replacement review reconciliation",
        errors,
    )
    _require_timestamp_order(
        resolved_at,
        accepted_at,
        f"candidate {review.get('candidate_id')} acceptance",
        f"review {review_id} resolution",
        errors,
    )

    rows = _record_list(
        resolution.get("criterion_resolutions"),
        f"review {review_id}.resolution.criterion_resolutions",
        errors,
    )
    resolved_criteria: set[str] = set()
    for index, row in enumerate(rows):
        label = f"review {review_id}.resolution.criterion_resolutions[{index}]"
        _require_exact_fields(
            row,
            {"criterion_id", "requirement", "evidence_ids"},
            label,
            errors,
        )
        criterion_id = row.get("criterion_id")
        if not _nonempty_string(criterion_id):
            errors.append(f"{label}.criterion_id must be a non-empty string")
            continue
        if criterion_id in resolved_criteria:
            errors.append(f"review {review_id} duplicates resolution for {criterion_id}")
            continue
        resolved_criteria.add(criterion_id)
        if row.get("requirement") != criterion_requirements.get(criterion_id):
            errors.append(f"{label}.requirement does not match current acceptance")
        evidence_ids = _string_list(row.get("evidence_ids"), f"{label}.evidence_ids", errors)
        if not evidence_ids:
            errors.append(f"{label}.evidence_ids must not be empty")
        for evidence_id in evidence_ids:
            evidence_row = evidence.get(evidence_id)
            if (
                evidence_row is None
                or evidence_row.get("candidate_id") != review.get("candidate_id")
                or evidence_row.get("criterion_id") != criterion_id
                or evidence_row.get("result") != "pass"
            ):
                errors.append(
                    f"review {review_id} resolution evidence {evidence_id} does not cover criterion {criterion_id}"
                )
            else:
                evidence_observed_at = _parse_timestamp(
                    evidence_row.get("observed_at"),
                    f"review {review_id} resolution evidence {evidence_id}.observed_at",
                    errors,
                )
                _require_timestamp_order(
                    evidence_observed_at,
                    resolved_at,
                    f"review {review_id} resolution",
                    f"evidence {evidence_id} observation",
                    errors,
                )
    if resolved_criteria != adverse_criteria:
        errors.append(
            f"review {review_id} resolution must cover every adverse criterion exactly"
        )
    return len(errors) == start_error_count


def _validate_optional_review_adjudication(
    review_id: str,
    review: dict[str, Any],
    info: dict[str, Any],
    *,
    candidate: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    criterion_requirements: dict[str, str],
    accepted_at: datetime | None,
    coordinator_id: Any,
    errors: list[str],
) -> bool:
    """Validate coordinator rejection of every adverse criterion in an optional review."""

    start_error_count = len(errors)
    adjudication = review.get("optional_adjudication")
    label = f"review {review_id}.optional_adjudication"
    if not isinstance(adjudication, dict):
        errors.append(f"{label} must be an object")
        return False
    _require_exact_fields(
        adjudication,
        {"adjudicated_by", "adjudicated_at", "reason", "criterion_adjudications"},
        label,
        errors,
    )
    if candidate.get("review_required") is not False:
        errors.append(
            f"{label} is allowed only when candidate.review_required is false"
        )
    if info.get("review_status") != "effective":
        errors.append(f"{label} is allowed only on an effective review")
    if not info.get("structurally_valid"):
        errors.append(f"{label} cannot cure a structurally invalid review")
    if info.get("clean"):
        errors.append(f"{label} cannot discard a clean review")
    adverse_criteria = set(info.get("adverse_criteria", set()))
    if not adverse_criteria:
        errors.append(f"{label} requires at least one adverse criterion")
    if adjudication.get("adjudicated_by") != coordinator_id:
        errors.append(f"{label} must be owned by the coordinator")
    if not _nonempty_string(adjudication.get("reason")):
        errors.append(f"{label}.reason must be a non-empty string")

    adjudicated_at = _parse_timestamp(
        adjudication.get("adjudicated_at"), f"{label}.adjudicated_at", errors
    )
    _require_timestamp_order(
        info.get("reconciled_at"),
        adjudicated_at,
        f"review {review_id} optional adjudication",
        "review reconciliation",
        errors,
    )
    _require_timestamp_order(
        adjudicated_at,
        accepted_at,
        f"candidate {review.get('candidate_id')} acceptance",
        f"review {review_id} optional adjudication",
        errors,
    )

    rows = _record_list(
        adjudication.get("criterion_adjudications"),
        f"{label}.criterion_adjudications",
        errors,
    )
    adjudicated_criteria: set[str] = set()
    all_rejected = True
    for index, row in enumerate(rows):
        row_label = f"{label}.criterion_adjudications[{index}]"
        _require_exact_fields(
            row,
            {
                "criterion_id",
                "requirement",
                "disposition",
                "rationale",
                "evidence_ids",
            },
            row_label,
            errors,
        )
        criterion_id = row.get("criterion_id")
        if not _nonempty_string(criterion_id):
            errors.append(f"{row_label}.criterion_id must be a non-empty string")
            continue
        if criterion_id in adjudicated_criteria:
            errors.append(
                f"review {review_id} duplicates optional adjudication for {criterion_id}"
            )
            continue
        adjudicated_criteria.add(criterion_id)
        if row.get("requirement") != criterion_requirements.get(criterion_id):
            errors.append(f"{row_label}.requirement does not match current acceptance")
        disposition = row.get("disposition")
        if disposition not in ALLOWED_OPTIONAL_REVIEW_DISPOSITIONS:
            errors.append(f"{row_label}.disposition is unsupported")
            all_rejected = False
        elif disposition == "confirmed_material":
            all_rejected = False
        if not _nonempty_string(row.get("rationale")):
            errors.append(f"{row_label}.rationale must be a non-empty string")
        evidence_ids = _unique_string_list(
            row.get("evidence_ids"), f"{row_label}.evidence_ids", errors
        )
        if not evidence_ids:
            errors.append(f"{row_label}.evidence_ids must not be empty")
        for evidence_id in evidence_ids:
            evidence_row = evidence.get(evidence_id)
            if (
                evidence_row is None
                or evidence_row.get("candidate_id") != review.get("candidate_id")
                or evidence_row.get("criterion_id") != criterion_id
                or evidence_row.get("result") != "pass"
            ):
                errors.append(
                    f"review {review_id} optional adjudication evidence {evidence_id} "
                    f"does not cover criterion {criterion_id}"
                )
                continue
            evidence_observed_at = _parse_timestamp(
                evidence_row.get("observed_at"),
                f"review {review_id} optional adjudication evidence "
                f"{evidence_id}.observed_at",
                errors,
            )
            _require_timestamp_order(
                evidence_observed_at,
                adjudicated_at,
                f"review {review_id} optional adjudication",
                f"evidence {evidence_id} observation",
                errors,
            )
    if adjudicated_criteria != adverse_criteria:
        errors.append(
            f"review {review_id} optional adjudication must cover every adverse "
            "criterion exactly"
        )
    return all_rejected and len(errors) == start_error_count


def _build_stale_closure(
    tasks: dict[str, dict[str, Any]],
    attempts: dict[str, dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
    supersedes: list[dict[str, Any]],
    authority_ids: set[str],
    *,
    strict_graph: bool,
    errors: list[str],
) -> tuple[set[str], set[str], set[str], dict[str, str]]:
    identity_types: dict[str, set[str]] = {}
    for kind, identities in (
        ("task", tasks),
        ("attempt", attempts),
        ("candidate", candidates),
    ):
        for identity in identities:
            identity_types.setdefault(identity, set()).add(kind)
    for identity in authority_ids:
        identity_types.setdefault(identity, set()).add("authority")

    supersession_map: dict[str, str] = {}
    valid_subjects: set[str] = set()
    for index, edge in enumerate(supersedes):
        label = f"supersedes[{index}]"
        if strict_graph:
            _require_exact_key_set(
                edge,
                {"subject_id", "replacement_id", "reason"},
                label,
                errors,
            )
        subject_id = edge.get("subject_id")
        replacement_id = edge.get("replacement_id")
        reason = edge.get("reason")
        edge_valid = True
        if not _nonempty_string(subject_id):
            errors.append(f"{label}.subject_id must be a non-empty string")
            edge_valid = False
        if not _nonempty_string(replacement_id):
            errors.append(f"{label}.replacement_id must be a non-empty string")
            edge_valid = False
        elif replacement_id == subject_id:
            errors.append(f"{label} cannot replace an identity with itself")
            edge_valid = False
        if not _nonempty_string(reason):
            errors.append(f"{label}.reason must be a non-empty string")
            edge_valid = False

        if strict_graph:
            endpoint_kinds: dict[str, set[str]] = {}
            for field, identity in (
                ("subject_id", subject_id),
                ("replacement_id", replacement_id),
            ):
                if not _nonempty_string(identity):
                    continue
                kinds = identity_types.get(identity, set())
                if not kinds:
                    errors.append(
                        f"{label}.{field} references unknown identity: {identity}"
                    )
                    edge_valid = False
                elif len(kinds) != 1:
                    errors.append(
                        f"{label}.{field} is ambiguous across identity domains: {identity}"
                    )
                    edge_valid = False
                else:
                    endpoint_kinds[field] = kinds
            if (
                len(endpoint_kinds) == 2
                and endpoint_kinds["subject_id"]
                != endpoint_kinds["replacement_id"]
            ):
                errors.append(
                    f"{label} subject and replacement must remain within one identity domain"
                )
                edge_valid = False
            elif (
                len(endpoint_kinds) == 2
                and endpoint_kinds["subject_id"] == {"attempt"}
                and attempts.get(subject_id, {}).get("task_id")
                != attempts.get(replacement_id, {}).get("task_id")
            ):
                errors.append(
                    f"{label} attempt subject and replacement must stay within one task_id"
                )
                edge_valid = False
        if _nonempty_string(subject_id) and subject_id in supersession_map:
            errors.append(
                f"run.supersedes has multiple replacement edges for {subject_id}"
            )
            edge_valid = False
        if edge_valid and _nonempty_string(subject_id) and _nonempty_string(replacement_id):
            supersession_map[subject_id] = replacement_id
            valid_subjects.add(subject_id)

    reported_cycles: set[frozenset[str]] = set()
    for start in supersession_map:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in supersession_map:
            if current in positions:
                cycle = path[positions[current] :] + [current]
                signature = frozenset(cycle[:-1])
                if signature not in reported_cycles:
                    reported_cycles.add(signature)
                    errors.append(
                        "run.supersedes contains a cycle: " + " -> ".join(cycle)
                    )
                break
            positions[current] = len(path)
            path.append(current)
            current = supersession_map[current]

    stale_ids: set[str] = set(valid_subjects)
    stale_tasks = {
        task_id for task_id, task in tasks.items() if task.get("status") == "superseded"
    }
    stale_candidates: set[str] = set()

    changed = True
    while changed:
        changed = False
        universe = stale_ids | stale_tasks | stale_candidates

        for attempt_id, attempt in attempts.items():
            if attempt_id not in universe:
                continue
            task_id = attempt.get("task_id")
            task = tasks.get(task_id, {})
            if task.get("current_attempt_id") == attempt_id and task_id not in stale_tasks:
                stale_tasks.add(task_id)
                changed = True

        for task_id, task in tasks.items():
            dependencies = task.get("depends_on", [])
            consumes = task.get("consumes", [])
            authorities = _string_list(
                task.get("authority_identities", []),
                f"task {task_id}.authority_identities",
                errors,
            )
            if task_id in universe or any(
                item in universe for item in dependencies + consumes + authorities
            ):
                if task_id not in stale_tasks:
                    stale_tasks.add(task_id)
                    changed = True

        for candidate_id, candidate in candidates.items():
            consumes = candidate.get("consumes", [])
            authorities = _string_list(
                candidate.get("authority_identities", []),
                f"candidate {candidate_id}.authority_identities",
                errors,
            )
            produced_by = candidate.get("produced_by")
            producer = attempts.get(produced_by, {})
            producer_task = producer.get("task_id")
            candidate_is_stale = (
                candidate_id in universe
                or produced_by in universe
                or producer_task in stale_tasks
                or any(item in universe for item in consumes + authorities)
            )
            if candidate_is_stale:
                if candidate_id not in stale_candidates:
                    stale_candidates.add(candidate_id)
                    changed = True
                producer_task_record = tasks.get(producer_task, {})
                producer_attempt = attempts.get(produced_by, {})
                candidate_is_current = (
                    producer_task_record.get("current_attempt_id") == produced_by
                    and producer_attempt.get("candidate_id") == candidate_id
                )
                if (
                    candidate_is_current
                    and _nonempty_string(producer_task)
                    and producer_task not in stale_tasks
                ):
                    stale_tasks.add(producer_task)
                    changed = True

        stale_ids.update(stale_tasks)
        stale_ids.update(stale_candidates)

    return stale_ids, stale_tasks, stale_candidates, supersession_map


def audit_coordination_state(
    run: dict[str, Any],
    *,
    legacy_run: dict[str, Any] | None = None,
    latest_result: dict[str, Any] | None = None,
    recovery: dict[str, Any] | None = None,
    project_root: str | Path | None = None,
    closure: bool = False,
    require_current_contract: bool = False,
) -> dict[str, Any]:
    """Validate a persisted run and return an audit report."""

    errors: list[str] = []
    run_schema_version = run.get("schema_version")
    current_contract = (
        type(run_schema_version) is int
        and run_schema_version == CURRENT_RUN_SCHEMA_VERSION
    )
    if type(run_schema_version) is not int or run_schema_version not in {
        LEGACY_RUN_SCHEMA_VERSION,
        CURRENT_RUN_SCHEMA_VERSION,
    }:
        errors.append("run.schema_version must be 1 or 2")
    if require_current_contract and not current_contract:
        errors.append(
            "current structural fail_closed_v2 conformance requires run.schema_version 2 provenance"
        )
    for field in ("run_id", "batch_id", "binding_id"):
        if not _nonempty_string(run.get(field)):
            errors.append(f"run.{field} must be a non-empty string")
    schema_established_at: datetime | None = None
    if current_contract:
        for field in ("skill_commit_at_creation", "coordinator_id"):
            if not _nonempty_string(run.get(field)):
                errors.append(f"run.{field} must be a non-empty string")
        creation_return_contract = run.get("return_contract_version")
        if (
            not _nonempty_string(creation_return_contract)
            or creation_return_contract not in RETURN_CONTRACT_VERSIONS.values()
        ):
            errors.append(
                "run.return_contract_version must identify a supported creation-time contract"
            )
        schema_established_at = _validate_schema_provenance(run, legacy_run, errors)
        if "waivers" in run:
            errors.append("run waivers are outside the v2 audit contract")

    records: dict[str, list[dict[str, Any]]] = {}
    for field in LIST_FIELDS:
        if current_contract and field not in run:
            errors.append(f"run.{field} is required for schema_version 2")
            value: Any = []
        else:
            value = run.get(field, [])
        records[field] = _record_list(value, f"run.{field}", errors)

    tasks = _index_records(records["tasks"], "task_id", "run.tasks", errors)
    attempts = _index_records(records["attempts"], "attempt_id", "run.attempts", errors)
    candidates = _index_records(
        records["candidates"], "candidate_id", "run.candidates", errors
    )
    evidence = _index_records(records["evidence"], "evidence_id", "run.evidence", errors)
    reviews = _index_records(records["reviews"], "review_id", "run.reviews", errors)
    active_work = _index_records(
        records["active_work"], "active_id", "run.active_work", errors
    )
    coordinator_return_target = run.get("coordinator_return_target")
    coordinator_native_identity: tuple[str, str] | None = None
    if current_contract and coordinator_return_target is not None:
        if not isinstance(coordinator_return_target, dict):
            errors.append(
                "run.coordinator_return_target must be null or an exact task/host object"
            )
        else:
            _require_exact_fields(
                coordinator_return_target,
                {"task_id", "host_id"},
                "run.coordinator_return_target",
                errors,
            )
            target_fields_valid = True
            for field in ("task_id", "host_id"):
                if not _nonempty_string(coordinator_return_target.get(field)):
                    errors.append(
                        f"run.coordinator_return_target.{field} must be a non-empty string"
                    )
                    target_fields_valid = False
            if target_fields_valid:
                coordinator_native_identity = (
                    coordinator_return_target["host_id"],
                    coordinator_return_target["task_id"],
                )
    nonterminal_stages = _validate_stage_chains(
        records["chains"], closure=closure, errors=errors
    )

    criteria_by_task: dict[str, dict[str, str]] = {}
    authorities_by_task: dict[str, list[str]] = {}
    for task_id, source_task in list(tasks.items()):
        task = dict(source_task)
        tasks[task_id] = task
        if current_contract:
            _require_exact_fields(
                task,
                CURRENT_TASK_FIELDS,
                f"task {task_id}",
                errors,
            )
        status = task.get("status")
        if not _nonempty_string(status) or status not in ALLOWED_WORK_STATUSES:
            errors.append(f"task {task_id} has unsupported status: {status}")
        task["depends_on"] = _string_list(
            task.get("depends_on", []), f"task {task_id}.depends_on", errors
        )
        task["consumes"] = _unique_string_list(
            task.get("consumes", []), f"task {task_id}.consumes", errors
        )
        current_attempt_id = task.get("current_attempt_id")
        if current_attempt_id is not None and not _nonempty_string(current_attempt_id):
            errors.append(f"task {task_id}.current_attempt_id must be null or a string")
            task["current_attempt_id"] = None
        if current_contract:
            if "waiver" in task or "waivers" in task:
                errors.append(
                    f"task {task_id} waivers are outside the v2 audit contract"
                )
            authorities = _string_list(
                task.get("authority_identities"),
                f"task {task_id}.authority_identities",
                errors,
            )
            if not authorities:
                errors.append(f"task {task_id}.authority_identities must not be empty")
            task["authority_identities"] = authorities
            authorities_by_task[task_id] = authorities
            criteria_by_task[task_id] = _criterion_map(
                task.get("acceptance_criteria"),
                f"task {task_id}.acceptance_criteria",
                errors,
            )

    if current_contract:
        for task_id, task in tasks.items():
            for dependency_id in task.get("depends_on", []):
                dependency = tasks.get(dependency_id)
                if dependency is None:
                    errors.append(f"task {task_id} depends on unknown task: {dependency_id}")
                elif (
                    task.get("status") in ("running", "succeeded")
                    and dependency.get("status") != "succeeded"
                ):
                    errors.append(
                        f"task {task_id} advanced before dependency {dependency_id} succeeded"
                    )

    unresolved_uncertainty: set[str] = set()
    delivered_not_returned: list[str] = []
    returned_not_accepted: list[str] = []
    unreconciled_returns: list[str] = []
    attempt_delivery_times: dict[str, datetime] = {}
    attempt_first_wait_times: dict[str, datetime] = {}
    attempt_return_reconciled_times: dict[str, datetime] = {}
    attempt_acceptance_times: dict[str, datetime] = {}
    attempt_uncertain_times: dict[str, datetime] = {}
    attempt_uncertainty_reconciled_times: dict[str, datetime] = {}
    attempts_by_task: dict[str, list[str]] = {}
    material_dispatch_times: list[tuple[str, datetime, str]] = []
    return_barriers: list[
        tuple[str, datetime, datetime | None, str]
    ] = []
    for attempt_id, source_attempt in list(attempts.items()):
        attempt = dict(source_attempt)
        attempts[attempt_id] = attempt
        raw_task_id = attempt.get("task_id")
        task_id = raw_task_id if _nonempty_string(raw_task_id) else None
        if task_id is None or task_id not in tasks:
            errors.append(
                f"attempt {attempt_id} references unknown task_id: {raw_task_id}"
            )
            if task_id is None:
                attempt["task_id"] = None
        else:
            attempts_by_task.setdefault(task_id, []).append(attempt_id)
        if not _nonempty_string(attempt.get("owner")):
            errors.append(f"attempt {attempt_id}.owner must be a non-empty string")

        for field in ("delivered_at", "returned_at", "accepted_at", "uncertain_at", "reconciled_at"):
            value = attempt.get(field)
            if value is not None and not _nonempty_string(value):
                errors.append(f"attempt {attempt_id}.{field} must be null or a string")

        delivered_at = attempt.get("delivered_at")
        returned_at = attempt.get("returned_at")
        accepted_at = attempt.get("accepted_at")
        uncertain_at = attempt.get("uncertain_at")
        reconciled_at = attempt.get("reconciled_at")
        raw_candidate_id = attempt.get("candidate_id")
        candidate_id = (
            raw_candidate_id
            if raw_candidate_id is None or _nonempty_string(raw_candidate_id)
            else None
        )
        if raw_candidate_id is not None and candidate_id is None:
            errors.append(
                f"attempt {attempt_id}.candidate_id must be null or a non-empty string"
            )
            attempt["candidate_id"] = None

        if returned_at and not delivered_at:
            errors.append(f"attempt {attempt_id} returned before delivery was recorded")
        if accepted_at and not returned_at:
            errors.append(f"attempt {attempt_id} was accepted without a returned result")
        if accepted_at and not _nonempty_string(candidate_id):
            errors.append(f"attempt {attempt_id} was accepted without a candidate_id")
        if delivered_at and not returned_at:
            delivered_not_returned.append(attempt_id)
        if returned_at and not accepted_at:
            returned_not_accepted.append(attempt_id)
        if uncertain_at and not reconciled_at:
            unresolved_uncertainty.add(attempt_id)
        if reconciled_at and not uncertain_at:
            errors.append(f"attempt {attempt_id} has reconciled_at without uncertain_at")

        if not current_contract:
            continue

        accepted_by = attempt.get("accepted_by")
        if accepted_at and accepted_by != run.get("coordinator_id"):
            errors.append(
                f"attempt {attempt_id}.accepted_by must be the coordinator"
            )
        if accepted_by is not None and not accepted_at:
            errors.append(f"attempt {attempt_id} has accepted_by without accepted_at")

        return_mode = attempt.get("return_mode")
        return_contract_version = attempt.get("return_contract_version")
        expected_contract_version = (
            RETURN_CONTRACT_VERSIONS.get(return_mode)
            if _nonempty_string(return_mode)
            else None
        )
        if expected_contract_version is None:
            errors.append(f"attempt {attempt_id}.return_mode is unsupported: {return_mode}")
        elif return_contract_version != expected_contract_version:
            errors.append(
                f"attempt {attempt_id}.return_contract_version must be {expected_contract_version}"
            )
        if not _nonempty_string(attempt.get("skill_commit_at_dispatch")):
            errors.append(
                f"attempt {attempt_id}.skill_commit_at_dispatch must be a non-empty string"
            )
        if expected_contract_version is not None:
            _require_exact_fields(
                attempt,
                ATTEMPT_COMMON_FIELDS | ATTEMPT_MODE_FIELDS[return_mode],
                f"attempt {attempt_id}",
                errors,
            )

        parsed_delivered = (
            _parse_timestamp(
                delivered_at, f"attempt {attempt_id}.delivered_at", errors
            )
            if delivered_at is not None
            else None
        )
        parsed_returned = (
            _parse_timestamp(
                returned_at, f"attempt {attempt_id}.returned_at", errors
            )
            if returned_at is not None
            else None
        )
        parsed_accepted = (
            _parse_timestamp(
                accepted_at, f"attempt {attempt_id}.accepted_at", errors
            )
            if accepted_at is not None
            else None
        )
        parsed_uncertain = (
            _parse_timestamp(
                uncertain_at, f"attempt {attempt_id}.uncertain_at", errors
            )
            if uncertain_at is not None
            else None
        )
        parsed_uncertainty_reconciled = (
            _parse_timestamp(
                reconciled_at, f"attempt {attempt_id}.reconciled_at", errors
            )
            if reconciled_at is not None
            else None
        )
        if parsed_uncertain is not None:
            attempt_uncertain_times[attempt_id] = parsed_uncertain
        if parsed_uncertainty_reconciled is not None:
            attempt_uncertainty_reconciled_times[attempt_id] = (
                parsed_uncertainty_reconciled
            )
        event_value = attempt.get("return_event_received_at")
        parsed_event = (
            _parse_timestamp(
                event_value,
                f"attempt {attempt_id}.return_event_received_at",
                errors,
            )
            if event_value is not None
            else None
        )
        return_reconciled_value = attempt.get("return_reconciled_at")
        parsed_return_reconciled = (
            _parse_timestamp(
                return_reconciled_value,
                f"attempt {attempt_id}.return_reconciled_at",
                errors,
            )
            if return_reconciled_value is not None
            else None
        )
        if parsed_return_reconciled is not None:
            attempt_return_reconciled_times[attempt_id] = parsed_return_reconciled
        if parsed_delivered is not None:
            attempt_delivery_times[attempt_id] = parsed_delivered
            material_dispatch_times.append(
                (attempt_id, parsed_delivered, f"attempt:{attempt_id}")
            )
            _require_timestamp_order(
                schema_established_at,
                parsed_delivered,
                f"attempt {attempt_id} delivery",
                "attested v2 schema provenance establishment",
                errors,
            )
        if parsed_accepted is not None:
            attempt_acceptance_times[attempt_id] = parsed_accepted
        _require_timestamp_order(
            parsed_delivered,
            parsed_uncertain,
            f"attempt {attempt_id} uncertainty",
            "delivery",
            errors,
        )
        _require_timestamp_order(
            parsed_uncertain,
            parsed_uncertainty_reconciled,
            f"attempt {attempt_id} uncertainty reconciliation",
            "uncertain_at",
            errors,
        )

        task = tasks.get(task_id, {})
        is_current_active = (
            task.get("current_attempt_id") == attempt_id
            and task.get("status") in ("running", "succeeded")
        )
        if is_current_active and delivered_at is None:
            errors.append(
                f"attempt {attempt_id}.delivered_at is required before work is running"
            )
        parsed_first_wait: datetime | None = None
        parsed_push_preflight: datetime | None = None
        parsed_push_capability_verified: datetime | None = None
        parsed_manual_disclosed: datetime | None = None
        if parsed_delivered is not None and task:
            owner_surface = task.get("owner_surface")
            if not _nonempty_string(owner_surface):
                errors.append(
                    f"attempt {attempt_id} delivered work without task {task_id}.owner_surface"
                )
            elif (
                _nonempty_string(return_mode)
                and return_mode in RETURN_MODE_OWNER_SURFACES
            ):
                allowed_surfaces = RETURN_MODE_OWNER_SURFACES[return_mode]
                if owner_surface not in allowed_surfaces:
                    allowed_text = " or ".join(sorted(allowed_surfaces))
                    errors.append(
                        f"attempt {attempt_id} return mode {return_mode} requires task "
                        f"{task_id}.owner_surface to be {allowed_text}"
                    )
        needs_native_identity = bool(
            return_mode in NATIVE_IDENTITY_RETURN_MODES
            and (
                delivered_at is not None
                or is_current_active
                or returned_at
                or accepted_at
                or event_value
            )
        )
        if needs_native_identity:
            for field in ("worker_thread_id", "worker_host_id"):
                if not _nonempty_string(attempt.get(field)):
                    errors.append(
                        f"attempt {attempt_id}.{field} is required for delivered "
                        f"{return_mode} work"
                    )
        if (
            parsed_delivered is not None
            and return_mode in NATIVE_IDENTITY_RETURN_MODES
            and coordinator_native_identity is not None
            and (
                attempt.get("worker_host_id"),
                attempt.get("worker_thread_id"),
            )
            == coordinator_native_identity
        ):
            errors.append(
                f"attempt {attempt_id} native task identity must differ from the "
                "coordinator return target"
            )
        if return_mode in EVENT_RETURN_MODES:
            ready_field = RETURN_READY_FIELDS[return_mode]
            needs_ready_return = bool(
                delivered_at is not None
                or is_current_active
                or returned_at
                or accepted_at
                or event_value
            )
            if needs_ready_return:
                parsed_first_wait = _parse_timestamp(
                    attempt.get(ready_field),
                    f"attempt {attempt_id}.{ready_field}",
                    errors,
                )
                if parsed_first_wait is not None:
                    attempt_first_wait_times[attempt_id] = parsed_first_wait
            # A task-event wait is resumable and must carry its cursor. A notify
            # return is a single host event with nothing to resume from.
            if (
                return_mode == "task_event"
                and event_value is not None
                and not _nonempty_string(attempt.get("return_cursor"))
            ):
                errors.append(
                    f"attempt {attempt_id}.return_cursor is required for a returned task_event"
                )
        elif return_mode == "push":
            coordinator_target = coordinator_return_target
            if not isinstance(coordinator_target, dict):
                errors.append("run.coordinator_return_target must be an object for push return")
                coordinator_target = {}

            push_target = attempt.get("push_target")
            if not isinstance(push_target, dict):
                errors.append(f"attempt {attempt_id}.push_target must be an object")
                push_target = {}
            _require_exact_fields(
                push_target,
                {"task_id", "host_id"},
                f"attempt {attempt_id}.push_target",
                errors,
            )
            if push_target != coordinator_target:
                errors.append(
                    f"attempt {attempt_id}.push_target must match run.coordinator_return_target"
                )

            push_capability = attempt.get("push_capability")
            if not isinstance(push_capability, dict):
                errors.append(f"attempt {attempt_id}.push_capability must be an object")
                push_capability = {}
            _require_exact_fields(
                push_capability,
                {"name", "verified_at", "evidence"},
                f"attempt {attempt_id}.push_capability",
                errors,
            )
            if not _nonempty_string(push_capability.get("name")):
                errors.append(
                    f"attempt {attempt_id}.push_capability.name must be a non-empty string"
                )
            parsed_push_capability_verified = _parse_timestamp(
                push_capability.get("verified_at"),
                f"attempt {attempt_id}.push_capability.verified_at",
                errors,
            )
            capability_evidence = _string_list(
                push_capability.get("evidence"),
                f"attempt {attempt_id}.push_capability.evidence",
                errors,
            )
            if not capability_evidence:
                errors.append(
                    f"attempt {attempt_id}.push_capability.evidence must not be empty"
                )
            parsed_push_preflight = _parse_timestamp(
                attempt.get("push_preflight_at"),
                f"attempt {attempt_id}.push_preflight_at",
                errors,
            )
        elif return_mode == "manual":
            parsed_manual_disclosed = _parse_timestamp(
                attempt.get("manual_disclosed_at"),
                f"attempt {attempt_id}.manual_disclosed_at",
                errors,
            )
            disclosure_evidence = _string_list(
                attempt.get("manual_disclosure_evidence"),
                f"attempt {attempt_id}.manual_disclosure_evidence",
                errors,
            )
            if not disclosure_evidence:
                errors.append(
                    f"attempt {attempt_id}.manual_disclosure_evidence must not be empty"
                )
        elif return_mode == "automatic":
            automatic_return = attempt.get("automatic_return")
            if not isinstance(automatic_return, dict):
                errors.append(f"attempt {attempt_id}.automatic_return must be an object")
                automatic_return = {}
            _require_exact_fields(
                automatic_return,
                {"surface", "parent_coordinator_id", "worker_native_id"},
                f"attempt {attempt_id}.automatic_return",
                errors,
            )
            if automatic_return.get("surface") != "internal_subagent":
                errors.append(
                    f"attempt {attempt_id}.automatic_return.surface must be internal_subagent"
                )
            if automatic_return.get("parent_coordinator_id") != run.get(
                "coordinator_id"
            ):
                errors.append(
                    f"attempt {attempt_id}.automatic_return.parent_coordinator_id must be the coordinator"
                )
            if automatic_return.get("worker_native_id") != attempt.get("owner"):
                errors.append(
                    f"attempt {attempt_id}.automatic_return.worker_native_id must match owner"
                )
            if attempt.get("owner") == run.get("coordinator_id"):
                errors.append(
                    f"attempt {attempt_id} automatic worker must differ from the "
                    "coordinator parent"
                )

        if returned_at and parsed_event is None and return_mode != "manual":
            errors.append(
                f"attempt {attempt_id} returned without a verified native return event"
            )
        if parsed_event is not None and not returned_at:
            errors.append(
                f"attempt {attempt_id} has a return event without returned_at"
            )
        barrier_event = parsed_event
        if return_mode == "manual" and barrier_event is None:
            barrier_event = parsed_returned
        if return_reconciled_value is not None and barrier_event is None:
            errors.append(
                f"attempt {attempt_id} reconciled a return without verified return evidence"
            )
        if return_reconciled_value is not None and attempt.get(
            "return_reconciled_by"
        ) != run.get("coordinator_id"):
            errors.append(
                f"attempt {attempt_id}.return_reconciled_by must be the coordinator"
            )
        if barrier_event is not None:
            return_barriers.append(
                (
                    f"attempt {attempt_id}",
                    barrier_event,
                    parsed_return_reconciled,
                    f"attempt:{attempt_id}",
                )
            )
            if parsed_return_reconciled is None:
                unreconciled_returns.append(attempt_id)
        if accepted_at and parsed_return_reconciled is None:
            errors.append(
                f"attempt {attempt_id} was accepted before the coordinator reconciled its return"
            )

        if return_mode == "push":
            _require_timestamp_order(
                parsed_push_capability_verified,
                parsed_push_preflight,
                f"attempt {attempt_id} push preflight",
                "push capability verification",
                errors,
            )
            _require_timestamp_order(
                parsed_push_preflight,
                parsed_delivered,
                f"attempt {attempt_id} delivery",
                "push preflight",
                errors,
            )
        elif return_mode == "manual":
            _require_timestamp_order(
                parsed_manual_disclosed,
                parsed_delivered,
                f"attempt {attempt_id} delivery",
                "manual disclosure",
                errors,
            )
        if return_mode in EVENT_RETURN_MODES:
            ready_label = "first wait" if return_mode == "task_event" else "arming"
            _require_timestamp_order(
                parsed_delivered,
                parsed_first_wait,
                f"attempt {attempt_id} {ready_label}",
                "delivery",
                errors,
            )
            _require_timestamp_order(
                parsed_first_wait,
                parsed_event,
                f"attempt {attempt_id} return event",
                ready_label,
                errors,
            )
        elif parsed_event is not None:
            _require_timestamp_order(
                parsed_delivered,
                parsed_event,
                f"attempt {attempt_id} return event",
                "delivery",
                errors,
            )
        if parsed_event is not None:
            if return_mode in EVENT_RETURN_MODES:
                _require_atomic_observation_order(
                    parsed_event,
                    parsed_returned,
                    f"attempt {attempt_id} returned_at",
                    "return event",
                    errors,
                )
            else:
                _require_timestamp_order(
                    parsed_event,
                    parsed_returned,
                    f"attempt {attempt_id} returned_at",
                    "return event",
                    errors,
                )
        elif return_mode == "manual":
            _require_timestamp_order(
                parsed_delivered,
                parsed_returned,
                f"attempt {attempt_id} manual return",
                "delivery",
                errors,
            )
        _require_timestamp_order(
            parsed_returned,
            parsed_return_reconciled,
            f"attempt {attempt_id} return reconciliation",
            "returned_at",
            errors,
        )
        _require_timestamp_order(
            parsed_return_reconciled,
            parsed_accepted,
            f"attempt {attempt_id} acceptance",
            "return reconciliation",
            errors,
        )

    if current_contract:
        for task_id, task in tasks.items():
            if task.get("status") == "superseded":
                continue
            delivered_attempts = [
                attempt_id
                for attempt_id in attempts_by_task.get(task_id, [])
                if attempt_id in attempt_delivery_times
            ]
            if not delivered_attempts:
                continue
            current_attempt_id = task.get("current_attempt_id")
            if not _nonempty_string(current_attempt_id):
                errors.append(
                    f"non-superseded task {task_id} with delivered effective work must identify current_attempt_id"
                )
            elif current_attempt_id not in delivered_attempts:
                errors.append(
                    f"task {task_id}.current_attempt_id must identify its delivered effective attempt"
                )

        for task_id, task in tasks.items():
            current_attempt_id = task.get("current_attempt_id")
            effective_attempt_ids = (
                [current_attempt_id, *_retry_ancestors(current_attempt_id, attempts)]
                if _nonempty_string(current_attempt_id) and current_attempt_id in attempts
                else [
                    attempt_id
                    for attempt_id in attempts_by_task.get(task_id, [])
                    if task.get("status") == "superseded"
                    and attempt_id in attempt_delivery_times
                ]
            )
            for child_attempt_id in effective_attempt_ids:
                child_delivery = attempt_delivery_times.get(child_attempt_id)
                if child_delivery is None:
                    continue
                child_delivery_label = (
                    f"task {task_id} delivery"
                    if child_attempt_id == current_attempt_id
                    else (
                        f"task {task_id} superseded attempt {child_attempt_id} delivery"
                        if not _nonempty_string(current_attempt_id)
                        else f"task {task_id} retry ancestor {child_attempt_id} delivery"
                    )
                )
                for dependency_id in task.get("depends_on", []):
                    dependency = tasks.get(dependency_id)
                    if dependency is None:
                        continue
                    dependency_attempt_id = dependency.get("current_attempt_id")
                    dependency_attempt = attempts.get(dependency_attempt_id, {})
                    dependency_acceptance = attempt_acceptance_times.get(
                        dependency_attempt_id
                    )
                    if (
                        dependency_acceptance is None
                        or dependency_attempt.get("accepted_by")
                        != run.get("coordinator_id")
                    ):
                        if child_attempt_id == current_attempt_id:
                            errors.append(
                                f"task {task_id} delivered before dependency "
                                f"{dependency_id} had current coordinator acceptance"
                            )
                        elif _nonempty_string(current_attempt_id):
                            errors.append(
                                f"task {task_id} retry ancestor {child_attempt_id} "
                                f"delivered before dependency {dependency_id} had current "
                                "coordinator acceptance"
                            )
                        else:
                            errors.append(
                                f"task {task_id} superseded attempt {child_attempt_id} "
                                f"delivered before dependency {dependency_id} had current "
                                "coordinator acceptance"
                            )
                        continue
                    _require_timestamp_order(
                        dependency_acceptance,
                        child_delivery,
                        child_delivery_label,
                        f"dependency {dependency_id} coordinator acceptance",
                        errors,
                    )

    criteria_by_candidate: dict[str, dict[str, str]] = {}
    authorities_by_candidate: dict[str, list[str]] = {}
    candidate_observed_times: dict[str, datetime] = {}
    for candidate_id, source_candidate in list(candidates.items()):
        candidate = dict(source_candidate)
        candidates[candidate_id] = candidate
        if current_contract:
            _require_exact_fields(
                candidate,
                CURRENT_CANDIDATE_FIELDS,
                f"candidate {candidate_id}",
                errors,
            )
            candidate_kind = candidate.get("kind")
            if (
                not _nonempty_string(candidate_kind)
                or candidate_kind not in ALLOWED_CANDIDATE_KINDS
            ):
                errors.append(
                    f"candidate {candidate_id}.kind must be one of: "
                    + ", ".join(sorted(ALLOWED_CANDIDATE_KINDS))
                )
            for field in ("location", "scope"):
                if not _nonempty_string(candidate.get(field)):
                    errors.append(
                        f"candidate {candidate_id}.{field} must be a non-empty string"
                    )
            observed_at = _parse_timestamp(
                candidate.get("observed_at"),
                f"candidate {candidate_id}.observed_at",
                errors,
            )
            if observed_at is not None:
                candidate_observed_times[candidate_id] = observed_at
        produced_by = candidate.get("produced_by")
        if not _nonempty_string(produced_by):
            errors.append(f"candidate {candidate_id} references unknown produced_by: {produced_by}")
            produced_by = None
            candidate["produced_by"] = None
        elif produced_by not in attempts:
            errors.append(f"candidate {candidate_id} references unknown produced_by: {produced_by}")
        candidate["consumes"] = _unique_string_list(
            candidate.get("consumes", []), f"candidate {candidate_id}.consumes", errors
        )
        identity = candidate.get("identity")
        if not isinstance(identity, dict):
            errors.append(f"candidate {candidate_id}.identity must be an object")
        else:
            if current_contract:
                _require_exact_fields(
                    identity,
                    {"method", "value", "secondary"},
                    f"candidate {candidate_id}.identity",
                    errors,
                )
            if not _nonempty_string(identity.get("method")):
                errors.append(f"candidate {candidate_id}.identity.method must be a string")
            if not _nonempty_string(identity.get("value")):
                errors.append(f"candidate {candidate_id}.identity.value must be a string")
        if current_contract and type(candidate.get("review_required")) is not bool:
            errors.append(f"candidate {candidate_id}.review_required must be boolean")
        elif "review_required" in candidate and not isinstance(
            candidate["review_required"], bool
        ):
            errors.append(f"candidate {candidate_id}.review_required must be boolean")
        if current_contract:
            if "waiver" in candidate or "waivers" in candidate:
                errors.append(
                    f"candidate {candidate_id} waivers are outside the v2 audit contract"
                )
            producer_attempt = attempts.get(produced_by, {})
            producer_task_id = producer_attempt.get("task_id")
            task_criteria = criteria_by_task.get(producer_task_id, {})
            candidate_criteria = _criterion_map(
                candidate.get("acceptance_criteria"),
                f"candidate {candidate_id}.acceptance_criteria",
                errors,
            )
            criteria_by_candidate[candidate_id] = candidate_criteria
            if candidate_criteria != task_criteria:
                errors.append(
                    f"candidate {candidate_id}.acceptance_criteria do not match the current task criteria"
                )
            candidate_authorities = _string_list(
                candidate.get("authority_identities"),
                f"candidate {candidate_id}.authority_identities",
                errors,
            )
            candidate["authority_identities"] = candidate_authorities
            authorities_by_candidate[candidate_id] = candidate_authorities
            if candidate_authorities != authorities_by_task.get(producer_task_id, []):
                errors.append(
                    f"candidate {candidate_id}.authority_identities do not match current task authority"
                )

    if current_contract:
        for attempt_id, attempt in attempts.items():
            candidate_id = attempt.get("candidate_id")
            if candidate_id is None:
                continue
            if not _nonempty_string(candidate_id):
                errors.append(
                    f"attempt {attempt_id}.candidate_id must be null or a non-empty string"
                )
                continue
            candidate = candidates.get(candidate_id)
            if candidate is None:
                errors.append(
                    f"attempt {attempt_id}.candidate_id references unknown candidate {candidate_id}"
                )
            elif candidate.get("produced_by") != attempt_id:
                errors.append(
                    f"attempt {attempt_id}.candidate_id {candidate_id} does not match "
                    "candidate.produced_by"
                )
        for candidate_id, candidate in candidates.items():
            produced_by = candidate.get("produced_by")
            producer = attempts.get(produced_by, {})
            if producer.get("candidate_id") != candidate_id:
                errors.append(
                    f"candidate {candidate_id}.produced_by {produced_by} is not linked "
                    "back by attempt.candidate_id"
                )

    if current_contract:
        def require_consumed_candidate_acceptance(
            consumed_candidate_id: str,
            *,
            consumer_label: str,
            child_delivery: datetime,
            child_delivery_label: str,
        ) -> None:
            source_candidate = candidates[consumed_candidate_id]
            source_attempt_id = source_candidate.get("produced_by")
            source_attempt = attempts.get(source_attempt_id, {})
            source_task_id = source_attempt.get("task_id")
            source_task = tasks.get(source_task_id, {})
            source_acceptance = attempt_acceptance_times.get(source_attempt_id)
            source_is_current_accepted = (
                _nonempty_string(source_attempt_id)
                and source_task.get("current_attempt_id") == source_attempt_id
                and source_task.get("status") == "succeeded"
                and source_attempt.get("candidate_id") == consumed_candidate_id
                and source_attempt.get("accepted_by") == run.get("coordinator_id")
                and source_acceptance is not None
            )
            if not source_is_current_accepted:
                errors.append(
                    f"{consumer_label} consumed candidate {consumed_candidate_id} before its "
                    "producer had current coordinator acceptance"
                )
                return
            _require_timestamp_order(
                source_acceptance,
                child_delivery,
                child_delivery_label,
                f"consumed candidate {consumed_candidate_id} coordinator acceptance",
                errors,
            )

        def validate_consumed_identity(
            consumed_id: str,
            *,
            consumer_label: str,
            declared_authorities: list[str],
            child_delivery: datetime | None,
            child_delivery_label: str,
        ) -> None:
            is_candidate = consumed_id in candidates
            is_authority = consumed_id in declared_authorities
            if is_candidate and is_authority:
                errors.append(
                    f"{consumer_label}.consumes identity {consumed_id} is ambiguous "
                    "between candidate and declared authority"
                )
                return
            if not is_candidate and not is_authority:
                errors.append(
                    f"{consumer_label}.consumes identity {consumed_id} is neither a "
                    "known candidate nor a declared authority"
                )
                return
            if is_candidate and child_delivery is not None:
                require_consumed_candidate_acceptance(
                    consumed_id,
                    consumer_label=consumer_label,
                    child_delivery=child_delivery,
                    child_delivery_label=child_delivery_label,
                )

        for task_id, task in tasks.items():
            current_attempt_id = task.get("current_attempt_id")
            effective_attempt_ids = (
                [current_attempt_id, *_retry_ancestors(current_attempt_id, attempts)]
                if _nonempty_string(current_attempt_id) and current_attempt_id in attempts
                else [
                    attempt_id
                    for attempt_id in attempts_by_task.get(task_id, [])
                    if task.get("status") == "superseded"
                    and attempt_id in attempt_delivery_times
                ]
            )
            delivered_children = [
                attempt_id
                for attempt_id in effective_attempt_ids
                if attempt_id in attempt_delivery_times
            ]
            if not delivered_children:
                delivered_children = [None]
            for child_attempt_id in delivered_children:
                child_delivery = attempt_delivery_times.get(child_attempt_id)
                child_delivery_label = (
                    f"task {task_id} delivery"
                    if child_attempt_id in {None, current_attempt_id}
                    else (
                        f"task {task_id} superseded attempt {child_attempt_id} delivery"
                        if not _nonempty_string(current_attempt_id)
                        else f"task {task_id} retry ancestor {child_attempt_id} delivery"
                    )
                )
                for consumed_id in task.get("consumes", []):
                    validate_consumed_identity(
                        consumed_id,
                        consumer_label=f"task {task_id}",
                        declared_authorities=authorities_by_task.get(task_id, []),
                        child_delivery=child_delivery,
                        child_delivery_label=child_delivery_label,
                    )

        for candidate_id, candidate in candidates.items():
            producing_attempt_id = candidate.get("produced_by")
            child_delivery = attempt_delivery_times.get(producing_attempt_id)
            for consumed_id in candidate.get("consumes", []):
                validate_consumed_identity(
                    consumed_id,
                    consumer_label=f"candidate {candidate_id}",
                    declared_authorities=authorities_by_candidate.get(candidate_id, []),
                    child_delivery=child_delivery,
                    child_delivery_label=(
                        f"candidate {candidate_id} production delivery"
                    ),
                )

    evidence_by_candidate: dict[str, list[str]] = {}
    evidence_criteria_by_candidate: dict[str, dict[str, str]] = {}
    for evidence_id, item in evidence.items():
        candidate_id = item.get("candidate_id")
        if not _nonempty_string(candidate_id) or candidate_id not in candidates:
            errors.append(f"evidence {evidence_id} references unknown candidate_id: {candidate_id}")
            continue
        evidence_by_candidate.setdefault(candidate_id, []).append(evidence_id)
        if not current_contract:
            continue

        _require_exact_fields(
            item,
            CURRENT_EVIDENCE_FIELDS,
            f"evidence {evidence_id}",
            errors,
        )
        if "waiver" in item or "waivers" in item:
            errors.append(f"evidence {evidence_id} waivers are outside the v2 audit contract")
        criterion_id = item.get("criterion_id")
        criterion_requirements = criteria_by_candidate.get(candidate_id, {})
        if not _nonempty_string(criterion_id):
            errors.append(f"evidence {evidence_id}.criterion_id must be a non-empty string")
        elif criterion_id not in criterion_requirements:
            errors.append(
                f"evidence {evidence_id} references an unknown current criterion"
            )
        else:
            covered = evidence_criteria_by_candidate.setdefault(candidate_id, {})
            if criterion_id in covered:
                errors.append(
                    f"candidate {candidate_id} duplicates evidence for criterion {criterion_id}"
                )
            else:
                covered[criterion_id] = evidence_id
            if item.get("requirement") != criterion_requirements[criterion_id]:
                errors.append(
                    f"evidence {evidence_id}.requirement does not match current acceptance"
                )
        if item.get("result") != "pass":
            errors.append(f"evidence {evidence_id}.result must be pass")
        evidence_authorities = _string_list(
            item.get("authority_identities"),
            f"evidence {evidence_id}.authority_identities",
            errors,
        )
        if evidence_authorities != authorities_by_candidate.get(candidate_id, []):
            errors.append(f"evidence {evidence_id} authority binding is stale or wrong")
        evidence_identity = item.get("candidate_identity")
        if not isinstance(evidence_identity, dict):
            errors.append(f"evidence {evidence_id}.candidate_identity must be an object")
        else:
            _require_exact_fields(
                evidence_identity,
                {"method", "value", "secondary"},
                f"evidence {evidence_id}.candidate_identity",
                errors,
            )
            if evidence_identity != candidates[candidate_id].get("identity"):
                errors.append(
                    f"evidence {evidence_id} candidate identity is stale or wrong"
                )
        for field in ("kind", "method", "raw_output", "observed_by"):
            if not _nonempty_string(item.get(field)):
                errors.append(f"evidence {evidence_id}.{field} must be a non-empty string")
        observed_at = _parse_timestamp(
            item.get("observed_at"), f"evidence {evidence_id}.observed_at", errors
        )
        producer_attempt_id = candidates[candidate_id].get("produced_by")
        _require_timestamp_order(
            observed_at,
            attempt_acceptance_times.get(producer_attempt_id),
            f"candidate {candidate_id} acceptance",
            f"evidence {evidence_id} observation",
            errors,
        )

    if current_contract:
        for candidate_id, criterion_requirements in criteria_by_candidate.items():
            covered_ids = set(evidence_criteria_by_candidate.get(candidate_id, {}))
            if covered_ids != set(criterion_requirements):
                errors.append(
                    f"candidate {candidate_id} evidence must cover every criterion exactly"
                )

    reviews_by_candidate: dict[str, list[dict[str, Any]]] = {}
    qualifying_current_reviews: set[str] = set()
    current_review_reconciled_times: dict[str, datetime] = {}
    review_infos: dict[str, dict[str, Any]] = {}
    for review_id, review in reviews.items():
        candidate_id = review.get("candidate_id")
        if not _nonempty_string(candidate_id) or candidate_id not in candidates:
            errors.append(f"review {review_id} references unknown candidate_id: {candidate_id}")
            continue
        if current_contract:
            candidate = candidates[candidate_id]
            producer_attempt = attempts.get(candidate.get("produced_by"), {})
            producer_task = tasks.get(producer_attempt.get("task_id"), {})
            info = _validate_current_review(
                review_id,
                review,
                run=run,
                candidate=candidate,
                producer_attempt=producer_attempt,
                producer_task=producer_task,
                errors=errors,
            )
            review_infos[review_id] = info
            event_at = info.get("event_at")
            reconciled_at = info.get("reconciled_at")
            delivered_at = info.get("delivered_at")
            if info.get("clean") and info.get("review_status") == "effective":
                qualifying_current_reviews.add(review_id)
                if reconciled_at is not None:
                    current_review_reconciled_times[review_id] = reconciled_at
            if delivered_at is not None:
                material_dispatch_times.append(
                    (
                        f"review {review_id}",
                        delivered_at,
                        f"review:{review_id}",
                    )
                )
                _require_timestamp_order(
                    schema_established_at,
                    delivered_at,
                    f"review {review_id} dispatch",
                    "attested v2 schema provenance establishment",
                    errors,
                )
            if event_at is not None:
                return_barriers.append(
                    (
                        f"review {review_id}",
                        event_at,
                        reconciled_at,
                        f"review:{review_id}",
                    )
                )
                if reconciled_at is None:
                    unreconciled_returns.append(review_id)
        else:
            if not _nonempty_string(review.get("reviewer")):
                errors.append(f"review {review_id}.reviewer must be a non-empty string")
            if not isinstance(review.get("read_only"), bool):
                errors.append(f"review {review_id}.read_only must be boolean")
            completed_at = review.get("completed_at")
            if completed_at is not None and not _nonempty_string(completed_at):
                errors.append(f"review {review_id}.completed_at must be null or a string")
            _string_list(
                review.get("requirements", []),
                f"review {review_id}.requirements",
                errors,
            )
            _string_list(
                review.get("evidence", []), f"review {review_id}.evidence", errors
            )
            findings = review.get("open_material_findings", [])
            if not isinstance(findings, list):
                errors.append(f"review {review_id}.open_material_findings must be a list")
        reviews_by_candidate.setdefault(candidate_id, []).append(review)

    cleared_optional_review_ids: set[str] = set()
    if current_contract:
        for review_id, review in reviews.items():
            info = review_infos.get(review_id, {})
            if info.get("review_status") != "superseded":
                continue
            candidate_id = review.get("candidate_id")
            candidate = candidates.get(candidate_id, {})
            producer_attempt_id = candidate.get("produced_by")
            _validate_review_resolution(
                review_id,
                review,
                info,
                reviews=reviews,
                review_infos=review_infos,
                evidence=evidence,
                criterion_requirements=criteria_by_candidate.get(candidate_id, {}),
                accepted_at=attempt_acceptance_times.get(producer_attempt_id),
                coordinator_id=run.get("coordinator_id"),
                errors=errors,
            )

        for review_id, review in reviews.items():
            if review.get("optional_adjudication") is None:
                continue
            candidate_id = review.get("candidate_id")
            if not _nonempty_string(candidate_id) or candidate_id not in candidates:
                continue
            candidate = candidates.get(candidate_id, {})
            producer_attempt_id = candidate.get("produced_by")
            if _validate_optional_review_adjudication(
                review_id,
                review,
                review_infos.get(review_id, {}),
                candidate=candidate,
                evidence=evidence,
                criterion_requirements=criteria_by_candidate.get(candidate_id, {}),
                accepted_at=attempt_acceptance_times.get(producer_attempt_id),
                coordinator_id=run.get("coordinator_id"),
                errors=errors,
            ):
                cleared_optional_review_ids.add(review_id)

        authorized_reviewers_by_candidate: dict[str, set[str]] = {}
        for review_id, review in reviews.items():
            info = review_infos.get(review_id, {})
            reviewer = review.get("reviewer")
            candidate_id = review.get("candidate_id")
            if (
                _nonempty_string(candidate_id)
                and _nonempty_string(reviewer)
                and info.get("structurally_valid") is True
                and info.get("review_status") == "effective"
            ):
                authorized_reviewers_by_candidate.setdefault(candidate_id, set()).add(
                    reviewer
                )
        for evidence_id, item in evidence.items():
            candidate_id = item.get("candidate_id")
            observer = item.get("observed_by")
            if (
                _nonempty_string(candidate_id)
                and _nonempty_string(observer)
                and observer != run.get("coordinator_id")
                and observer
                not in authorized_reviewers_by_candidate.get(candidate_id, set())
            ):
                errors.append(
                    f"evidence {evidence_id}.observed_by {observer} is not authorized "
                    f"for candidate {candidate_id}"
                )

    for attempt_id, attempt in attempts.items():
        retry_of = attempt.get("retry_of")
        retry_reason = attempt.get("retry_reason")
        if retry_of is None:
            if retry_reason is not None or attempt.get("pre_retry_audit") is not None:
                errors.append(f"attempt {attempt_id} has retry fields without retry_of")
            continue
        if not _nonempty_string(retry_of) or retry_of not in attempts:
            errors.append(f"attempt {attempt_id} references unknown retry_of: {retry_of}")
        elif retry_of == attempt_id:
            errors.append(f"attempt {attempt_id} cannot retry itself")
        else:
            prior = attempts[retry_of]
            if prior.get("task_id") != attempt.get("task_id"):
                errors.append(f"attempt {attempt_id} retries an attempt from another task")
            if prior.get("accepted_at"):
                errors.append(f"attempt {attempt_id} retries already accepted attempt {retry_of}")
            if prior.get("uncertain_at") and not prior.get("reconciled_at"):
                errors.append(
                    f"attempt {attempt_id} retries unresolved uncertain attempt {retry_of}"
                )
            if current_contract and attempt_id in attempt_delivery_times:
                if retry_of not in attempt_delivery_times:
                    errors.append(
                        f"attempt {attempt_id} retries undelivered attempt {retry_of}"
                    )
                else:
                    _require_timestamp_order(
                        attempt_delivery_times[retry_of],
                        attempt_delivery_times[attempt_id],
                        f"attempt {attempt_id} delivery",
                        f"retry_of attempt {retry_of} delivery",
                        errors,
                    )
                    if (
                        retry_of in attempt_uncertain_times
                        and retry_of in attempt_uncertainty_reconciled_times
                    ):
                        _require_timestamp_order(
                            attempt_uncertainty_reconciled_times[retry_of],
                            attempt_delivery_times[attempt_id],
                            f"attempt {attempt_id} delivery",
                            f"retry_of attempt {retry_of} uncertainty reconciliation",
                            errors,
                        )
        if not _nonempty_string(retry_reason):
            errors.append(f"attempt {attempt_id}.retry_reason must be a non-empty string")
        _validate_pre_retry_audit(attempt_id, attempt.get("pre_retry_audit"), errors)

    _validate_retry_graph(attempts, errors)

    if current_contract:
        validated_migration_ids: set[str] = set()

        def unresolved_pushes_at(
            task_id: str, boundary: datetime
        ) -> list[tuple[datetime, str]]:
            unresolved: list[tuple[datetime, str]] = []
            for source_id in attempts_by_task.get(task_id, []):
                source = attempts[source_id]
                source_delivery = attempt_delivery_times.get(source_id)
                if (
                    source.get("return_contract_version") != "push_v1"
                    or source_delivery is None
                    or source_delivery > boundary
                ):
                    continue
                reconciliation_times = [
                    value
                    for value in (
                        attempt_return_reconciled_times.get(source_id),
                        attempt_uncertainty_reconciled_times.get(source_id),
                    )
                    if value is not None
                ]
                if not any(value < boundary for value in reconciliation_times):
                    unresolved.append((source_delivery, source_id))
            unresolved.sort(key=lambda item: (item[0], item[1]))
            return unresolved

        migration_children_by_source: dict[str, list[str]] = {}
        migration_transitions_by_task: dict[str, list[str]] = {}
        for possible_migration_id, possible_migration in attempts.items():
            source_id = possible_migration.get("retry_of")
            source = (
                attempts.get(source_id, {})
                if _nonempty_string(source_id)
                else {}
            )
            if (
                possible_migration.get("return_contract_version") == "task_event_v1"
                and source.get("return_contract_version") == "push_v1"
            ):
                migration_children_by_source.setdefault(source_id, []).append(
                    possible_migration_id
                )
                task_id = possible_migration.get("task_id")
                if _nonempty_string(task_id):
                    migration_transitions_by_task.setdefault(task_id, []).append(
                        possible_migration_id
                    )
        for task_id, transition_ids in migration_transitions_by_task.items():
            if len(transition_ids) > 1:
                errors.append(
                    f"task {task_id} has multiple push_v1 to task_event_v1 migration "
                    "transitions: " + ", ".join(sorted(transition_ids))
                )
        for source_id, migration_children in migration_children_by_source.items():
            if len(migration_children) > 1:
                errors.append(
                    f"push_v1 attempt {source_id} has multiple task_event migration "
                    "transitions: " + ", ".join(sorted(migration_children))
                )
            for migration_id in migration_children:
                migration = attempts[migration_id]
                _validate_contract_migration(
                    migration_id,
                    migration,
                    attempts,
                    attempt_delivery_times,
                    attempt_first_wait_times,
                    errors,
                )
                validated_migration_ids.add(migration_id)
                transition_delivery = attempt_delivery_times.get(migration_id)
                task_id = migration.get("task_id")
                if transition_delivery is None or not _nonempty_string(task_id):
                    continue
                unresolved_pushes = unresolved_pushes_at(
                    task_id, transition_delivery
                )
                if not unresolved_pushes:
                    continue
                direct_source_id = unresolved_pushes[-1][1]
                if migration.get("retry_of") != direct_source_id:
                    errors.append(
                        f"attempt {migration_id} must directly retry unresolved same-task "
                        f"push_v1 attempt {direct_source_id}"
                    )
                transition_ancestors = set(
                    _retry_ancestors(migration_id, attempts)
                )
                missing_lineage = sorted(
                    source_id
                    for _, source_id in unresolved_pushes
                    if source_id not in transition_ancestors
                )
                if missing_lineage:
                    errors.append(
                        f"attempt {migration_id} retry_of lineage does not include every "
                        "earlier unresolved same-task push_v1 attempt: "
                        + ", ".join(missing_lineage)
                    )

        for attempt_id, attempt in attempts.items():
            attempt_delivery = attempt_delivery_times.get(attempt_id)
            if (
                attempt.get("return_contract_version") != "task_event_v1"
                or attempt_delivery is None
            ):
                continue
            ancestors = _retry_ancestors(attempt_id, attempts)
            lineage = [attempt_id, *ancestors]
            migration_transitions: list[str] = []
            for child_id in lineage:
                child_attempt = attempts.get(child_id, {})
                source_id = child_attempt.get("retry_of")
                source_attempt = (
                    attempts.get(source_id, {})
                    if _nonempty_string(source_id)
                    else {}
                )
                if (
                    child_attempt.get("return_contract_version") == "task_event_v1"
                    and source_attempt.get("return_contract_version") == "push_v1"
                ):
                    migration_transitions.append(child_id)
            if len(migration_transitions) > 1:
                errors.append(
                    f"attempt {attempt_id} retry lineage contains multiple push_v1 to "
                    "task_event_v1 migration transitions: "
                    + ", ".join(migration_transitions)
                )
            task_id = attempt.get("task_id")
            if not _nonempty_string(task_id):
                continue
            unresolved_pushes = unresolved_pushes_at(task_id, attempt_delivery)
            if not unresolved_pushes:
                continue
            if not migration_transitions:
                direct_source_id = unresolved_pushes[-1][1]
                errors.append(
                    f"attempt {attempt_id} must directly retry unresolved same-task "
                    f"push_v1 attempt {direct_source_id}"
                )
                _validate_contract_migration(
                    attempt_id,
                    attempt,
                    attempts,
                    attempt_delivery_times,
                    attempt_first_wait_times,
                    errors,
                )
                validated_migration_ids.add(attempt_id)
                continue
            transition_ancestors = set(
                _retry_ancestors(migration_transitions[0], attempts)
            )
            missing_lineage = sorted(
                source_id
                for _, source_id in unresolved_pushes
                if source_id not in transition_ancestors
            )
            if missing_lineage:
                errors.append(
                    f"attempt {attempt_id} retry_of lineage does not include every earlier "
                    "unresolved same-task push_v1 attempt: "
                    + ", ".join(missing_lineage)
                )

        for attempt_id, attempt in attempts.items():
            if attempt.get("return_contract_version") != "task_event_v1":
                if attempt.get("contract_migration") is not None:
                    errors.append(
                        f"attempt {attempt_id}.contract_migration is only valid for task_event_v1"
                    )
                continue
            if (
                attempt_id not in validated_migration_ids
                and attempt.get("contract_migration") is not None
            ):
                _validate_contract_migration(
                    attempt_id,
                    attempt,
                    attempts,
                    attempt_delivery_times,
                    attempt_first_wait_times,
                    errors,
                )

    declared_authority_ids = {
        authority_id
        for authority_list in (
            list(authorities_by_task.values()) + list(authorities_by_candidate.values())
        )
        for authority_id in authority_list
    }
    _, stale_tasks, stale_candidates, supersession_map = _build_stale_closure(
        tasks,
        attempts,
        candidates,
        records["supersedes"],
        declared_authority_ids,
        strict_graph=current_contract,
        errors=errors,
    )
    unresolved_effective_delivered_not_returned: list[str] = []
    if current_contract:
        for subject_id, replacement_id in supersession_map.items():
            if subject_id in candidates and replacement_id in candidates:
                subject_observed_at = candidate_observed_times.get(subject_id)
                replacement_observed_at = candidate_observed_times.get(replacement_id)
                if subject_observed_at is None or replacement_observed_at is None:
                    errors.append(
                        f"candidate supersession {subject_id} -> {replacement_id} "
                        "requires both canonical candidate observed_at timestamps"
                    )
                elif replacement_observed_at <= subject_observed_at:
                    errors.append(
                        f"candidate supersession chronology requires replacement "
                        f"candidate {replacement_id}.observed_at to be strictly after "
                        f"subject candidate {subject_id}.observed_at"
                    )
                continue
            if subject_id not in attempts or replacement_id not in attempts:
                continue
            subject_delivery = attempt_delivery_times.get(subject_id)
            replacement_delivery = attempt_delivery_times.get(replacement_id)
            _require_timestamp_order(
                subject_delivery,
                replacement_delivery,
                f"supersession replacement attempt {replacement_id} delivery",
                f"superseded attempt {subject_id} delivery",
                errors,
            )

        for task_id, task in tasks.items():
            current_attempt_id = task.get("current_attempt_id")
            if not _nonempty_string(current_attempt_id) or current_attempt_id not in attempts:
                unresolved_effective_delivered_not_returned.extend(
                    attempt_id
                    for attempt_id in attempts_by_task.get(task_id, [])
                    if attempt_id in attempt_delivery_times
                    and not attempts[attempt_id].get("returned_at")
                    and not (
                        attempt_id in attempt_uncertain_times
                        and attempt_id in attempt_uncertainty_reconciled_times
                    )
                )
                continue
            ancestors = _retry_ancestors(current_attempt_id, attempts)
            ancestry_targets = {current_attempt_id, *ancestors}
            lineage_children: dict[str, str] = {}
            child_id = current_attempt_id
            for ancestor_id in ancestors:
                lineage_children[ancestor_id] = child_id
                child_id = ancestor_id

            reconciled_supersession_by_attempt: dict[str, bool] = {}

            for attempt_id in attempts_by_task.get(task_id, []):
                if (
                    attempt_id == current_attempt_id
                    or attempt_id not in attempt_delivery_times
                ):
                    continue
                in_retry_lineage = attempt_id in ancestors
                supersession_path = _supersession_path_to(
                    attempt_id,
                    ancestry_targets,
                    supersession_map,
                )
                path_is_causal = supersession_path is not None
                if supersession_path is not None:
                    cross_task_path = [
                        path_attempt_id
                        for path_attempt_id in supersession_path
                        if attempts.get(path_attempt_id, {}).get("task_id") != task_id
                    ]
                    if cross_task_path:
                        errors.append(
                            f"attempt {attempt_id} run-level supersession path must stay "
                            f"within task {task_id}: " + ", ".join(cross_task_path)
                        )
                        path_is_causal = False
                    missing_delivery = [
                        path_attempt_id
                        for path_attempt_id in supersession_path
                        if path_attempt_id not in attempt_delivery_times
                    ]
                    if missing_delivery:
                        errors.append(
                            f"attempt {attempt_id} run-level supersession path contains "
                            "attempts without delivered_at: "
                            + ", ".join(missing_delivery)
                        )
                        path_is_causal = False
                    else:
                        path_is_causal = all(
                            attempt_delivery_times[later_id]
                            > attempt_delivery_times[earlier_id]
                            for earlier_id, later_id in zip(
                                supersession_path, supersession_path[1:]
                            )
                        )
                source_attempt = attempts[attempt_id]
                if source_attempt.get("returned_at"):
                    source_reconciled = bool(
                        attempt_id in attempt_return_reconciled_times
                        and source_attempt.get("return_reconciled_by")
                        == run.get("coordinator_id")
                    )
                else:
                    source_reconciled = bool(
                        attempt_id in attempt_uncertain_times
                        and attempt_id in attempt_uncertainty_reconciled_times
                    )
                reconciled_run_supersession = bool(
                    path_is_causal and source_reconciled
                )
                reconciled_supersession_by_attempt[attempt_id] = (
                    reconciled_run_supersession
                )
                if not in_retry_lineage and not reconciled_run_supersession:
                    errors.append(
                        f"noncurrent delivered attempt {attempt_id} is outside current "
                        f"attempt {current_attempt_id} retry lineage and lacks reconciled "
                        "run-level supersession"
                    )

            for attempt_id in attempts_by_task.get(task_id, []):
                if (
                    attempt_id not in attempt_delivery_times
                    or attempts[attempt_id].get("returned_at")
                ):
                    continue
                if attempt_id == current_attempt_id:
                    if not (
                        attempt_id in attempt_uncertain_times
                        and attempt_id in attempt_uncertainty_reconciled_times
                    ):
                        unresolved_effective_delivered_not_returned.append(attempt_id)
                    continue
                lineage_child_id = lineage_children.get(attempt_id)
                resolved_by_retry_audit = bool(
                    lineage_child_id is not None
                    and _pre_retry_audit_is_complete(
                        attempts[lineage_child_id].get("pre_retry_audit")
                    )
                )
                resolved_by_supersession = bool(
                    reconciled_supersession_by_attempt.get(attempt_id)
                )
                if not resolved_by_retry_audit and not resolved_by_supersession:
                    unresolved_effective_delivered_not_returned.append(attempt_id)

    stale_evidence = sorted(
        evidence_id
        for evidence_id, item in evidence.items()
        if _nonempty_string(item.get("candidate_id"))
        and item.get("candidate_id") in stale_candidates
    )
    for task_id in sorted(stale_tasks):
        if task_id in tasks and tasks[task_id].get("status") != "superseded":
            errors.append(f"affected task {task_id} must be marked superseded")

    accepted_candidates: set[str] = set()
    for task_id, task in tasks.items():
        current_attempt_id = task.get("current_attempt_id")
        current_attempt = attempts.get(current_attempt_id, {})
        status = task.get("status")

        if status in ("running", "succeeded") and not current_attempt:
            errors.append(f"{status} task {task_id} must identify a current attempt")
            continue
        if current_attempt and current_attempt.get("task_id") != task_id:
            errors.append(f"task {task_id} current attempt belongs to another task")

        if status == "succeeded":
            if not current_attempt.get("accepted_at"):
                errors.append(f"succeeded task {task_id} lacks accepted current attempt")
                continue
            candidate_id = current_attempt.get("candidate_id")
            candidate = (
                candidates.get(candidate_id)
                if _nonempty_string(candidate_id)
                else None
            )
            if not candidate:
                errors.append(f"succeeded task {task_id} references unknown candidate: {candidate_id}")
                continue
            if candidate.get("produced_by") != current_attempt_id:
                errors.append(f"candidate {candidate_id} was not produced by task {task_id} current attempt")
            if candidate_id in stale_candidates or task_id in stale_tasks:
                errors.append(f"succeeded task {task_id} uses stale candidate {candidate_id}")
            if not evidence_by_candidate.get(candidate_id):
                errors.append(f"succeeded task {task_id} candidate {candidate_id} lacks evidence")
            accepted_candidates.add(candidate_id)

            candidate_review_ids: set[str] = set()
            qualifying_ids: set[str] = set()
            if current_contract:
                candidate_review_ids = {
                    review.get("review_id")
                    for review in reviews_by_candidate.get(candidate_id, [])
                }
                effective_review_ids = {
                    review_id
                    for review_id in candidate_review_ids
                    if review_infos.get(review_id, {}).get("review_status")
                    == "effective"
                }
                qualifying_ids = candidate_review_ids.intersection(
                    qualifying_current_reviews
                )
                accepted_time = attempt_acceptance_times.get(current_attempt_id)
                for review_id in sorted(effective_review_ids):
                    info = review_infos.get(review_id, {})
                    optional_adverse_cleared = (
                        candidate.get("review_required") is False
                        and review_id in cleared_optional_review_ids
                    )
                    if (
                        info.get("structurally_valid")
                        and not info.get("clean")
                        and not optional_adverse_cleared
                    ):
                        errors.append(
                            f"effective review {review_id} has unresolved adverse criteria or material findings"
                        )
                    if not info.get("structurally_valid"):
                        errors.append(
                            f"effective review {review_id} is not structurally valid"
                        )
                    review_reconciled_at = info.get("reconciled_at")
                    if (
                        accepted_time is None
                        or review_reconciled_at is None
                        or review_reconciled_at >= accepted_time
                    ):
                        errors.append(
                            f"candidate {candidate_id} was accepted before effective review {review_id} reconciliation"
                        )

            if candidate.get("review_required") is True:
                if current_contract:
                    if not qualifying_ids:
                        errors.append(
                            f"candidate {candidate_id} lacks a returned, coordinator-reconciled independent review"
                        )
                    else:
                        accepted_time = attempt_acceptance_times.get(current_attempt_id)
                        reviewed_before_acceptance = any(
                            accepted_time is not None
                            and current_review_reconciled_times.get(review_id) is not None
                            and current_review_reconciled_times[review_id] < accepted_time
                            for review_id in qualifying_ids
                        )
                        if not reviewed_before_acceptance:
                            errors.append(
                                f"candidate {candidate_id} was accepted before required review reconciliation; "
                                "required review reconciliation must be strictly before acceptance"
                            )
                else:
                    producer_owner = current_attempt.get("owner")
                    qualifying_review = False
                    for review in reviews_by_candidate.get(candidate_id, []):
                        findings = review.get("open_material_findings")
                        requirements = review.get("requirements")
                        review_evidence = review.get("evidence")
                        if (
                            review.get("read_only") is True
                            and _nonempty_string(review.get("completed_at"))
                            and review.get("reviewer") != producer_owner
                            and isinstance(requirements, list)
                            and bool(requirements)
                            and isinstance(review_evidence, list)
                            and bool(review_evidence)
                            and isinstance(findings, list)
                            and not findings
                        ):
                            qualifying_review = True
                            break
                    if not qualifying_review:
                        errors.append(
                            f"candidate {candidate_id} lacks a completed fresh read-only review without open material findings"
                        )

        if current_attempt.get("accepted_at") and status not in (
            "succeeded",
            "superseded",
        ):
            errors.append(
                f"task {task_id} has an accepted current attempt but status is {status}"
            )

    active_details: dict[str, tuple[list[str], str | None]] = {}
    active_attempt_claims: dict[tuple[str, str], str] = {}
    filesystem_claim_types: set[str] = set()
    for active_id, item in active_work.items():
        if current_contract:
            _require_exact_fields(
                item,
                CURRENT_ACTIVE_WORK_FIELDS,
                f"active work {active_id}",
                errors,
            )
        active_kind = item.get("kind")
        if (
            not _nonempty_string(active_kind)
            or active_kind not in ALLOWED_ACTIVE_KINDS
        ):
            errors.append(f"active work {active_id} has unsupported kind: {item.get('kind')}")
        if not _nonempty_string(item.get("owner")):
            errors.append(f"active work {active_id}.owner must be a non-empty string")
        raw_writes = _string_list(
            item.get("writes"), f"active work {active_id}.writes", errors
        )
        writes: list[str] = []
        for index, raw_write in enumerate(raw_writes):
            label = f"active work {active_id}.writes[{index}]"
            canonical_write, claim_type = _canonicalize_write_claim(
                raw_write,
                project_root=project_root,
                label=label,
                errors=errors,
            )
            if claim_type in {"relative", "absolute"}:
                filesystem_claim_types.add(claim_type)
            if canonical_write is not None:
                writes.append(canonical_write)
                authority_alias = _authority_descendant_alias(
                    raw_write,
                    project_root=project_root,
                )
                if authority_alias is not None and authority_alias != canonical_write:
                    writes.append(authority_alias)
        if not raw_writes:
            errors.append(f"active work {active_id} must claim at least one mutable write")
        isolation_key = item.get("isolation_key")
        if isolation_key is not None and not _nonempty_string(isolation_key):
            errors.append(f"active work {active_id}.isolation_key must be null or a string")
            isolation_key = None
        task_id = item.get("task_id")
        attempt_id = item.get("attempt_id")
        valid_task_id = task_id if _nonempty_string(task_id) else None
        valid_attempt_id = attempt_id if _nonempty_string(attempt_id) else None
        if task_id is not None and valid_task_id is None:
            errors.append(
                f"active work {active_id}.task_id must be null or a non-empty string"
            )
        if attempt_id is not None and valid_attempt_id is None:
            errors.append(
                f"active work {active_id}.attempt_id must be null or a non-empty string"
            )
        if valid_task_id is not None and valid_task_id not in tasks:
            errors.append(
                f"active work {active_id} references unknown task_id: {valid_task_id}"
            )
        elif (
            valid_task_id is not None
            and tasks[valid_task_id].get("status") != "running"
        ):
            errors.append(
                f"active work {active_id} task {valid_task_id} is not running"
            )
        if valid_attempt_id is not None and valid_attempt_id not in attempts:
            errors.append(
                f"active work {active_id} references unknown attempt_id: {valid_attempt_id}"
            )
        elif valid_attempt_id is not None:
            bound_attempt = attempts[valid_attempt_id]
            bound_task_id = bound_attempt.get("task_id")
            if valid_task_id is None:
                errors.append(
                    f"active work {active_id}.task_id is required when attempt_id is set"
                )
            elif bound_task_id != valid_task_id:
                errors.append(f"active work {active_id} attempt belongs to another task")
            if item.get("owner") != bound_attempt.get("owner"):
                errors.append(
                    f"active work {active_id}.owner must match attempt "
                    f"{valid_attempt_id}.owner"
                )
            if _nonempty_string(bound_task_id):
                claim_key = (bound_task_id, valid_attempt_id)
                previous_active_id = active_attempt_claims.get(claim_key)
                if previous_active_id is not None:
                    errors.append(
                        f"active work {active_id} duplicates accountable attempt "
                        f"{bound_task_id}/{valid_attempt_id} already claimed by "
                        f"{previous_active_id}"
                    )
                else:
                    active_attempt_claims[claim_key] = active_id
        if valid_task_id in stale_tasks:
            errors.append(f"active work {active_id} belongs to superseded task {task_id}")
        active_details[active_id] = (writes, isolation_key)

    if project_root is None and filesystem_claim_types == {"relative", "absolute"}:
        errors.append(
            "active_work mixes relative and absolute filesystem write claims without "
            "project_root"
        )

    active_ids = sorted(active_details)
    for left_index, left_id in enumerate(active_ids):
        left_writes, left_isolation = active_details[left_id]
        for right_id in active_ids[left_index + 1 :]:
            right_writes, right_isolation = active_details[right_id]
            overlap = any(
                _writes_overlap(left, right)
                for left in left_writes
                for right in right_writes
            )
            isolated = (
                _nonempty_string(left_isolation)
                and _nonempty_string(right_isolation)
                and left_isolation != right_isolation
            )
            if overlap and not isolated:
                errors.append(
                    f"active work {left_id} and {right_id} have overlapping writes without distinct isolation"
                )

    if current_contract:
        for return_label, event_at, reconciled_at, source_key in return_barriers:
            for dispatch_label, delivered_at, dispatch_key in material_dispatch_times:
                if dispatch_key == source_key:
                    continue
                if event_at <= delivered_at and (
                    reconciled_at is None or reconciled_at >= delivered_at
                ):
                    errors.append(
                        f"return-first barrier: {return_label} was not reconciled before dispatching {dispatch_label}"
                    )

    current_candidate_id: str | None = None
    if latest_result is not None:
        if not isinstance(latest_result, dict):
            errors.append("latest_result must be an object")
            latest_result = {}
        pointer_structurally_valid = _require_exact_key_set(
            latest_result,
            LATEST_RESULT_FIELDS,
            "latest_result",
            errors,
        )
        if type(latest_result.get("schema_version")) is not int or latest_result.get(
            "schema_version"
        ) != 1:
            errors.append("latest_result.schema_version must be 1")
            pointer_structurally_valid = False
        latest_run_id = latest_result.get("run_id")
        pointer_candidate_id = latest_result.get("candidate_id")
        if pointer_candidate_id is not None:
            if not _nonempty_string(pointer_candidate_id):
                errors.append(
                    "latest_result.candidate_id must be null or a non-empty string"
                )
                pointer_structurally_valid = False
            for field in ("candidate_id", "run_id", "result_manifest", "source_digest"):
                if not _nonempty_string(latest_result.get(field)):
                    errors.append(
                        f"latest_result.{field} must be a non-empty string when "
                        "candidate_id is set"
                    )
                    pointer_structurally_valid = False
            if _nonempty_string(pointer_candidate_id):
                current_candidate_id = pointer_candidate_id
            if _nonempty_string(latest_run_id) and latest_run_id != run.get("run_id"):
                errors.append("latest_result.run_id does not match the audited run")
                pointer_structurally_valid = False
            if not _nonempty_string(pointer_candidate_id):
                pass
            elif pointer_candidate_id not in candidates:
                errors.append(
                    f"latest_result references unknown candidate: {pointer_candidate_id}"
                )
            elif pointer_candidate_id in stale_candidates:
                errors.append(
                    f"latest_result candidate is stale: {pointer_candidate_id}"
                )
            elif pointer_candidate_id not in accepted_candidates:
                errors.append(
                    "latest_result candidate is not accepted by a succeeded current "
                    f"task: {pointer_candidate_id}"
                )
        else:
            for field in ("run_id", "result_manifest", "source_digest"):
                if latest_result.get(field) is not None:
                    errors.append(
                        f"latest_result.{field} must be null when candidate_id is null"
                    )
                    pointer_structurally_valid = False
        if pointer_candidate_id is not None and pointer_structurally_valid:
            if project_root is None:
                errors.append(
                    "latest_result with a non-null candidate_id requires project_root artifact verification"
                )
            else:
                _validate_result_artifacts(
                    run, latest_result, candidates, project_root, errors
                )
    if recovery is not None:
        if type(recovery.get("schema_version")) is not int or recovery.get(
            "schema_version"
        ) != 1:
            errors.append("recovery.schema_version must be 1")
        for field in ("binding_id", "batch_id", "run_id"):
            if recovery.get(field) != run.get(field):
                errors.append(f"recovery.{field} does not match the audited run")
        if not _nonempty_string(recovery.get("objective")):
            errors.append("recovery.objective must be a non-empty string")
        recovery_lists: dict[str, list[str]] = {}
        for field in (
            "latest_constraints",
            "current_candidates",
            "verified_evidence",
            "decisions",
            "succeeded_work",
            "pending_work",
            "superseded_work",
            "active_work",
            "uncertain_attempts",
        ):
            recovery_lists[field] = _string_list(
                recovery.get(field), f"recovery.{field}", errors
            )
        if not _nonempty_string(recovery.get("next_action")):
            errors.append("recovery.next_action must be a non-empty string")
        if "blocker" not in recovery or (
            recovery.get("blocker") is not None
            and not _nonempty_string(recovery.get("blocker"))
        ):
            errors.append("recovery.blocker must be null or a non-empty string")
        missing_uncertain = unresolved_uncertainty.difference(
            recovery_lists.get("uncertain_attempts", [])
        )
        if missing_uncertain:
            errors.append(
                "recovery misses uncertain attempts: " + ", ".join(sorted(missing_uncertain))
            )
        missing_active = set(active_work).difference(recovery_lists.get("active_work", []))
        if missing_active:
            errors.append(
                "recovery misses active work: " + ", ".join(sorted(missing_active))
            )
        extra_active = set(recovery_lists.get("active_work", [])).difference(active_work)
        if extra_active:
            errors.append(
                "recovery lists non-active work: " + ", ".join(sorted(extra_active))
            )
        extra_uncertain = set(recovery_lists.get("uncertain_attempts", [])).difference(
            unresolved_uncertainty
        )
        if extra_uncertain:
            errors.append(
                "recovery lists reconciled or unknown uncertain attempts: "
                + ", ".join(sorted(extra_uncertain))
            )
        for candidate_id in recovery_lists.get("current_candidates", []):
            if candidate_id not in candidates:
                errors.append(f"recovery references unknown current candidate: {candidate_id}")
            elif candidate_id in stale_candidates:
                errors.append(f"recovery references stale current candidate: {candidate_id}")
    elif unresolved_uncertainty:
        errors.append("unresolved uncertain attempts require a recovery capsule")

    nonterminal_tasks = sorted(
        task_id
        for task_id, task in tasks.items()
        if task.get("status") not in ("succeeded", "superseded")
    )
    closure_ready = (
        not active_work
        and not unresolved_uncertainty
        and (
            not current_contract
            or not unresolved_effective_delivered_not_returned
        )
        and not nonterminal_tasks
        and not nonterminal_stages
        and (not current_contract or not unreconciled_returns)
    )
    if closure:
        if active_work:
            errors.append("closure requires an empty active_work list")
        if unresolved_uncertainty:
            errors.append("closure requires all uncertain attempts to be reconciled")
        if nonterminal_tasks:
            errors.append(
                "closure requires every effective task to be succeeded or superseded: "
                + ", ".join(nonterminal_tasks)
            )
        if current_contract and unreconciled_returns:
            errors.append(
                "closure requires every delivered return to be coordinator-reconciled: "
                + ", ".join(sorted(unreconciled_returns))
            )
        if current_contract and unresolved_effective_delivered_not_returned:
            errors.append(
                "closure requires every effective delivered attempt to have returned "
                "or been reconciled: "
                + ", ".join(
                    sorted(set(unresolved_effective_delivered_not_returned))
                )
            )

    report: dict[str, Any] = {
        "schema_version": 1,
        "valid": not errors,
        "run_id": run.get("run_id"),
        "contract_conformance": (
            "fail_closed_v2" if current_contract else "legacy_readable_only"
        ),
        "contract_conformance_scope": (
            "structural_over_trusted_persisted_attestations"
            if current_contract
            else "legacy_readability_only"
        ),
        "provenance_trust_model": (
            PROVENANCE_TRUST_MODEL if current_contract else None
        ),
        "cryptographic_actor_or_creation_proof": False,
        "warnings": [PROVENANCE_WARNING] if current_contract else [],
        "schema_provenance_mode": (
            run.get("schema_provenance", {}).get("mode")
            if isinstance(run.get("schema_provenance"), dict)
            else None
        ),
        "current_contract_ready": current_contract and not errors,
        "closure_requested": closure,
        "closure_ready": closure_ready and not errors,
        "counts": {
            "tasks": len(tasks),
            "attempts": len(attempts),
            "candidates": len(candidates),
            "evidence": len(evidence),
            "reviews": len(reviews),
            "active_work": len(active_work),
        },
        "delivered_not_returned": sorted(delivered_not_returned),
        "unresolved_effective_delivered_not_returned": sorted(
            set(unresolved_effective_delivered_not_returned)
        ),
        "returned_not_accepted": sorted(returned_not_accepted),
        "unreconciled_returns": sorted(unreconciled_returns),
        "unresolved_uncertainty": sorted(unresolved_uncertainty),
        "nonterminal_stages": nonterminal_stages,
        "stale_tasks": sorted(stale_tasks),
        "stale_candidates": sorted(stale_candidates),
        "stale_evidence": stale_evidence,
        "current_candidate_id": current_candidate_id,
        "errors": errors,
    }
    if errors:
        raise CoordinationAuditError(errors, report)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit of persisted multi-thread-coordinator run state."
    )
    parser.add_argument("--run", required=True, help="Path to coordination/run.json")
    parser.add_argument(
        "--legacy-run",
        help=(
            "Trusted schema-version-1 source record required for structural "
            "migrated_from_v1 comparison"
        ),
    )
    parser.add_argument("--latest-result", help="Optional path to latest_result.json")
    parser.add_argument(
        "--project-root",
        help=(
            "Approved project root for active-write canonicalization and read-only "
            "result artifact verification; required when latest_result candidate_id "
            "is non-null"
        ),
    )
    parser.add_argument("--recovery", help="Optional path to recovery.json")
    parser.add_argument(
        "--closure",
        action="store_true",
        help="Require no active, uncertain, or non-terminal effective work",
    )
    parser.add_argument(
        "--require-current-contract",
        action="store_true",
        help=(
            "Reject legacy-readable schema v1 when structural fail_closed_v2 "
            "conformance over trusted persisted attestations is required"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        run = _load_json(args.run, "run record")
        legacy_run = (
            _load_json(args.legacy_run, "legacy run record")
            if args.legacy_run
            else None
        )
        latest_result = (
            _load_json(args.latest_result, "latest result") if args.latest_result else None
        )
        recovery = _load_json(args.recovery, "recovery capsule") if args.recovery else None
        report = audit_coordination_state(
            run,
            legacy_run=legacy_run,
            latest_result=latest_result,
            recovery=recovery,
            project_root=args.project_root,
            closure=args.closure,
            require_current_contract=args.require_current_contract,
        )
    except ValueError as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 2
    except CoordinationAuditError as exc:
        print(json.dumps(exc.report, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from copy import deepcopy
from contextlib import contextmanager
from contextlib import redirect_stderr
from contextlib import redirect_stdout
import importlib.util
import hashlib
from io import StringIO
import json
import shutil
import unittest
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "multi-thread-coordinator"
    / "scripts"
    / "audit_coordination_state.py"
)
SPEC = importlib.util.spec_from_file_location("audit_coordination_state", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

CURRENT_SKILL_COMMIT = "f12670de41bbac81dd33e4c2eebf3173bcc8aec4"
LEGACY_SKILL_COMMIT = "4f8fe1b"
COORDINATOR_ID = "coordinator_main"


@contextmanager
def isolated_parent():
    container = REPO_ROOT / "tests" / ".tmp-audit-coordination-state"
    container.mkdir(exist_ok=True)
    case = container / f"case-{uuid.uuid4().hex}"
    case.mkdir(parents=True)
    try:
        yield case
    finally:
        shutil.rmtree(case)
        try:
            container.rmdir()
        except OSError:
            pass


def empty_run() -> dict:
    return {
        "schema_version": 1,
        "run_id": "run_0001",
        "batch_id": "batch_0001",
        "binding_id": "binding_v001",
        "chains": [],
        "tasks": [],
        "attempts": [],
        "candidates": [],
        "evidence": [],
        "reviews": [],
        "supersedes": [],
        "active_work": [],
    }


def add_accepted_task(
    run: dict,
    task_id: str,
    *,
    owner: str = "worker_a",
    depends_on: list[str] | None = None,
    consumes: list[str] | None = None,
    candidate_consumes: list[str] | None = None,
    review_required: bool = False,
) -> tuple[str, str, str]:
    suffix = task_id.removeprefix("task_")
    attempt_id = f"attempt_{suffix}_001"
    candidate_id = f"candidate_{suffix}_001"
    evidence_id = f"evidence_{suffix}_001"
    run["tasks"].append(
        {
            "task_id": task_id,
            "status": "succeeded",
            "depends_on": depends_on or [],
            "consumes": consumes or [],
            "current_attempt_id": attempt_id,
        }
    )
    run["attempts"].append(
        {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "owner": owner,
            "delivered_at": "2026-08-25T01:00:00Z",
            "returned_at": "2026-08-25T01:01:00Z",
            "accepted_at": "2026-08-25T01:02:00Z",
            "candidate_id": candidate_id,
        }
    )
    run["candidates"].append(
        {
            "candidate_id": candidate_id,
            "produced_by": attempt_id,
            "consumes": candidate_consumes or [],
            "identity": {"method": "sha256", "value": f"digest-{suffix}"},
            "review_required": review_required,
        }
    )
    run["evidence"].append(
        {
            "evidence_id": evidence_id,
            "candidate_id": candidate_id,
            "kind": "inspection",
        }
    )
    return attempt_id, candidate_id, evidence_id


def latest_result(candidate_id: str | None) -> dict:
    return {
        "schema_version": 1,
        "run_id": "run_0001" if candidate_id else None,
        "result_manifest": "run_0001/result_manifest.json" if candidate_id else None,
        "candidate_id": candidate_id,
        "source_digest": "source-digest" if candidate_id else None,
    }


def recovery_capsule(*, active: list[str], uncertain: list[str]) -> dict:
    return {
        "schema_version": 1,
        "binding_id": "binding_v001",
        "batch_id": "batch_0001",
        "run_id": "run_0001",
        "objective": "complete the synthetic task",
        "latest_constraints": ["stay synthetic"],
        "current_candidates": [],
        "verified_evidence": [],
        "decisions": [],
        "succeeded_work": [],
        "pending_work": ["task_demo"],
        "superseded_work": [],
        "active_work": active,
        "uncertain_attempts": uncertain,
        "blocker": None,
        "next_action": "inspect native task state",
    }


def _creation_snapshot(run: dict, established_at: str) -> dict:
    return {
        "schema_version": 2,
        "run_id": run["run_id"],
        "batch_id": run["batch_id"],
        "binding_id": run["binding_id"],
        "skill_commit_at_creation": run["skill_commit_at_creation"],
        "return_contract_version": run["return_contract_version"],
        "coordinator_id": run["coordinator_id"],
        "established_at": established_at,
        "chains": [],
        "tasks": [],
        "attempts": [],
        "candidates": [],
        "evidence": [],
        "reviews": [],
        "supersedes": [],
        "active_work": [],
    }


def _refresh_creation_provenance(run: dict) -> None:
    established_at = run["schema_provenance"]["established_at"]
    run["schema_provenance"]["creation_digest"] = AUDIT._canonical_sha256(
        _creation_snapshot(run, established_at)
    )


def current_run(
    *,
    creation_contract: str = "task_event_v1",
    skill_commit: str = CURRENT_SKILL_COMMIT,
) -> dict:
    run = empty_run()
    run.update(
        {
            "schema_version": 2,
            "skill_commit_at_creation": skill_commit,
            "return_contract_version": creation_contract,
            "coordinator_id": COORDINATOR_ID,
            "schema_provenance": {
                "mode": "created_v2",
                "established_at": "2026-09-01T00:00:00Z",
                "creation_digest": "pending",
            },
        }
    )
    _refresh_creation_provenance(run)
    return run


def criterion_rows() -> list[dict]:
    return [
        {"criterion_id": "criterion_accuracy", "requirement": "values tie to source"},
        {"criterion_id": "criterion_layout", "requirement": "layout is readable"},
    ]


def evidence_row(
    *,
    evidence_id: str,
    candidate_id: str,
    criterion: dict,
    candidate_identity: dict,
    authority_identities: list[str],
    observed_at: str = "2026-09-01T01:03:30Z",
) -> dict:
    return {
        "evidence_id": evidence_id,
        "candidate_id": candidate_id,
        "criterion_id": criterion["criterion_id"],
        "requirement": criterion["requirement"],
        "result": "pass",
        "authority_identities": authority_identities,
        "candidate_identity": deepcopy(candidate_identity),
        "kind": "inspection",
        "method": f"inspect {criterion['criterion_id']}",
        "raw_output": f"raw/{evidence_id}.txt",
        "observed_by": COORDINATOR_ID,
        "observed_at": observed_at,
    }


def _refresh_packet_digest(review: dict) -> None:
    packet = review["packet"]
    body = {key: value for key, value in packet.items() if key != "packet_digest"}
    packet["packet_digest"] = AUDIT._canonical_sha256(body)


def add_current_hybrid_task(run: dict) -> tuple[str, str, str]:
    task_id = "task_report"
    attempt_id = "attempt_report_001"
    candidate_id = "candidate_report_001"
    criteria = criterion_rows()
    authority_identities = ["authority_v1@sha256:source"]
    candidate_identity = {"method": "sha256", "value": "digest-report"}
    run["tasks"].append(
        {
            "task_id": task_id,
            "status": "succeeded",
            "owner_surface": "user_visible_task",
            "depends_on": [],
            "consumes": [],
            "current_attempt_id": attempt_id,
            "authority_identities": authority_identities,
            "acceptance_criteria": criteria,
            "decisions": ["decision_use_current_scope"],
        }
    )
    run["attempts"].append(
        {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "owner": "worker_a",
            "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
            "return_mode": "task_event",
            "return_contract_version": "task_event_v1",
            "worker_thread_id": "thread_producer",
            "worker_host_id": "host_main",
            "delivered_at": "2026-09-01T01:00:00Z",
            "first_wait_at": "2026-09-01T01:00:10Z",
            "return_event_received_at": "2026-09-01T01:02:00Z",
            "return_cursor": "cursor_producer_001",
            "returned_at": "2026-09-01T01:02:30Z",
            "return_reconciled_at": "2026-09-01T01:03:00Z",
            "return_reconciled_by": COORDINATOR_ID,
            "accepted_at": "2026-09-01T01:08:00Z",
            "accepted_by": COORDINATOR_ID,
            "candidate_id": candidate_id,
        }
    )
    run["candidates"].append(
        {
            "candidate_id": candidate_id,
            "kind": "document",
            "location": "results/report.xlsx",
            "scope": "synthetic report workbook",
            "produced_by": attempt_id,
            "consumes": [],
            "identity": candidate_identity,
            "authority_identities": authority_identities,
            "acceptance_criteria": deepcopy(criteria),
            "observed_at": "2026-09-01T01:03:05Z",
            "source_snapshots": ["source_manifest@sha256:source"],
            "review_required": True,
        }
    )
    for index, criterion in enumerate(criteria, start=1):
        run["evidence"].append(
            evidence_row(
                evidence_id=f"evidence_report_{index:03d}",
                candidate_id=candidate_id,
                criterion=criterion,
                candidate_identity=candidate_identity,
                authority_identities=authority_identities,
            )
        )
    packet = {
        "packet_schema_version": 1,
        "packet_id": "review_packet_001",
        "correlation": {
            "batch_id": run["batch_id"],
            "run_id": run["run_id"],
            "task_id": task_id,
            "attempt_id": attempt_id,
            "skill_commit_at_creation": run["skill_commit_at_creation"],
        },
        "candidate": {
            "candidate_id": candidate_id,
            "identity": {"method": "sha256", "value": "digest-report"},
            "scope": "synthetic report workbook",
            "producer": "worker_a",
            "source_snapshots": ["source_manifest@sha256:source"],
        },
        "authority": {
            "identities": ["authority_v1@sha256:source"],
            "requirements": criteria,
            "decisions": ["decision_use_current_scope"],
        },
        "review_matrix": [
            {
                "criterion_id": item["criterion_id"],
                "requirement": item["requirement"],
                "evidence_required": [f"evidence for {item['criterion_id']}"],
            }
            for item in criteria
        ],
        "boundaries": {
            "read_only": True,
            "allowed_reads": ["synthetic source and candidate"],
            "required_capabilities": ["source inspection"],
            "prohibited_actions": ["candidate mutation"],
        },
        "raw_evidence": ["synthetic source", "candidate render"],
        "lineage": {
            "predecessor_candidates": [],
            "protected_behavior": ["source remains unchanged"],
        },
        "return_contract": {
            "return_mode": "task_event",
            "return_contract_version": "task_event_v1",
            "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
            "events": ["completed", "needs_attention"],
        },
    }
    review = {
        "review_id": "review_001",
        "candidate_id": candidate_id,
        "reviewer": "reviewer_b",
        "review_status": "effective",
        "read_only": True,
        "packet": packet,
        "admitted_at": "2026-09-01T01:03:10Z",
        "delivered_at": "2026-09-01T01:03:20Z",
        "worker_thread_id": "thread_reviewer",
        "worker_host_id": "host_main",
        "first_wait_at": "2026-09-01T01:04:00Z",
        "return_cursor": "cursor_reviewer_001",
        "completed_at": "2026-09-01T01:05:00Z",
        "return_event_received_at": "2026-09-01T01:06:00Z",
        "returned_at": "2026-09-01T01:06:30Z",
        "reconciled_at": "2026-09-01T01:07:00Z",
        "reconciled_by": COORDINATOR_ID,
        "reviewer_actions": {
            "mutated_candidate": False,
            "waived_criteria": False,
            "unlocked_dependents": False,
            "updated_current_pointer": False,
            "accepted_candidate": False,
        },
        "criterion_results": [
            {
                "criterion_id": item["criterion_id"],
                "requirement": item["requirement"],
                "result": "pass",
                "evidence": [f"observed {item['criterion_id']}"],
            }
            for item in criteria
        ],
        "open_material_findings": [],
    }
    run["reviews"].append(review)
    _refresh_packet_digest(review)
    return task_id, attempt_id, candidate_id


def convert_to_notify(run: dict) -> None:
    """Rewrite the hybrid fixture onto the notify (re-invocation) contract.

    A notify host never waits in-turn, so the producer attempt and the reviewer
    swap their first-wait/cursor fields for the single arming timestamp that
    proves the host's notification path was live for that exact worker.
    """
    run["return_contract_version"] = "notify_v1"
    _refresh_creation_provenance(run)

    attempt = run["attempts"][0]
    attempt["return_mode"] = "notify"
    attempt["return_contract_version"] = "notify_v1"
    attempt["return_armed_at"] = attempt.pop("first_wait_at")
    attempt.pop("return_cursor")

    review = run["reviews"][0]
    review["return_armed_at"] = review.pop("first_wait_at")
    review.pop("return_cursor")
    review["packet"]["return_contract"]["return_mode"] = "notify"
    review["packet"]["return_contract"]["return_contract_version"] = "notify_v1"
    _refresh_packet_digest(review)


def add_adverse_review(
    run: dict,
    *,
    failed_criterion: bool = False,
    open_finding: bool = False,
) -> dict:
    review = deepcopy(run["reviews"][0])
    review.update(
        {
            "review_id": "review_adverse_001",
            "reviewer": "reviewer_c",
            "worker_thread_id": "thread_reviewer_adverse",
            "return_cursor": "cursor_reviewer_adverse_001",
            "admitted_at": "2026-09-01T01:03:01Z",
            "delivered_at": "2026-09-01T01:03:02Z",
            "first_wait_at": "2026-09-01T01:03:03Z",
            "completed_at": "2026-09-01T01:03:04Z",
            "return_event_received_at": "2026-09-01T01:03:05Z",
            "returned_at": "2026-09-01T01:03:06Z",
            "reconciled_at": "2026-09-01T01:03:07Z",
        }
    )
    review["packet"]["packet_id"] = "review_packet_adverse_001"
    if failed_criterion:
        review["criterion_results"][0]["result"] = "fail"
    if open_finding:
        review["open_material_findings"] = [
            {
                "criterion_id": "criterion_accuracy",
                "requirement": "values tie to source",
                "expected": "values tie",
                "observed": "one value differs",
                "location": "sheet A1",
                "evidence": "source comparison",
                "impact": "reported result is wrong",
                "requested_delta": "correct and rerun",
            }
        ]
    _refresh_packet_digest(review)
    run["reviews"].append(review)
    return review


def add_optional_adjudication(
    run: dict,
    review: dict,
    *,
    disposition: str = "false_positive",
) -> dict:
    requirements = {
        row["criterion_id"]: row["requirement"]
        for row in run["candidates"][0]["acceptance_criteria"]
    }
    adverse_ids = {
        row["criterion_id"]
        for row in review["criterion_results"]
        if row.get("result") != "pass"
    }
    adverse_ids.update(
        finding["criterion_id"] for finding in review["open_material_findings"]
    )
    evidence_ids = {
        "criterion_accuracy": "evidence_report_001",
        "criterion_layout": "evidence_report_002",
    }
    adjudication = {
        "adjudicated_by": COORDINATOR_ID,
        "adjudicated_at": "2026-09-01T01:07:30Z",
        "reason": "cross-task authority and candidate-bound evidence reject the adverse claim",
        "criterion_adjudications": [
            {
                "criterion_id": criterion_id,
                "requirement": requirements[criterion_id],
                "disposition": disposition,
                "rationale": "current source-bound evidence disproves material impact",
                "evidence_ids": [evidence_ids[criterion_id]],
            }
            for criterion_id in sorted(adverse_ids)
        ],
    }
    review["optional_adjudication"] = adjudication
    return adjudication


def add_current_accepted_task(
    run: dict,
    slug: str,
    *,
    hour: int,
    status: str = "succeeded",
    accepted_at: str | None = None,
    authority_identities: list[str] | None = None,
) -> tuple[str, str, str]:
    task_id = f"task_{slug}"
    attempt_id = f"attempt_{slug}_001"
    candidate_id = f"candidate_{slug}_001"
    criterion = {
        "criterion_id": f"criterion_{slug}",
        "requirement": f"{slug} is correct",
    }
    authorities = authority_identities or [f"authority_{slug}_v1"]
    identity = {"method": "sha256", "value": f"digest-{slug}"}
    prefix = f"2026-09-01T{hour:02d}:"
    run["tasks"].append(
        {
            "task_id": task_id,
            "status": status,
            "owner_surface": "user_visible_task",
            "depends_on": [],
            "consumes": [],
            "current_attempt_id": attempt_id,
            "authority_identities": authorities,
            "acceptance_criteria": [criterion],
        }
    )
    run["attempts"].append(
        {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "owner": f"worker_{slug}",
            "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
            "return_mode": "task_event",
            "return_contract_version": "task_event_v1",
            "worker_thread_id": f"thread_{slug}",
            "worker_host_id": "host_main",
            "delivered_at": prefix + "00:00Z",
            "first_wait_at": prefix + "00:10Z",
            "return_event_received_at": prefix + "01:00Z",
            "return_cursor": f"cursor_{slug}",
            "returned_at": prefix + "02:00Z",
            "return_reconciled_at": prefix + "03:00Z",
            "return_reconciled_by": COORDINATOR_ID,
            "accepted_at": accepted_at or prefix + "05:00Z",
            "accepted_by": COORDINATOR_ID,
            "candidate_id": candidate_id,
        }
    )
    run["candidates"].append(
        {
            "candidate_id": candidate_id,
            "kind": "file",
            "location": f"results/{slug}.json",
            "scope": f"synthetic {slug} result",
            "produced_by": attempt_id,
            "consumes": [],
            "identity": identity,
            "authority_identities": authorities,
            "acceptance_criteria": [criterion],
            "observed_at": prefix + "04:00Z",
            "review_required": False,
        }
    )
    run["evidence"].append(
        evidence_row(
            evidence_id=f"evidence_{slug}_001",
            candidate_id=candidate_id,
            criterion=criterion,
            candidate_identity=identity,
            authority_identities=authorities,
            observed_at=prefix + "04:00Z",
        )
    )
    return task_id, attempt_id, candidate_id


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CoordinationStateAuditTests(unittest.TestCase):
    def assert_audit_error(self, run: dict, expected: str, **kwargs) -> AUDIT.CoordinationAuditError:
        with self.assertRaises(AUDIT.CoordinationAuditError) as raised:
            AUDIT.audit_coordination_state(run, **kwargs)
        self.assertIn(expected, "\n".join(raised.exception.errors))
        return raised.exception

    def test_delivery_does_not_equal_acceptance(self) -> None:
        run = empty_run()
        run["tasks"].append(
            {
                "task_id": "task_demo",
                "status": "running",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_demo_001",
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_demo_001",
                "task_id": "task_demo",
                "owner": "worker_a",
                "delivered_at": "2026-08-25T01:00:00Z",
            }
        )

        report = AUDIT.audit_coordination_state(run)
        self.assertEqual(["attempt_demo_001"], report["delivered_not_returned"])

        run["tasks"][0]["status"] = "succeeded"
        self.assert_audit_error(run, "lacks accepted current attempt")

    def test_cli_emits_a_closure_audit_report(self) -> None:
        with isolated_parent() as parent:
            run_path = parent / "run.json"
            run_path.write_text(json.dumps(empty_run()), encoding="utf-8")
            output = StringIO()

            with redirect_stdout(output):
                exit_code = AUDIT.main(["--run", str(run_path), "--closure"])

            self.assertEqual(0, exit_code)
            report = json.loads(output.getvalue())
            self.assertTrue(report["valid"])
            self.assertTrue(report["closure_ready"])

    def test_required_review_must_be_fresh_read_only_and_clear(self) -> None:
        run = empty_run()
        _, candidate_id, _ = add_accepted_task(
            run, "task_report", review_required=True, owner="worker_a"
        )
        self.assert_audit_error(run, "lacks a completed fresh read-only review")

        run["reviews"].append(
            {
                "review_id": "review_001",
                "candidate_id": candidate_id,
                "reviewer": "worker_a",
                "read_only": True,
                "completed_at": "2026-08-25T01:03:00Z",
                "requirements": ["criterion A"],
                "evidence": ["raw synthetic source"],
                "open_material_findings": [],
            }
        )
        self.assert_audit_error(run, "lacks a completed fresh read-only review")

        run["reviews"][0]["reviewer"] = "reviewer_b"
        run["reviews"][0]["open_material_findings"] = ["finding_001"]
        self.assert_audit_error(run, "lacks a completed fresh read-only review")

        run["reviews"][0]["open_material_findings"] = []
        report = AUDIT.audit_coordination_state(run)
        self.assertTrue(report["valid"])

    def test_current_hybrid_review_passes_fail_closed_closure(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)

        report = AUDIT.audit_coordination_state(
            run, closure=True, require_current_contract=True
        )

        self.assertTrue(report["valid"])
        self.assertTrue(report["closure_ready"])
        self.assertTrue(report["current_contract_ready"])
        self.assertEqual("fail_closed_v2", report["contract_conformance"])
        self.assertEqual(
            "trusted_persisted_attestation", report["provenance_trust_model"]
        )
        self.assertFalse(report["cryptographic_actor_or_creation_proof"])
        self.assertEqual([AUDIT.PROVENANCE_WARNING], report["warnings"])
        self.assertIn(
            "cannot detect a coordinated full-record rewrite or backfill",
            AUDIT.PROVENANCE_WARNING,
        )

    def test_schema_v2_structural_provenance_rejects_incomplete_relabel_and_accepts_attested_origins(self) -> None:
        legacy = empty_run()
        add_accepted_task(legacy, "task_legacy")

        relabeled = deepcopy(legacy)
        relabeled.update(
            {
                "schema_version": 2,
                "skill_commit_at_creation": CURRENT_SKILL_COMMIT,
                "return_contract_version": "task_event_v1",
                "coordinator_id": COORDINATOR_ID,
            }
        )
        self.assert_audit_error(
            relabeled,
            "run.schema_provenance is required for structural fail_closed_v2 conformance",
            require_current_contract=True,
        )

        backfilled_creation = deepcopy(relabeled)
        backfilled_creation["schema_provenance"] = {
            "mode": "created_v2",
            "established_at": "2026-09-01T00:00:00Z",
            "creation_digest": "pending",
        }
        _refresh_creation_provenance(backfilled_creation)
        self.assert_audit_error(
            backfilled_creation,
            "attempt attempt_legacy_001 delivery must be strictly after attested v2 schema provenance establishment",
            require_current_contract=True,
        )

        created = current_run()
        created_report = AUDIT.audit_coordination_state(
            created, require_current_contract=True
        )
        self.assertTrue(created_report["current_contract_ready"])
        self.assertEqual(
            "trusted_persisted_attestation",
            created_report["provenance_trust_model"],
        )
        self.assertFalse(created_report["cryptographic_actor_or_creation_proof"])

        migrated = current_run()
        migrated["run_id"] = "run_0002"
        migrated["schema_provenance"] = {
            "mode": "migrated_from_v1",
            "established_at": "2026-09-01T00:00:00Z",
            "source_run_id": legacy["run_id"],
            "source_run_digest": AUDIT._canonical_sha256(legacy),
            "reason": "adopt the structural fail_closed_v2 contract in a new run",
            "evidence": ["trusted legacy source record captured before migration"],
        }
        migrated_report = AUDIT.audit_coordination_state(
            migrated,
            legacy_run=legacy,
            require_current_contract=True,
        )
        self.assertTrue(migrated_report["current_contract_ready"])
        self.assertEqual("migrated_from_v1", migrated_report["schema_provenance_mode"])

    def test_schema_discriminators_reject_booleans(self) -> None:
        run = current_run()
        run["schema_version"] = True
        self.assert_audit_error(run, "run.schema_version must be 1 or 2")

        packet = current_run()
        add_current_hybrid_task(packet)
        packet["reviews"][0]["packet"]["packet_schema_version"] = True
        _refresh_packet_digest(packet["reviews"][0])
        self.assert_audit_error(
            packet,
            "review review_001.packet.packet_schema_version must be 1",
        )

        recovery = recovery_capsule(active=[], uncertain=[])
        recovery["pending_work"] = []
        recovery["schema_version"] = True
        self.assert_audit_error(
            empty_run(),
            "recovery.schema_version must be 1",
            recovery=recovery,
        )

    def test_schema_v2_requires_all_record_lists_and_explicit_review_flag(self) -> None:
        record_list_fields = (
            "chains",
            "tasks",
            "attempts",
            "candidates",
            "evidence",
            "reviews",
            "supersedes",
            "active_work",
        )
        for field in record_list_fields:
            with self.subTest(contract="v2", field=field):
                current = current_run()
                current.pop(field)
                self.assert_audit_error(
                    current,
                    f"run.{field} is required for schema_version 2",
                    require_current_contract=True,
                )

            with self.subTest(contract="v1", field=field):
                legacy = empty_run()
                legacy.pop(field)
                self.assertTrue(AUDIT.audit_coordination_state(legacy)["valid"])

        missing_review_flag = current_run()
        add_current_hybrid_task(missing_review_flag)
        missing_review_flag["candidates"][0].pop("review_required")
        self.assert_audit_error(
            missing_review_flag,
            "candidate candidate_report_001.review_required must be boolean",
            require_current_contract=True,
        )

        legacy_candidate = empty_run()
        add_accepted_task(legacy_candidate, "task_legacy")
        legacy_candidate["candidates"][0].pop("review_required")
        self.assertTrue(AUDIT.audit_coordination_state(legacy_candidate)["valid"])

    def test_required_review_rejects_coordinator_or_producer_substitution(self) -> None:
        for reviewer, expected in (
            (COORDINATOR_ID, "reviewer must differ from the coordinator"),
            ("worker_a", "reviewer must differ from the producer"),
        ):
            with self.subTest(reviewer=reviewer):
                run = current_run()
                add_current_hybrid_task(run)
                run["reviews"][0]["reviewer"] = reviewer
                self.assert_audit_error(run, expected)

    def test_required_review_rejects_producer_coordinator_identity_overlap(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["attempts"][0]["owner"] = COORDINATOR_ID
        run["reviews"][0]["packet"]["candidate"]["producer"] = COORDINATOR_ID
        _refresh_packet_digest(run["reviews"][0])

        self.assert_audit_error(
            run,
            "producer must differ from the coordinator for required review",
        )

    def test_current_acceptance_requires_the_coordinator_actor(self) -> None:
        for accepted_by in (None, "reviewer_b"):
            with self.subTest(accepted_by=accepted_by):
                run = current_run()
                add_current_hybrid_task(run)
                if accepted_by is None:
                    run["attempts"][0].pop("accepted_by")
                else:
                    run["attempts"][0]["accepted_by"] = accepted_by

                self.assert_audit_error(
                    run,
                    "attempt attempt_report_001.accepted_by must be the coordinator",
                )

    def test_required_review_rejects_mutation_and_open_finding(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["reviewer_actions"]["mutated_candidate"] = True
        self.assert_audit_error(
            run, "reviewer_actions.mutated_candidate must be false"
        )

        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["open_material_findings"] = [
            {
                "criterion_id": "criterion_accuracy",
                "requirement": "values tie to source",
                "expected": "values tie",
                "observed": "one value differs",
                "location": "sheet A1",
                "evidence": "source comparison",
                "impact": "reported result is wrong",
                "requested_delta": "correct and rerun",
            }
        ]
        self.assert_audit_error(
            run, "lacks a returned, coordinator-reconciled independent review"
        )

    def test_one_clean_review_cannot_mask_any_effective_adverse_review(self) -> None:
        for adverse_kind in ("failed criterion", "open finding"):
            with self.subTest(adverse_kind=adverse_kind):
                run = current_run()
                add_current_hybrid_task(run)
                add_adverse_review(
                    run,
                    failed_criterion=adverse_kind == "failed criterion",
                    open_finding=adverse_kind == "open finding",
                )

                self.assert_audit_error(
                    run,
                    "effective review review_adverse_001 has unresolved adverse criteria",
                )

        optional_review = current_run()
        add_current_hybrid_task(optional_review)
        optional_review["candidates"][0]["review_required"] = False
        add_adverse_review(optional_review, failed_criterion=True)
        self.assert_audit_error(
            optional_review,
            "effective review review_adverse_001 has unresolved adverse criteria",
        )

    def test_optional_adverse_review_allows_exact_evidence_bound_adjudication(self) -> None:
        for disposition in (
            "false_positive",
            "nonmaterial",
            "outside_supported_scope",
        ):
            with self.subTest(disposition=disposition):
                run = current_run()
                add_current_hybrid_task(run)
                run["candidates"][0]["review_required"] = False
                adverse = add_adverse_review(
                    run, failed_criterion=True, open_finding=True
                )
                add_optional_adjudication(
                    run, adverse, disposition=disposition
                )

                report = AUDIT.audit_coordination_state(
                    run, closure=True, require_current_contract=True
                )
                self.assertTrue(report["valid"])
                self.assertTrue(report["closure_ready"])

    def test_optional_adjudication_cannot_hide_material_or_invalid_review(self) -> None:
        confirmed = current_run()
        add_current_hybrid_task(confirmed)
        confirmed["candidates"][0]["review_required"] = False
        adverse = add_adverse_review(confirmed, failed_criterion=True)
        add_optional_adjudication(
            confirmed, adverse, disposition="confirmed_material"
        )
        self.assert_audit_error(
            confirmed,
            "effective review review_adverse_001 has unresolved adverse criteria",
        )

        structurally_invalid = current_run()
        add_current_hybrid_task(structurally_invalid)
        structurally_invalid["candidates"][0]["review_required"] = False
        adverse = add_adverse_review(structurally_invalid, failed_criterion=True)
        adverse["reviewer_actions"]["mutated_candidate"] = True
        add_optional_adjudication(structurally_invalid, adverse)
        error = self.assert_audit_error(
            structurally_invalid,
            "optional_adjudication cannot cure a structurally invalid review",
        )
        self.assertIn(
            "effective review review_adverse_001 is not structurally valid",
            error.errors,
        )

        required = current_run()
        add_current_hybrid_task(required)
        adverse = add_adverse_review(required, failed_criterion=True)
        add_optional_adjudication(required, adverse)
        self.assert_audit_error(
            required,
            "optional_adjudication is allowed only when candidate.review_required is false",
        )

        clean = current_run()
        add_current_hybrid_task(clean)
        clean["candidates"][0]["review_required"] = False
        clean["reviews"][0]["optional_adjudication"] = {
            "adjudicated_by": COORDINATOR_ID,
            "adjudicated_at": "2026-09-01T01:07:30Z",
            "reason": "invalid attempt to discard clean work",
            "criterion_adjudications": [],
        }
        self.assert_audit_error(
            clean, "optional_adjudication cannot discard a clean review"
        )

    def test_optional_adjudication_requires_exact_current_evidence_and_chronology(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["candidates"][0]["review_required"] = False
        adverse = add_adverse_review(run, failed_criterion=True)
        add_optional_adjudication(run, adverse)

        cases: list[tuple[str, Any, str]] = [
            (
                "wrong actor",
                lambda value: value["reviews"][1]["optional_adjudication"].__setitem__(
                    "adjudicated_by", "reviewer_c"
                ),
                "optional_adjudication must be owned by the coordinator",
            ),
            (
                "missing criterion",
                lambda value: value["reviews"][1]["optional_adjudication"].__setitem__(
                    "criterion_adjudications", []
                ),
                "must cover every adverse criterion exactly",
            ),
            (
                "wrong evidence",
                lambda value: value["reviews"][1]["optional_adjudication"]
                ["criterion_adjudications"][0].__setitem__(
                    "evidence_ids", ["evidence_report_002"]
                ),
                "optional adjudication evidence evidence_report_002 does not cover criterion criterion_accuracy",
            ),
            (
                "at reconciliation",
                lambda value: value["reviews"][1]["optional_adjudication"].__setitem__(
                    "adjudicated_at", value["reviews"][1]["reconciled_at"]
                ),
                "optional adjudication must be strictly after review reconciliation",
            ),
            (
                "at evidence",
                lambda value: value["reviews"][1]["optional_adjudication"].__setitem__(
                    "adjudicated_at", value["evidence"][0]["observed_at"]
                ),
                "optional adjudication must be strictly after evidence evidence_report_001 observation",
            ),
            (
                "at acceptance",
                lambda value: value["reviews"][1]["optional_adjudication"].__setitem__(
                    "adjudicated_at", value["attempts"][0]["accepted_at"]
                ),
                "acceptance must be strictly after review review_adverse_001 optional adjudication",
            ),
        ]
        for name, mutate, expected in cases:
            with self.subTest(name=name):
                invalid = deepcopy(run)
                mutate(invalid)
                self.assert_audit_error(invalid, expected)

    def test_adverse_review_may_be_superseded_only_by_bound_coordinator_resolution(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        adverse = add_adverse_review(run, failed_criterion=True, open_finding=True)
        adverse["review_status"] = "superseded"
        adverse["resolution"] = {
            "replacement_review_id": "review_001",
            "resolved_by": COORDINATOR_ID,
            "resolved_at": "2026-09-01T01:07:30Z",
            "reason": "fresh re-performance and candidate-bound evidence close the finding",
            "criterion_resolutions": [
                {
                    "criterion_id": "criterion_accuracy",
                    "requirement": "values tie to source",
                    "evidence_ids": ["evidence_report_001"],
                }
            ],
        }

        report = AUDIT.audit_coordination_state(run, require_current_contract=True)
        self.assertTrue(report["valid"])

        wrong_actor = deepcopy(run)
        wrong_actor["reviews"][1]["resolution"]["resolved_by"] = "reviewer_c"
        self.assert_audit_error(
            wrong_actor,
            "review review_adverse_001 resolution must be owned by the coordinator",
        )

        stale_evidence = deepcopy(run)
        stale_evidence["reviews"][1]["resolution"]["criterion_resolutions"][0][
            "evidence_ids"
        ] = ["evidence_report_002"]
        self.assert_audit_error(
            stale_evidence,
            "resolution evidence evidence_report_002 does not cover criterion criterion_accuracy",
        )

        prior_clean_review = deepcopy(run)
        prior_clean_review["reviews"][0]["admitted_at"] = "2026-09-01T01:03:06Z"
        self.assert_audit_error(
            prior_clean_review,
            "review review_adverse_001 replacement admission must be strictly after superseded review reconciliation",
        )

        late_resolution_evidence = deepcopy(run)
        late_resolution_evidence["evidence"][0]["observed_at"] = (
            late_resolution_evidence["reviews"][1]["resolution"]["resolved_at"]
        )
        self.assert_audit_error(
            late_resolution_evidence,
            "review review_adverse_001 resolution must be strictly after evidence "
            "evidence_report_001 observation",
        )

    def test_malformed_replacement_review_id_fails_closed_in_api_and_cli(self) -> None:
        def run_with_replacement_id(replacement_id: object) -> dict:
            run = current_run()
            add_current_hybrid_task(run)
            adverse = add_adverse_review(
                run, failed_criterion=True, open_finding=True
            )
            adverse["review_status"] = "superseded"
            adverse["resolution"] = {
                "replacement_review_id": replacement_id,
                "resolved_by": COORDINATOR_ID,
                "resolved_at": "2026-09-01T01:07:30Z",
                "reason": "fresh re-performance closes the adverse review",
                "criterion_resolutions": [
                    {
                        "criterion_id": "criterion_accuracy",
                        "requirement": "values tie to source",
                        "evidence_ids": ["evidence_report_001"],
                    }
                ],
            }
            return run

        expected = (
            "review review_adverse_001.resolution.replacement_review_id "
            "must be a non-empty string"
        )
        for malformed in ([], {}):
            with self.subTest(surface="api", malformed=malformed):
                self.assert_audit_error(
                    run_with_replacement_id(malformed),
                    expected,
                    require_current_contract=True,
                )

            with self.subTest(surface="cli", malformed=malformed):
                with isolated_parent() as parent:
                    run_path = parent / "run.json"
                    run_path.write_text(
                        json.dumps(run_with_replacement_id(malformed)),
                        encoding="utf-8",
                    )
                    error_output = StringIO()
                    with redirect_stderr(error_output):
                        exit_code = AUDIT.main(
                            [
                                "--run",
                                str(run_path),
                                "--require-current-contract",
                            ]
                        )
                    self.assertEqual(2, exit_code)
                    payload = json.loads(error_output.getvalue())
                    self.assertFalse(payload["valid"])
                    self.assertIn(expected, payload["errors"])

    def test_material_findings_bind_the_current_criterion_and_requirement(self) -> None:
        base_finding = {
            "criterion_id": "criterion_accuracy",
            "requirement": "values tie to source",
            "expected": "values tie",
            "observed": "one value differs",
            "location": "sheet A1",
            "evidence": "source comparison",
            "impact": "reported result is wrong",
            "requested_delta": "correct and rerun",
        }
        cases = (
            (
                "unknown criterion",
                {**base_finding, "criterion_id": "criterion_unknown"},
                "criterion_id references an unknown current criterion",
            ),
            (
                "missing requirement",
                {key: value for key, value in base_finding.items() if key != "requirement"},
                ".requirement must be a non-empty string",
            ),
            (
                "mismatched requirement",
                {**base_finding, "requirement": "stale requirement"},
                ".requirement does not match current acceptance",
            ),
        )
        for name, finding, expected in cases:
            with self.subTest(name=name):
                run = current_run()
                add_current_hybrid_task(run)
                run["reviews"][0]["open_material_findings"] = [finding]
                self.assert_audit_error(run, expected)

    def test_required_review_rejects_stale_candidate_or_authority_packet(self) -> None:
        cases = (
            ("candidate", "packet candidate identity is stale or wrong"),
            ("authority", "packet authority identities are stale or wrong"),
        )
        for case, expected in cases:
            with self.subTest(case=case):
                run = current_run()
                add_current_hybrid_task(run)
                packet = run["reviews"][0]["packet"]
                if case == "candidate":
                    packet["candidate"]["identity"]["value"] = "stale-digest"
                else:
                    packet["authority"]["identities"] = ["authority_v0@sha256:old"]
                _refresh_packet_digest(run["reviews"][0])
                self.assert_audit_error(run, expected)

    def test_review_packet_rejects_nested_bias_and_unknown_row_fields(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["packet"]["authority"]["desired_verdict"] = "pass"
        _refresh_packet_digest(run["reviews"][0])
        self.assert_audit_error(
            run,
            "forbidden verdict-bias key at packet.authority.desired_verdict",
        )

        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["packet"]["review_matrix"][0]["notes"] = "extra"
        _refresh_packet_digest(run["reviews"][0])
        self.assert_audit_error(
            run,
            "packet.review_matrix[0] has unsupported fields: notes",
        )

    def test_review_packet_depth_is_bounded_without_recursive_failure(self) -> None:
        within_limit: Any = "leaf"
        for _ in range(AUDIT.MAX_REVIEW_PACKET_DEPTH):
            within_limit = {"safe": within_limit}
        errors: list[str] = []
        self.assertTrue(
            AUDIT._reject_recursive_packet_bias(
                within_limit,
                path="packet",
                review_id="review_depth_ok",
                errors=errors,
            )
        )
        self.assertEqual([], errors)

        over_limit: Any = "leaf"
        for _ in range(AUDIT.MAX_REVIEW_PACKET_DEPTH + 1):
            over_limit = {"safe": over_limit}
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["packet"]["raw_evidence"] = [over_limit]
        error = self.assert_audit_error(
            run,
            f"packet exceeds maximum nesting depth {AUDIT.MAX_REVIEW_PACKET_DEPTH}",
        )
        depth_errors = [
            item for item in error.errors if "exceeds maximum nesting depth" in item
        ]
        self.assertEqual(1, len(depth_errors))
        self.assertFalse(
            any("packet_digest does not match" in item for item in error.errors)
        )

        canonical_depth: Any = None
        for _ in range(5000):
            canonical_depth = [canonical_depth]
        try:
            digest = AUDIT._canonical_sha256(canonical_depth)
        except ValueError as error:
            self.assertIn("canonical JSON exceeds", str(error))
        else:
            # Python's JSON encoder may handle this iteratively on newer
            # runtimes. The packet-specific depth guard above remains the
            # security boundary; a successful generic digest is also valid.
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_cli_deep_valid_json_returns_structured_error_without_traceback(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["packet"]["raw_evidence"] = ["__DEEP_PACKET__"]
        serialized = json.dumps(run)
        deep_json = "[" * 5000 + "null" + "]" * 5000
        serialized = serialized.replace('"__DEEP_PACKET__"', deep_json, 1)

        with isolated_parent() as parent:
            run_path = parent / "deep-run.json"
            run_path.write_text(serialized, encoding="utf-8")
            error_output = StringIO()
            with redirect_stderr(error_output):
                exit_code = AUDIT.main(["--run", str(run_path)])

        self.assertEqual(2, exit_code)
        rendered_error = error_output.getvalue()
        self.assertNotIn("Traceback", rendered_error)
        payload = json.loads(rendered_error)
        self.assertFalse(payload["valid"])
        self.assertTrue(
            any(
                "cannot read valid JSON" in error
                or "exceeds maximum nesting depth" in error
                for error in payload["errors"]
            )
        )

    def test_required_review_rejects_omitted_criterion_or_evidence(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["packet"]["review_matrix"].pop()
        _refresh_packet_digest(run["reviews"][0])
        self.assert_audit_error(run, "review matrix must cover every criterion exactly")

        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["criterion_results"][0]["evidence"] = []
        self.assert_audit_error(run, "criterion_results[0].evidence must not be empty")

    def test_current_candidate_requires_exact_criterion_evidence_coverage(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        report = AUDIT.audit_coordination_state(run, require_current_contract=True)
        self.assertTrue(report["valid"])

        zero = deepcopy(run)
        zero["tasks"][0]["acceptance_criteria"] = []
        zero["candidates"][0]["acceptance_criteria"] = []
        self.assert_audit_error(
            zero,
            "task task_report.acceptance_criteria must contain at least one criterion",
        )

        missing = deepcopy(run)
        missing["evidence"].pop()
        self.assert_audit_error(
            missing,
            "candidate candidate_report_001 evidence must cover every criterion exactly",
        )

        extra = deepcopy(run)
        extra_row = deepcopy(extra["evidence"][0])
        extra_row.update(
            {
                "evidence_id": "evidence_report_extra",
                "criterion_id": "criterion_unknown",
                "requirement": "unknown requirement",
            }
        )
        extra["evidence"].append(extra_row)
        self.assert_audit_error(
            extra,
            "evidence evidence_report_extra references an unknown current criterion",
        )

        duplicate = deepcopy(run)
        duplicate_row = deepcopy(duplicate["evidence"][0])
        duplicate_row["evidence_id"] = "evidence_report_duplicate"
        duplicate["evidence"].append(duplicate_row)
        self.assert_audit_error(
            duplicate,
            "candidate candidate_report_001 duplicates evidence for criterion criterion_accuracy",
        )

        unmapped = deepcopy(run)
        unmapped["evidence"][0]["candidate_identity"]["value"] = "stale-digest"
        self.assert_audit_error(
            unmapped,
            "evidence evidence_report_001 candidate identity is stale or wrong",
        )

    def test_current_contract_rejects_implicit_waivers(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["candidates"][0]["waivers"] = ["criterion_accuracy"]

        self.assert_audit_error(
            run,
            "candidate candidate_report_001 waivers are outside the v2 audit contract",
        )

    def test_required_review_must_return_and_be_reconciled_before_acceptance(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0].pop("return_event_received_at")
        self.assert_audit_error(
            run,
            "review review_001.return_event_received_at must be a non-empty ISO-8601 timestamp",
        )

        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["reconciled_at"] = None
        error = self.assert_audit_error(
            run,
            "review review_001.reconciled_at must be",
            closure=True,
        )
        self.assertIn(
            "closure requires every delivered return to be coordinator-reconciled: review_001",
            error.errors,
        )

        run = current_run()
        _, attempt_id, _ = add_current_hybrid_task(run)
        for attempt in run["attempts"]:
            if attempt["attempt_id"] == attempt_id:
                attempt["accepted_at"] = "2026-09-01T01:06:30Z"
        self.assert_audit_error(
            run, "accepted before required review reconciliation"
        )

    def test_required_review_reconciliation_must_strictly_precede_acceptance(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["attempts"][0]["accepted_at"] = run["reviews"][0]["reconciled_at"]

        self.assert_audit_error(
            run,
            "required review reconciliation must be strictly before acceptance",
        )

    def test_review_task_event_requires_ready_identity_wait_and_return_cursor(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        for field in ("worker_thread_id", "first_wait_at", "return_cursor"):
            run["reviews"][0].pop(field)

        error = self.assert_audit_error(run, "review review_001.worker_thread_id must be non-empty")
        self.assertIn(
            "review review_001.first_wait_at must be a non-empty ISO-8601 timestamp",
            error.errors,
        )
        self.assertIn(
            "review review_001.return_cursor must be non-empty",
            error.errors,
        )

    def test_required_reviewer_must_use_a_distinct_native_task(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["worker_thread_id"] = run["attempts"][0][
            "worker_thread_id"
        ]
        run["reviews"][0]["worker_host_id"] = run["attempts"][0][
            "worker_host_id"
        ]

        self.assert_audit_error(
            run,
            "review review_001 native task identity must differ from the producer attempt",
        )

    def test_review_admission_and_dispatch_follow_producer_reconciliation(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["reviews"][0]["admitted_at"] = "2026-09-01T01:02:59Z"

        self.assert_audit_error(
            run,
            "review review_001 admission must be strictly after producer return reconciliation",
        )

        equal_dispatch_wait = current_run()
        add_current_hybrid_task(equal_dispatch_wait)
        equal_dispatch_wait["reviews"][0]["delivered_at"] = (
            equal_dispatch_wait["reviews"][0]["first_wait_at"]
        )
        self.assert_audit_error(
            equal_dispatch_wait,
            "review review_001 first wait must be strictly after review dispatch",
        )

    def test_native_wait_may_observe_review_completion_event_and_payload_atomically(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        atomic_at = "2026-09-01T01:06:00Z"
        run["reviews"][0]["completed_at"] = atomic_at
        run["reviews"][0]["return_event_received_at"] = atomic_at
        run["reviews"][0]["returned_at"] = atomic_at

        self.assertTrue(
            AUDIT.audit_coordination_state(
                run, closure=True, require_current_contract=True
            )["valid"]
        )

        event_before_completion = deepcopy(run)
        event_before_completion["reviews"][0]["completed_at"] = (
            "2026-09-01T01:06:01Z"
        )
        self.assert_audit_error(
            event_before_completion,
            "review review_001 return event must not precede completion",
        )

        payload_before_event = deepcopy(run)
        payload_before_event["reviews"][0]["returned_at"] = (
            "2026-09-01T01:05:59Z"
        )
        self.assert_audit_error(
            payload_before_event,
            "review review_001 returned_at must not precede return event",
        )

        equal_reconciliation = deepcopy(run)
        equal_reconciliation["reviews"][0]["reconciled_at"] = atomic_at
        self.assert_audit_error(
            equal_reconciliation,
            "review review_001 reconciliation must be strictly after returned_at",
        )

    def test_task_event_payload_may_share_native_return_event_timestamp(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["attempts"][0]["returned_at"] = run["attempts"][0][
            "return_event_received_at"
        ]
        self.assertTrue(
            AUDIT.audit_coordination_state(
                run, closure=True, require_current_contract=True
            )["valid"]
        )

        payload_before_event = deepcopy(run)
        payload_before_event["attempts"][0]["returned_at"] = (
            "2026-09-01T01:01:59Z"
        )
        self.assert_audit_error(
            payload_before_event,
            "attempt attempt_report_001 returned_at must not precede return event",
        )

        equal_delivery_wait = deepcopy(run)
        equal_delivery_wait["attempts"][0]["first_wait_at"] = (
            equal_delivery_wait["attempts"][0]["delivered_at"]
        )
        self.assert_audit_error(
            equal_delivery_wait,
            "attempt attempt_report_001 first wait must be strictly after delivery",
        )

    def test_review_dispatch_is_a_material_return_first_barrier(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["tasks"].append(
            {
                "task_id": "task_prior",
                "status": "running",
                "owner_surface": "user_visible_task",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_prior_001",
                "authority_identities": ["authority_v1@sha256:source"],
                "acceptance_criteria": [
                    {"criterion_id": "criterion_prior", "requirement": "prior work returns"}
                ],
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_prior_001",
                "task_id": "task_prior",
                "owner": "worker_prior",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_prior",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T01:01:00Z",
                "first_wait_at": "2026-09-01T01:01:10Z",
                "return_event_received_at": "2026-09-01T01:03:15Z",
                "return_cursor": "cursor_prior",
                "returned_at": "2026-09-01T01:03:16Z",
            }
        )

        self.assert_audit_error(
            run,
            "return-first barrier: attempt attempt_prior_001 was not reconciled before dispatching review review_001",
        )

    def test_task_event_running_requires_ready_identity_and_first_wait(self) -> None:
        run = current_run()
        run["tasks"].append(
            {
                "task_id": "task_demo",
                "status": "running",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_demo_001",
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_demo_001",
                "task_id": "task_demo",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "delivered_at": "2026-09-01T01:00:00Z",
            }
        )

        error = self.assert_audit_error(run, "worker_thread_id is required")
        self.assertIn(
            "attempt attempt_demo_001.first_wait_at must be a non-empty ISO-8601 timestamp",
            error.errors,
        )

    def test_any_delivered_task_event_requires_ready_identity_and_first_wait(self) -> None:
        run = current_run()
        run["tasks"].append(
            {
                "task_id": "task_preserved",
                "status": "pending",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": None,
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_preserved_001",
                "task_id": "task_preserved",
                "owner": "worker_old",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "delivered_at": "2026-09-01T01:00:00Z",
            }
        )

        error = self.assert_audit_error(
            run,
            "attempt attempt_preserved_001.worker_thread_id is required for delivered task_event work",
        )
        self.assertIn(
            "attempt attempt_preserved_001.first_wait_at must be a non-empty ISO-8601 timestamp",
            error.errors,
        )

    def test_push_preflight_must_strictly_precede_delivery(self) -> None:
        for preflight in (
            "2026-09-01T01:00:00Z",
            "2026-09-01T01:00:01Z",
        ):
            with self.subTest(preflight=preflight):
                run = current_run(creation_contract="push_v1")
                run["tasks"].append(
                    {
                        "task_id": "task_push",
                        "status": "running",
                        "depends_on": [],
                        "consumes": [],
                        "current_attempt_id": "attempt_push_001",
                    }
                )
                run["attempts"].append(
                    {
                        "attempt_id": "attempt_push_001",
                        "task_id": "task_push",
                        "owner": "worker_push",
                        "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                        "return_mode": "push",
                        "return_contract_version": "push_v1",
                        "push_target": COORDINATOR_ID,
                        "push_preflight_at": preflight,
                        "delivered_at": "2026-09-01T01:00:00Z",
                    }
                )

                self.assert_audit_error(
                    run,
                    "attempt attempt_push_001 delivery must be strictly after push preflight",
                )

    def test_push_return_evidence_must_strictly_follow_delivery(self) -> None:
        run = current_run(creation_contract="push_v1")
        run["tasks"].append(
            {
                "task_id": "task_push",
                "status": "running",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_push_001",
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_push_001",
                "task_id": "task_push",
                "owner": "worker_push",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "push",
                "return_contract_version": "push_v1",
                "push_target": COORDINATOR_ID,
                "push_preflight_at": "2026-09-01T00:50:00Z",
                "delivered_at": "2026-09-01T01:00:00Z",
                "return_event_received_at": "2026-09-01T00:58:00Z",
                "returned_at": "2026-09-01T00:59:00Z",
                "return_reconciled_at": "2026-09-01T00:59:30Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )

        self.assert_audit_error(
            run,
            "attempt attempt_push_001 return event must be strictly after delivery",
        )

    def test_manual_return_must_strictly_follow_delivery(self) -> None:
        run = current_run(creation_contract="manual_v1")
        run["tasks"].append(
            {
                "task_id": "task_manual",
                "status": "running",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_manual_001",
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_manual_001",
                "task_id": "task_manual",
                "owner": "worker_manual",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "manual",
                "return_contract_version": "manual_v1",
                "delivered_at": "2026-09-01T01:00:00Z",
                "returned_at": "2026-09-01T00:58:00Z",
                "return_reconciled_at": "2026-09-01T00:59:00Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )

        self.assert_audit_error(
            run,
            "attempt attempt_manual_001 manual return must be strictly after delivery",
        )

    def test_manual_return_uses_returned_at_as_the_reconciliation_barrier(self) -> None:
        run = current_run(creation_contract="manual_v1")
        criteria = [
            {"criterion_id": "criterion_manual", "requirement": "manual result is correct"}
        ]
        authorities = ["authority_manual_v1"]
        candidate_identity = {"method": "sha256", "value": "digest-manual"}
        run["tasks"].append(
            {
                "task_id": "task_manual",
                "status": "succeeded",
                "owner_surface": "user_visible_task",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_manual_001",
                "authority_identities": authorities,
                "acceptance_criteria": criteria,
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_manual_001",
                "task_id": "task_manual",
                "owner": "worker_manual",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "manual",
                "return_contract_version": "manual_v1",
                "worker_thread_id": "thread_manual",
                "worker_host_id": "host_main",
                "manual_disclosed_at": "2026-09-01T00:50:00Z",
                "manual_disclosure_evidence": ["user was told to relay the result"],
                "delivered_at": "2026-09-01T01:00:00Z",
                "returned_at": "2026-09-01T01:01:00Z",
                "return_reconciled_at": "2026-09-01T01:02:00Z",
                "return_reconciled_by": COORDINATOR_ID,
                "accepted_at": "2026-09-01T01:03:00Z",
                "accepted_by": COORDINATOR_ID,
                "candidate_id": "candidate_manual_001",
            }
        )
        run["candidates"].append(
            {
                "candidate_id": "candidate_manual_001",
                "kind": "message_result",
                "location": "native/manual-return",
                "scope": "synthetic manual result",
                "produced_by": "attempt_manual_001",
                "consumes": [],
                "identity": candidate_identity,
                "authority_identities": authorities,
                "acceptance_criteria": deepcopy(criteria),
                "observed_at": "2026-09-01T01:02:10Z",
                "review_required": False,
            }
        )
        run["evidence"].append(
            evidence_row(
                evidence_id="evidence_manual_001",
                candidate_id="candidate_manual_001",
                criterion=criteria[0],
                candidate_identity=candidate_identity,
                authority_identities=authorities,
                observed_at="2026-09-01T01:02:30Z",
            )
        )

        report = AUDIT.audit_coordination_state(
            run, closure=True, require_current_contract=True
        )

        self.assertTrue(report["closure_ready"])

    def test_each_return_mode_requires_complete_bound_provenance(self) -> None:
        def build_mode(mode: str) -> dict:
            run = current_run(creation_contract=f"{mode}_v1")
            owner_surface = (
                "internal_subagent" if mode == "automatic" else "user_visible_task"
            )
            run["tasks"].append(
                {
                    "task_id": f"task_{mode}",
                    "status": "running",
                    "owner_surface": owner_surface,
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": f"attempt_{mode}_001",
                    "authority_identities": [f"authority_{mode}_v1"],
                    "acceptance_criteria": [
                        {
                            "criterion_id": f"criterion_{mode}",
                            "requirement": f"{mode} result is correct",
                        }
                    ],
                }
            )
            attempt = {
                "attempt_id": f"attempt_{mode}_001",
                "task_id": f"task_{mode}",
                "owner": f"worker_{mode}",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": mode,
                "return_contract_version": f"{mode}_v1",
                "delivered_at": "2026-09-01T01:00:00Z",
            }
            if mode != "automatic":
                attempt.update(
                    {
                        "worker_thread_id": f"thread_{mode}",
                        "worker_host_id": "host_main",
                    }
                )
            if mode == "push":
                run["coordinator_return_target"] = {
                    "task_id": "coordinator_task_001",
                    "host_id": "host_main",
                }
                attempt.update(
                    {
                        "push_target": deepcopy(run["coordinator_return_target"]),
                        "push_capability": {
                            "name": "send_message_to_thread",
                            "verified_at": "2026-09-01T00:40:00Z",
                            "evidence": ["native send probe reached the exact coordinator target"],
                        },
                        "push_preflight_at": "2026-09-01T00:50:00Z",
                    }
                )
            elif mode == "manual":
                attempt.update(
                    {
                        "manual_disclosed_at": "2026-09-01T00:50:00Z",
                        "manual_disclosure_evidence": [
                            "user was told before dispatch that relay is required"
                        ],
                    }
                )
            elif mode == "task_event":
                attempt.update(
                    {
                        "worker_thread_id": "thread_task_event",
                        "worker_host_id": "host_main",
                        "first_wait_at": "2026-09-01T01:00:10Z",
                    }
                )
            else:
                attempt.update(
                    {
                        "automatic_return": {
                            "surface": "internal_subagent",
                            "parent_coordinator_id": COORDINATOR_ID,
                            "worker_native_id": f"worker_{mode}",
                        },
                        "return_event_received_at": "2026-09-01T01:02:00Z",
                        "returned_at": "2026-09-01T01:02:10Z",
                        "return_reconciled_at": "2026-09-01T01:02:20Z",
                        "return_reconciled_by": COORDINATOR_ID,
                    }
                )
            run["attempts"].append(attempt)
            return run

        for mode in ("task_event", "push", "manual", "automatic"):
            with self.subTest(valid_mode=mode):
                report = AUDIT.audit_coordination_state(
                    build_mode(mode), require_current_contract=True
                )
                self.assertTrue(report["valid"])

        for mode in ("task_event", "push", "manual"):
            with self.subTest(valid_worktree_mode=mode):
                worktree_mode = build_mode(mode)
                worktree_mode["tasks"][0]["owner_surface"] = "worktree"
                self.assertTrue(
                    AUDIT.audit_coordination_state(
                        worktree_mode, require_current_contract=True
                    )["valid"]
                )

        misdirected = build_mode("push")
        misdirected["attempts"][0]["push_target"]["task_id"] = "wrong_task"
        self.assert_audit_error(
            misdirected,
            "attempt attempt_push_001.push_target must match run.coordinator_return_target",
        )

        arbitrary_push_field = build_mode("push")
        arbitrary_push_field["attempts"][0]["push_target"]["alias"] = "coordinator"
        self.assert_audit_error(
            arbitrary_push_field,
            "attempt attempt_push_001.push_target has unsupported fields: alias",
        )

        missing_capability = build_mode("push")
        missing_capability["attempts"][0].pop("push_capability")
        self.assert_audit_error(
            missing_capability,
            "attempt attempt_push_001.push_capability must be an object",
        )

        missing_disclosure = build_mode("manual")
        missing_disclosure["attempts"][0].pop("manual_disclosed_at")
        self.assert_audit_error(
            missing_disclosure,
            "attempt attempt_manual_001.manual_disclosed_at must be a non-empty ISO-8601 timestamp",
        )

        late_disclosure = build_mode("manual")
        late_disclosure["attempts"][0]["manual_disclosed_at"] = (
            late_disclosure["attempts"][0]["delivered_at"]
        )
        self.assert_audit_error(
            late_disclosure,
            "attempt attempt_manual_001 delivery must be strictly after manual disclosure",
        )

        for mode in ("task_event", "push", "manual"):
            with self.subTest(cross_mode_internal_surface=mode):
                wrong_surface = build_mode(mode)
                wrong_surface["tasks"][0]["owner_surface"] = "internal_subagent"
                self.assert_audit_error(
                    wrong_surface,
                    f"attempt attempt_{mode}_001 return mode {mode} requires task "
                    f"task_{mode}.owner_surface to be user_visible_task or worktree",
                )

        missing_surface = build_mode("task_event")
        missing_surface["tasks"][0].pop("owner_surface")
        self.assert_audit_error(
            missing_surface,
            "attempt attempt_task_event_001 delivered work without task task_task_event.owner_surface",
        )

        for owner_surface in ("user_visible_task", "worktree"):
            with self.subTest(automatic_cross_mode_surface=owner_surface):
                wrong_automatic_surface = build_mode("automatic")
                wrong_automatic_surface["tasks"][0]["owner_surface"] = owner_surface
                self.assert_audit_error(
                    wrong_automatic_surface,
                    "attempt attempt_automatic_001 return mode automatic requires task "
                    "task_automatic.owner_surface to be internal_subagent",
                )

        missing_automatic_identity = build_mode("automatic")
        missing_automatic_identity["attempts"][0].pop("automatic_return")
        self.assert_audit_error(
            missing_automatic_identity,
            "attempt attempt_automatic_001.automatic_return must be an object",
        )

        for malformed_mode in ([], {}):
            with self.subTest(malformed_mode=malformed_mode):
                malformed_return_mode = build_mode("task_event")
                malformed_return_mode["attempts"][0]["return_mode"] = malformed_mode
                self.assert_audit_error(
                    malformed_return_mode,
                    f"attempt attempt_task_event_001.return_mode is unsupported: "
                    f"{malformed_mode}",
                )

        coordinator_as_automatic_worker = build_mode("automatic")
        coordinator_as_automatic_worker["attempts"][0]["owner"] = COORDINATOR_ID
        coordinator_as_automatic_worker["attempts"][0]["automatic_return"][
            "worker_native_id"
        ] = COORDINATOR_ID
        self.assert_audit_error(
            coordinator_as_automatic_worker,
            "attempt attempt_automatic_001 automatic worker must differ from the "
            "coordinator parent",
        )

    def test_push_and_manual_producers_require_native_identity_distinct_from_reviewer(self) -> None:
        def build(mode: str) -> dict:
            run = current_run()
            add_current_hybrid_task(run)
            attempt = run["attempts"][0]
            attempt["return_mode"] = mode
            attempt["return_contract_version"] = f"{mode}_v1"
            attempt.pop("first_wait_at")
            attempt.pop("return_cursor")
            if mode == "push":
                run["coordinator_return_target"] = {
                    "task_id": "coordinator_task_001",
                    "host_id": "host_main",
                }
                attempt.update(
                    {
                        "push_target": deepcopy(run["coordinator_return_target"]),
                        "push_capability": {
                            "name": "send_message_to_thread",
                            "verified_at": "2026-09-01T00:40:00Z",
                            "evidence": ["exact native push target verified"],
                        },
                        "push_preflight_at": "2026-09-01T00:50:00Z",
                    }
                )
            else:
                attempt.pop("return_event_received_at")
                attempt.update(
                    {
                        "manual_disclosed_at": "2026-09-01T00:50:00Z",
                        "manual_disclosure_evidence": [
                            "manual relay requirement disclosed before dispatch"
                        ],
                    }
                )
            return run

        for mode in ("push", "manual"):
            with self.subTest(valid_mode=mode):
                self.assertTrue(AUDIT.audit_coordination_state(build(mode))["valid"])

            with self.subTest(missing_native_pair=mode):
                missing_pair = build(mode)
                missing_pair["attempts"][0].pop("worker_thread_id")
                self.assert_audit_error(
                    missing_pair,
                    f"attempt attempt_report_001.worker_thread_id is required for "
                    f"delivered {mode} work",
                )

            with self.subTest(reviewer_reuses_native_pair=mode):
                reused_pair = build(mode)
                reused_pair["reviews"][0]["worker_thread_id"] = (
                    reused_pair["attempts"][0]["worker_thread_id"]
                )
                reused_pair["reviews"][0]["worker_host_id"] = (
                    reused_pair["attempts"][0]["worker_host_id"]
                )
                self.assert_audit_error(
                    reused_pair,
                    "review review_001 native task identity must differ from the producer attempt",
                )

    def test_return_first_barrier_blocks_new_material_dispatch(self) -> None:
        run = current_run()
        for suffix, delivered, first_wait in (
            ("a", "2026-09-01T01:00:00Z", "2026-09-01T01:00:10Z"),
            ("b", "2026-09-01T01:03:00Z", "2026-09-01T01:03:10Z"),
        ):
            task_id = f"task_{suffix}"
            attempt_id = f"attempt_{suffix}_001"
            run["tasks"].append(
                {
                    "task_id": task_id,
                    "status": "running",
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": attempt_id,
                }
            )
            attempt = {
                "attempt_id": attempt_id,
                "task_id": task_id,
                "owner": f"worker_{suffix}",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": f"thread_{suffix}",
                "worker_host_id": "host_main",
                "delivered_at": delivered,
                "first_wait_at": first_wait,
            }
            if suffix == "a":
                attempt.update(
                    {
                        "return_event_received_at": "2026-09-01T01:02:00Z",
                        "return_cursor": "cursor_a",
                        "returned_at": "2026-09-01T01:02:10Z",
                    }
                )
            run["attempts"].append(attempt)

        self.assert_audit_error(
            run,
            "return-first barrier: attempt attempt_a_001 was not reconciled before dispatching attempt_b_001",
        )

    def test_return_first_barrier_rejects_equal_event_and_later_dispatch_time(self) -> None:
        run = current_run()
        run["tasks"].extend(
            [
                {
                    "task_id": "task_a",
                    "status": "running",
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": "attempt_a_001",
                },
                {
                    "task_id": "task_b",
                    "status": "running",
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": "attempt_b_001",
                },
            ]
        )
        run["attempts"].extend(
            [
                {
                    "attempt_id": "attempt_a_001",
                    "task_id": "task_a",
                    "owner": "worker_a",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "task_event",
                    "return_contract_version": "task_event_v1",
                    "worker_thread_id": "thread_a",
                    "worker_host_id": "host_main",
                    "delivered_at": "2026-09-01T01:00:00Z",
                    "first_wait_at": "2026-09-01T01:00:10Z",
                    "return_event_received_at": "2026-09-01T01:02:00Z",
                    "return_cursor": "cursor_a",
                    "returned_at": "2026-09-01T01:02:10Z",
                },
                {
                    "attempt_id": "attempt_b_001",
                    "task_id": "task_b",
                    "owner": "worker_b",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "task_event",
                    "return_contract_version": "task_event_v1",
                    "worker_thread_id": "thread_b",
                    "worker_host_id": "host_main",
                    "delivered_at": "2026-09-01T01:02:00Z",
                    "first_wait_at": "2026-09-01T01:02:10Z",
                },
            ]
        )

        self.assert_audit_error(
            run,
            "return-first barrier: attempt attempt_a_001 was not reconciled before dispatching attempt_b_001",
        )

    def test_legacy_push_to_task_event_requires_explicit_new_attempt_migration(self) -> None:
        run = current_run(
            creation_contract="push_v1", skill_commit=LEGACY_SKILL_COMMIT
        )
        run["coordinator_return_target"] = {
            "task_id": "legacy_coordinator",
            "host_id": "legacy_host",
        }
        run["tasks"].append(
            {
                "task_id": "task_demo",
                "status": "running",
                "owner_surface": "user_visible_task",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_demo_002",
                "authority_identities": ["authority_demo_v1"],
                "acceptance_criteria": [
                    {"criterion_id": "criterion_demo", "requirement": "demo succeeds"}
                ],
            }
        )
        run["attempts"].extend(
            [
                {
                    "attempt_id": "attempt_demo_001",
                    "task_id": "task_demo",
                    "owner": "worker_a",
                    "skill_commit_at_dispatch": LEGACY_SKILL_COMMIT,
                    "return_mode": "push",
                    "return_contract_version": "push_v1",
                    "worker_thread_id": "thread_demo",
                    "worker_host_id": "host_main",
                    "push_target": deepcopy(run["coordinator_return_target"]),
                    "push_capability": {
                        "name": "send_message_to_thread",
                        "verified_at": "2026-09-01T00:40:00Z",
                        "evidence": ["legacy native push capability was verified"],
                    },
                    "push_preflight_at": "2026-09-01T00:50:00Z",
                    "delivered_at": "2026-09-01T00:51:00Z",
                },
                {
                    "attempt_id": "attempt_demo_002",
                    "task_id": "task_demo",
                    "owner": "worker_a",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "task_event",
                    "return_contract_version": "task_event_v1",
                    "worker_thread_id": "thread_demo",
                    "worker_host_id": "host_main",
                    "delivered_at": "2026-09-01T01:24:00Z",
                    "first_wait_at": "2026-09-01T01:24:10Z",
                    "retry_of": "attempt_demo_001",
                    "retry_reason": "migrate the in-flight return surface",
                    "pre_retry_audit": {
                        "native_state_checked": True,
                        "candidate_locations_checked": True,
                        "side_effects_disposition": "reused",
                        "evidence": ["legacy task remained in flight"],
                    },
                },
            ]
        )

        self.assert_audit_error(run, "without an explicit contract_migration")

        run["attempts"][1]["contract_migration"] = {
            "from_attempt_id": "attempt_demo_001",
            "from_skill_commit": LEGACY_SKILL_COMMIT,
            "from_return_contract_version": "push_v1",
            "to_skill_commit": CURRENT_SKILL_COMMIT,
            "to_return_contract_version": "task_event_v1",
            "migrated_at": "2026-09-01T01:23:00Z",
            "reason": "coordinator-owned task events became available",
            "evidence": ["native task and side effects reconciled"],
        }
        self.assertTrue(AUDIT.audit_coordination_state(run)["valid"])

        later_task_event_retry = deepcopy(run)
        later_task_event_retry["tasks"][0]["current_attempt_id"] = "attempt_demo_003"
        later_task_event_retry["attempts"].append(
            {
                "attempt_id": "attempt_demo_003",
                "task_id": "task_demo",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_demo_later",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T01:30:00Z",
                "first_wait_at": "2026-09-01T01:30:10Z",
                "retry_of": "attempt_demo_002",
                "retry_reason": "continue the already migrated native wait contract",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["the migrated attempt was inspected"],
                },
            }
        )
        self.assertTrue(
            AUDIT.audit_coordination_state(later_task_event_retry)["valid"]
        )

        late_reconciled_omitted_push = deepcopy(later_task_event_retry)
        late_reconciled_omitted_push["attempts"][2].update(
            {
                "delivered_at": "2026-09-01T01:50:00Z",
                "first_wait_at": "2026-09-01T01:50:10Z",
            }
        )
        late_reconciled_omitted_push["attempts"].insert(
            0,
            {
                "attempt_id": "attempt_demo_000",
                "task_id": "task_demo",
                "owner": "worker_a",
                "skill_commit_at_dispatch": LEGACY_SKILL_COMMIT,
                "return_mode": "push",
                "return_contract_version": "push_v1",
                "worker_thread_id": "thread_demo_000",
                "worker_host_id": "host_main",
                "push_target": deepcopy(run["coordinator_return_target"]),
                "push_capability": {
                    "name": "send_message_to_thread",
                    "verified_at": "2026-09-01T00:20:00Z",
                    "evidence": ["the earlier push capability was verified"],
                },
                "push_preflight_at": "2026-09-01T00:30:00Z",
                "delivered_at": "2026-09-01T00:45:00Z",
                "return_event_received_at": "2026-09-01T01:35:00Z",
                "returned_at": "2026-09-01T01:36:00Z",
                "return_reconciled_at": "2026-09-01T01:40:00Z",
                "return_reconciled_by": COORDINATOR_ID,
            },
        )
        late_reconciled_omitted_push["supersedes"] = [
            {
                "subject_id": "attempt_demo_000",
                "replacement_id": "attempt_demo_001",
                "reason": "the omitted push was later reconciled and replaced",
            }
        ]
        self.assert_audit_error(
            late_reconciled_omitted_push,
            "attempt attempt_demo_002 retry_of lineage does not include every earlier "
            "unresolved same-task push_v1 attempt: attempt_demo_000",
        )

        superseded_without_pointer = deepcopy(late_reconciled_omitted_push)
        superseded_without_pointer["tasks"][0].update(
            {"status": "superseded", "current_attempt_id": None}
        )
        attempts_by_id = {
            item["attempt_id"]: item for item in superseded_without_pointer["attempts"]
        }
        attempts_by_id["attempt_demo_001"].update(
            {
                "return_event_received_at": "2026-09-01T01:25:00Z",
                "returned_at": "2026-09-01T01:26:00Z",
                "return_reconciled_at": "2026-09-01T01:27:00Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )
        attempts_by_id["attempt_demo_002"].update(
            {
                "uncertain_at": "2026-09-01T01:24:20Z",
                "reconciled_at": "2026-09-01T01:24:30Z",
            }
        )
        attempts_by_id["attempt_demo_003"].update(
            {
                "uncertain_at": "2026-09-01T01:50:20Z",
                "reconciled_at": "2026-09-01T01:50:30Z",
            }
        )
        self.assert_audit_error(
            superseded_without_pointer,
            "attempt attempt_demo_002 retry_of lineage does not include every earlier "
            "unresolved same-task push_v1 attempt: attempt_demo_000",
            closure=True,
        )

        repeated_original_transition = deepcopy(later_task_event_retry)
        repeated_original_transition["attempts"][2]["retry_of"] = "attempt_demo_001"
        repeated_original_transition["attempts"][2]["contract_migration"] = deepcopy(
            repeated_original_transition["attempts"][1]["contract_migration"]
        )
        repeated_original_transition["attempts"][2]["contract_migration"][
            "migrated_at"
        ] = "2026-09-01T01:29:00Z"
        self.assert_audit_error(
            repeated_original_transition,
            "push_v1 attempt attempt_demo_001 has multiple task_event migration transitions",
        )

        side_branch_transition = deepcopy(run)
        side_branch_transition["attempts"].extend(
            [
                {
                    "attempt_id": "attempt_demo_side_push",
                    "task_id": "task_demo",
                    "owner": "worker_a",
                    "skill_commit_at_dispatch": LEGACY_SKILL_COMMIT,
                    "return_mode": "push",
                    "return_contract_version": "push_v1",
                    "worker_thread_id": "thread_demo_side_push",
                    "worker_host_id": "host_main",
                    "push_target": deepcopy(run["coordinator_return_target"]),
                    "push_capability": {
                        "name": "send_message_to_thread",
                        "verified_at": "2026-09-01T01:28:00Z",
                        "evidence": ["the side push capability was verified"],
                    },
                    "push_preflight_at": "2026-09-01T01:29:00Z",
                    "delivered_at": "2026-09-01T01:30:00Z",
                },
                {
                    "attempt_id": "attempt_demo_side_event",
                    "task_id": "task_demo",
                    "owner": "worker_a",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "task_event",
                    "return_contract_version": "task_event_v1",
                    "worker_thread_id": "thread_demo_side_event",
                    "worker_host_id": "host_main",
                    "delivered_at": "2026-09-01T01:40:00Z",
                    "first_wait_at": "2026-09-01T01:40:10Z",
                    "retry_of": "attempt_demo_side_push",
                    "retry_reason": "invalid second migration branch",
                    "pre_retry_audit": {
                        "native_state_checked": True,
                        "candidate_locations_checked": True,
                        "side_effects_disposition": "reused",
                        "evidence": ["the side push was inspected"],
                    },
                    "contract_migration": {
                        "from_attempt_id": "attempt_demo_side_push",
                        "from_skill_commit": LEGACY_SKILL_COMMIT,
                        "from_return_contract_version": "push_v1",
                        "to_skill_commit": CURRENT_SKILL_COMMIT,
                        "to_return_contract_version": "task_event_v1",
                        "migrated_at": "2026-09-01T01:35:00Z",
                        "reason": "invalid second migration branch",
                        "evidence": ["the side branch was reconciled"],
                    },
                },
            ]
        )
        self.assert_audit_error(
            side_branch_transition,
            "task task_demo has multiple push_v1 to task_event_v1 migration transitions",
        )

        incomplete_multi_push = deepcopy(run)
        incomplete_multi_push["attempts"].insert(
            0,
            {
                "attempt_id": "attempt_demo_000",
                "task_id": "task_demo",
                "owner": "worker_a",
                "skill_commit_at_dispatch": LEGACY_SKILL_COMMIT,
                "return_mode": "push",
                "return_contract_version": "push_v1",
                "worker_thread_id": "thread_demo_legacy_000",
                "worker_host_id": "legacy_host",
                "push_target": deepcopy(run["coordinator_return_target"]),
                "push_capability": {
                    "name": "send_message_to_thread",
                    "verified_at": "2026-09-01T00:30:00Z",
                    "evidence": ["earlier push capability was verified"],
                },
                "push_preflight_at": "2026-09-01T00:40:00Z",
                "delivered_at": "2026-09-01T00:45:00Z",
            },
        )
        self.assert_audit_error(
            incomplete_multi_push,
            "attempt attempt_demo_002 retry_of lineage does not include every earlier "
            "unresolved same-task push_v1 attempt: attempt_demo_000",
        )

        complete_multi_push = deepcopy(incomplete_multi_push)
        complete_multi_push["attempts"][1].update(
            {
                "retry_of": "attempt_demo_000",
                "retry_reason": "continue the earlier unresolved push attempt",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["earlier push state was reconciled for retry"],
                },
            }
        )
        self.assertTrue(AUDIT.audit_coordination_state(complete_multi_push)["valid"])

        omitted_lineage = deepcopy(run)
        for field in (
            "retry_of",
            "retry_reason",
            "pre_retry_audit",
            "contract_migration",
        ):
            omitted_lineage["attempts"][1].pop(field)
        self.assert_audit_error(
            omitted_lineage,
            "attempt attempt_demo_002 must directly retry unresolved same-task push_v1 "
            "attempt attempt_demo_001",
        )

        side_chain = deepcopy(run)
        side_chain["attempts"].insert(
            1,
            {
                "attempt_id": "attempt_demo_side",
                "task_id": "task_demo",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "delivered_at": None,
                "retry_of": "attempt_demo_001",
                "retry_reason": "record an intermediate retry",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["legacy task state was inspected"],
                },
            },
        )
        side_chain["attempts"][2]["retry_of"] = "attempt_demo_side"
        side_chain["attempts"][2]["contract_migration"]["from_attempt_id"] = (
            "attempt_demo_side"
        )
        self.assert_audit_error(
            side_chain,
            "attempt attempt_demo_side changes legacy push to task_event without an "
            "explicit contract_migration",
        )

        cyclic_lineage = deepcopy(run)
        cyclic_lineage["attempts"][0].update(
            {
                "retry_of": "attempt_demo_002",
                "retry_reason": "invalid cyclic retry",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["synthetic cycle probe"],
                },
            }
        )
        self.assert_audit_error(
            cyclic_lineage,
            "retry_of lineage contains a cycle",
        )

        equal_to_source_delivery = deepcopy(run)
        equal_to_source_delivery["attempts"][1]["contract_migration"][
            "migrated_at"
        ] = "2026-09-01T00:51:00Z"
        self.assertTrue(AUDIT.audit_coordination_state(equal_to_source_delivery)["valid"])

        masquerade = deepcopy(run)
        masquerade["attempts"][0]["return_mode"] = "task_event"
        masquerade["attempts"][0]["return_contract_version"] = "task_event_v1"
        self.assert_audit_error(
            masquerade,
            "source attempt must preserve push_v1",
        )

        before_source = deepcopy(run)
        before_source["attempts"][1]["contract_migration"]["migrated_at"] = (
            "2026-09-01T00:50:00Z"
        )
        self.assert_audit_error(
            before_source,
            "migrated_at cannot precede source delivered_at",
        )

        for migrated_at in (
            "2026-09-01T01:24:00Z",
            "2026-09-01T01:25:00Z",
        ):
            with self.subTest(migrated_at=migrated_at):
                at_or_after_replacement = deepcopy(run)
                at_or_after_replacement["attempts"][1]["contract_migration"][
                    "migrated_at"
                ] = migrated_at
                self.assert_audit_error(
                    at_or_after_replacement,
                    "migrated_at must be strictly before replacement delivered_at",
                )

    def test_noncurrent_delivered_attempts_require_lineage_or_explicit_reconciled_supersession(self) -> None:
        def build_prior() -> tuple[dict, dict]:
            run = current_run()
            add_current_hybrid_task(run)
            prior = {
                "attempt_id": "attempt_report_000",
                "task_id": "task_report",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_producer",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T00:10:00Z",
                "first_wait_at": "2026-09-01T00:10:10Z",
            }
            run["attempts"].insert(0, prior)
            return run, prior

        legitimate, _ = build_prior()
        legitimate["attempts"][1].update(
            {
                "retry_of": "attempt_report_000",
                "retry_reason": "continue after the first attempt was audited",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["the first attempt and candidate locations were inspected"],
                },
            }
        )
        self.assertTrue(
            AUDIT.audit_coordination_state(
                legitimate, closure=True, require_current_contract=True
            )["closure_ready"]
        )

        hidden_sibling, _ = build_prior()
        self.assert_audit_error(
            hidden_sibling,
            "noncurrent delivered attempt attempt_report_000 is outside current attempt "
            "attempt_report_001 retry lineage and lacks reconciled run-level supersession",
        )

        hidden_later = current_run()
        add_current_hybrid_task(hidden_later)
        hidden_later["attempts"].append(
            {
                "attempt_id": "attempt_report_002",
                "task_id": "task_report",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_producer",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T01:09:00Z",
                "first_wait_at": "2026-09-01T01:09:10Z",
            }
        )
        later_error = self.assert_audit_error(
            hidden_later,
            "noncurrent delivered attempt attempt_report_002 is outside current attempt "
            "attempt_report_001 retry lineage",
            closure=True,
        )
        self.assertIn(
            "closure requires every effective delivered attempt to have returned or been reconciled: "
            "attempt_report_002",
            later_error.errors,
        )

        reversed_retry = deepcopy(hidden_later)
        reversed_retry["attempts"][0].update(
            {
                "retry_of": "attempt_report_002",
                "retry_reason": "invalid retry of later-dispatched work",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["synthetic reversed chronology probe"],
                },
            }
        )
        self.assert_audit_error(
            reversed_retry,
            "attempt attempt_report_001 delivery must be strictly after retry_of "
            "attempt attempt_report_002 delivery",
            closure=True,
        )

        bridged_later = deepcopy(hidden_later)
        bridged_later["attempts"][1].update(
            {
                "uncertain_at": "2026-09-01T01:09:10Z",
                "reconciled_at": "2026-09-01T01:09:20Z",
            }
        )
        authority_id = bridged_later["tasks"][0]["authority_identities"][0]
        bridged_later["supersedes"] = [
            {
                "subject_id": "attempt_report_002",
                "replacement_id": authority_id,
                "reason": "invalid cross-domain bridge",
            },
            {
                "subject_id": authority_id,
                "replacement_id": "attempt_report_001",
                "reason": "invalid bridge to earlier current attempt",
            },
        ]
        self.assert_audit_error(
            bridged_later,
            "subject and replacement must remain within one identity domain",
            closure=True,
        )

        same_domain_bridge = deepcopy(hidden_later)
        same_domain_bridge["attempts"][1].update(
            {
                "uncertain_at": "2026-09-01T01:09:10Z",
                "reconciled_at": "2026-09-01T01:09:20Z",
            }
        )
        same_domain_bridge["attempts"].append(
            {
                "attempt_id": "attempt_report_bridge",
                "task_id": "task_report",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "delivered_at": None,
            }
        )
        same_domain_bridge["supersedes"] = [
            {
                "subject_id": "attempt_report_002",
                "replacement_id": "attempt_report_bridge",
                "reason": "invalid undelivered bridge",
            },
            {
                "subject_id": "attempt_report_bridge",
                "replacement_id": "attempt_report_001",
                "reason": "invalid bridge to an earlier current attempt",
            },
        ]
        self.assert_audit_error(
            same_domain_bridge,
            "run-level supersession path contains attempts without delivered_at: "
            "attempt_report_bridge",
            closure=True,
        )

        reconciled_supersession, prior = build_prior()
        prior.update(
            {
                "uncertain_at": "2026-09-01T00:11:00Z",
                "reconciled_at": "2026-09-01T00:12:00Z",
            }
        )
        reconciled_supersession["supersedes"].append(
            {
                "subject_id": "attempt_report_000",
                "replacement_id": "attempt_report_001",
                "reason": "the first attempt was reconciled and replaced",
            }
        )
        self.assertTrue(
            AUDIT.audit_coordination_state(
                reconciled_supersession,
                closure=True,
                require_current_contract=True,
            )["closure_ready"]
        )

        unreconciled_supersession = deepcopy(reconciled_supersession)
        unreconciled_supersession["attempts"][0].pop("reconciled_at")
        error = self.assert_audit_error(
            unreconciled_supersession,
            "attempt_report_000 is outside current attempt attempt_report_001 retry lineage "
            "and lacks reconciled run-level supersession",
            closure=True,
        )
        self.assertIn(
            "closure requires every effective delivered attempt to have returned or been reconciled: "
            "attempt_report_000",
            error.errors,
        )

    def test_current_contract_gates_task_dependencies(self) -> None:
        run = current_run()
        run["tasks"].extend(
            [
                {
                    "task_id": "task_source",
                    "status": "failed",
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": None,
                },
                {
                    "task_id": "task_child",
                    "status": "running",
                    "depends_on": ["task_source"],
                    "consumes": [],
                    "current_attempt_id": "attempt_child_001",
                },
            ]
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_child_001",
                "task_id": "task_child",
                "owner": "worker_child",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_child",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T01:00:00Z",
                "first_wait_at": "2026-09-01T01:00:10Z",
            }
        )

        self.assert_audit_error(
            run, "task task_child advanced before dependency task_source succeeded"
        )

    def test_dependency_acceptance_must_strictly_precede_effective_child_delivery(self) -> None:
        def build(dependency_accepted_at: str) -> dict:
            run = current_run()
            source_criteria = [
                {"criterion_id": "criterion_source", "requirement": "source is accepted"}
            ]
            source_identity = {"method": "sha256", "value": "digest-source"}
            run["tasks"].extend(
                [
                    {
                        "task_id": "task_source",
                        "status": "succeeded",
                        "owner_surface": "user_visible_task",
                        "depends_on": [],
                        "consumes": [],
                        "current_attempt_id": "attempt_source_001",
                        "authority_identities": ["authority_source_v1"],
                        "acceptance_criteria": source_criteria,
                    },
                    {
                        "task_id": "task_child",
                        "status": "running",
                        "owner_surface": "user_visible_task",
                        "depends_on": ["task_source"],
                        "consumes": ["candidate_source_001"],
                        "current_attempt_id": "attempt_child_001",
                        "authority_identities": ["authority_source_v1"],
                        "acceptance_criteria": [
                            {
                                "criterion_id": "criterion_child",
                                "requirement": "child uses accepted source",
                            }
                        ],
                    },
                ]
            )
            run["attempts"].extend(
                [
                    {
                        "attempt_id": "attempt_source_001",
                        "task_id": "task_source",
                        "owner": "worker_source",
                        "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                        "return_mode": "task_event",
                        "return_contract_version": "task_event_v1",
                        "worker_thread_id": "thread_source",
                        "worker_host_id": "host_main",
                        "delivered_at": "2026-09-01T00:10:00Z",
                        "first_wait_at": "2026-09-01T00:20:00Z",
                        "return_event_received_at": "2026-09-01T00:30:00Z",
                        "return_cursor": "cursor_source",
                        "returned_at": "2026-09-01T00:40:00Z",
                        "return_reconciled_at": "2026-09-01T00:50:00Z",
                        "return_reconciled_by": COORDINATOR_ID,
                        "accepted_at": dependency_accepted_at,
                        "accepted_by": COORDINATOR_ID,
                        "candidate_id": "candidate_source_001",
                    },
                    {
                        "attempt_id": "attempt_child_001",
                        "task_id": "task_child",
                        "owner": "worker_child",
                        "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                        "return_mode": "task_event",
                        "return_contract_version": "task_event_v1",
                        "worker_thread_id": "thread_child",
                        "worker_host_id": "host_main",
                        "delivered_at": "2026-09-01T01:00:00Z",
                        "first_wait_at": "2026-09-01T01:00:10Z",
                    },
                ]
            )
            run["candidates"].append(
                {
                    "candidate_id": "candidate_source_001",
                    "kind": "dataset",
                    "location": "synthetic/source.json",
                    "scope": "synthetic source records",
                    "produced_by": "attempt_source_001",
                    "consumes": [],
                    "identity": source_identity,
                    "authority_identities": ["authority_source_v1"],
                    "acceptance_criteria": deepcopy(source_criteria),
                    "observed_at": "2026-09-01T00:44:00Z",
                    "review_required": False,
                }
            )
            run["evidence"].append(
                evidence_row(
                    evidence_id="evidence_source_001",
                    candidate_id="candidate_source_001",
                    criterion=source_criteria[0],
                    candidate_identity=source_identity,
                    authority_identities=["authority_source_v1"],
                    observed_at="2026-09-01T00:45:00Z",
                )
            )
            return run

        strict_before = build("2026-09-01T00:59:00Z")
        self.assertTrue(AUDIT.audit_coordination_state(strict_before)["valid"])

        consumes_without_depends = build("2026-09-01T00:59:00Z")
        consumes_without_depends["tasks"][1]["depends_on"] = []
        self.assertTrue(
            AUDIT.audit_coordination_state(consumes_without_depends)["valid"]
        )

        late_consumed_source = build("2026-09-01T01:00:00Z")
        late_consumed_source["tasks"][1]["depends_on"] = []
        self.assert_audit_error(
            late_consumed_source,
            "task task_child delivery must be strictly after consumed candidate "
            "candidate_source_001 coordinator acceptance",
        )

        candidate_consumes = build("2026-09-01T00:59:00Z")
        candidate_consumes["tasks"][1]["depends_on"] = []
        candidate_consumes["tasks"][1]["consumes"] = []
        candidate_consumes["attempts"][1]["candidate_id"] = "candidate_child_001"
        child_criteria = candidate_consumes["tasks"][1]["acceptance_criteria"]
        child_authorities = candidate_consumes["tasks"][1]["authority_identities"]
        child_identity = {"method": "sha256", "value": "digest-child"}
        candidate_consumes["candidates"].append(
            {
                "candidate_id": "candidate_child_001",
                "kind": "file",
                "location": "synthetic/child.json",
                "scope": "synthetic child result",
                "produced_by": "attempt_child_001",
                "consumes": ["candidate_source_001"],
                "identity": child_identity,
                "authority_identities": child_authorities,
                "acceptance_criteria": deepcopy(child_criteria),
                "observed_at": "2026-09-01T01:01:00Z",
                "review_required": False,
            }
        )
        candidate_consumes["evidence"].append(
            evidence_row(
                evidence_id="evidence_child_001",
                candidate_id="candidate_child_001",
                criterion=child_criteria[0],
                candidate_identity=child_identity,
                authority_identities=child_authorities,
            )
        )
        self.assertTrue(AUDIT.audit_coordination_state(candidate_consumes)["valid"])

        candidate_consumes_late = deepcopy(candidate_consumes)
        candidate_consumes_late["attempts"][0]["accepted_at"] = (
            candidate_consumes_late["attempts"][1]["delivered_at"]
        )
        self.assert_audit_error(
            candidate_consumes_late,
            "candidate candidate_child_001 production delivery must be strictly after "
            "consumed candidate candidate_source_001 coordinator acceptance",
        )

        for accepted_at in (
            "2026-09-01T01:00:00Z",
            "2026-09-01T01:01:00Z",
        ):
            with self.subTest(accepted_at=accepted_at):
                run = build(accepted_at)
                self.assert_audit_error(
                    run,
                    "task task_child delivery must be strictly after dependency task_source coordinator acceptance",
                )

    def test_retry_ancestors_preserve_dependency_and_consume_causality(self) -> None:
        def build(
            prior_delivery: str,
            prior_wait: str,
            *,
            status: str = "failed",
        ) -> dict:
            run = current_run()
            add_current_hybrid_task(run)
            run["tasks"].append(
                {
                    "task_id": "task_child",
                    "status": status,
                    "owner_surface": "user_visible_task",
                    "depends_on": ["task_report"],
                    "consumes": ["candidate_report_001"],
                    "current_attempt_id": "attempt_child_002",
                    "authority_identities": ["authority_v1@sha256:source"],
                    "acceptance_criteria": [
                        {
                            "criterion_id": "criterion_child",
                            "requirement": "child uses the accepted report",
                        }
                    ],
                }
            )
            run["attempts"].extend(
                [
                    {
                        "attempt_id": "attempt_child_001",
                        "task_id": "task_child",
                        "owner": "worker_child",
                        "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                        "return_mode": "task_event",
                        "return_contract_version": "task_event_v1",
                        "worker_thread_id": "thread_child_001",
                        "worker_host_id": "host_main",
                        "delivered_at": prior_delivery,
                        "first_wait_at": prior_wait,
                    },
                    {
                        "attempt_id": "attempt_child_002",
                        "task_id": "task_child",
                        "owner": "worker_child",
                        "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                        "return_mode": "task_event",
                        "return_contract_version": "task_event_v1",
                        "worker_thread_id": "thread_child_002",
                        "worker_host_id": "host_main",
                        "delivered_at": "2026-09-01T01:09:00Z",
                        "first_wait_at": "2026-09-01T01:09:10Z",
                        "retry_of": "attempt_child_001",
                        "retry_reason": "retry after reconciling the prior attempt",
                        "pre_retry_audit": {
                            "native_state_checked": True,
                            "candidate_locations_checked": True,
                            "side_effects_disposition": "none",
                            "evidence": ["the prior attempt was inspected"],
                        },
                    },
                ]
            )
            return run

        early_ancestor = build(
            "2026-09-01T01:07:30Z", "2026-09-01T01:07:40Z"
        )
        self.assert_audit_error(
            early_ancestor,
            "retry ancestor attempt_child_001 delivery must be strictly after "
            "dependency task_report coordinator acceptance",
        )
        self.assert_audit_error(
            early_ancestor,
            "retry ancestor attempt_child_001 delivery must be strictly after "
            "consumed candidate candidate_report_001 coordinator acceptance",
        )

        valid_ancestor = build(
            "2026-09-01T01:08:30Z", "2026-09-01T01:08:40Z"
        )
        self.assertTrue(AUDIT.audit_coordination_state(valid_ancestor)["valid"])

        superseded_early = build(
            "2026-09-01T01:07:30Z",
            "2026-09-01T01:07:40Z",
            status="superseded",
        )
        superseded_early["attempts"][-1].update(
            {
                "uncertain_at": "2026-09-01T01:09:20Z",
                "reconciled_at": "2026-09-01T01:09:30Z",
            }
        )
        error = self.assert_audit_error(
            superseded_early,
            "retry ancestor attempt_child_001 delivery must be strictly after "
            "dependency task_report coordinator acceptance",
            closure=True,
        )
        self.assertIn(
            "task task_child retry ancestor attempt_child_001 delivery must be strictly "
            "after consumed candidate candidate_report_001 coordinator acceptance",
            error.errors,
        )

        superseded_without_pointer = deepcopy(superseded_early)
        superseded_without_pointer["tasks"][1]["current_attempt_id"] = None
        superseded_without_pointer["attempts"][-2].update(
            {
                "uncertain_at": "2026-09-01T01:07:50Z",
                "reconciled_at": "2026-09-01T01:08:00Z",
            }
        )
        error = self.assert_audit_error(
            superseded_without_pointer,
            "superseded attempt attempt_child_001 delivery must be strictly after "
            "dependency task_report coordinator acceptance",
            closure=True,
        )
        self.assertIn(
            "task task_child superseded attempt attempt_child_001 delivery must be "
            "strictly after consumed candidate candidate_report_001 coordinator acceptance",
            error.errors,
        )

    def test_delivered_effective_work_requires_a_current_attempt_pointer_for_all_outcomes(self) -> None:
        def build(status: str, *, current: bool) -> dict:
            run = current_run()
            run["tasks"].append(
                {
                    "task_id": "task_terminal",
                    "status": status,
                    "owner_surface": "user_visible_task",
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": "attempt_terminal_001" if current else None,
                    "authority_identities": ["authority_terminal_v1"],
                    "acceptance_criteria": [
                        {
                            "criterion_id": "criterion_terminal",
                            "requirement": "terminal attempt remains traceable",
                        }
                    ],
                }
            )
            run["attempts"].append(
                {
                    "attempt_id": "attempt_terminal_001",
                    "task_id": "task_terminal",
                    "owner": "worker_terminal",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "task_event",
                    "return_contract_version": "task_event_v1",
                    "worker_thread_id": "thread_terminal",
                    "worker_host_id": "host_main",
                    "delivered_at": "2026-09-01T01:00:00Z",
                    "first_wait_at": "2026-09-01T01:00:10Z",
                }
            )
            return run

        for status in ("failed", "blocked", "needs_input"):
            with self.subTest(status=status):
                missing_pointer = build(status, current=False)
                self.assert_audit_error(
                    missing_pointer,
                    f"non-superseded task task_terminal with delivered effective work "
                    f"must identify current_attempt_id",
                )
                self.assertTrue(AUDIT.audit_coordination_state(build(status, current=True))["valid"])

        superseded = build("superseded", current=False)
        error = self.assert_audit_error(
            superseded,
            "closure requires every effective delivered attempt to have returned or been "
            "reconciled: attempt_terminal_001",
            closure=True,
        )
        self.assertIn(
            "closure requires every effective delivered attempt to have returned or been "
            "reconciled: attempt_terminal_001",
            error.errors,
        )

        superseded_reconciled = build("superseded", current=False)
        superseded_reconciled["attempts"][0].update(
            {
                "uncertain_at": "2026-09-01T01:01:00Z",
                "reconciled_at": "2026-09-01T01:02:00Z",
            }
        )
        self.assertTrue(
            AUDIT.audit_coordination_state(
                superseded_reconciled,
                closure=True,
                require_current_contract=True,
            )["closure_ready"]
        )

        superseded_returned = build("superseded", current=True)
        superseded_returned["attempts"][0].update(
            {
                "return_event_received_at": "2026-09-01T01:01:00Z",
                "return_cursor": "cursor_terminal",
                "returned_at": "2026-09-01T01:02:00Z",
                "return_reconciled_at": "2026-09-01T01:03:00Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )
        self.assertTrue(
            AUDIT.audit_coordination_state(
                superseded_returned, closure=True, require_current_contract=True
            )["closure_ready"]
        )

    def test_consumes_graph_and_candidate_attempt_links_are_exact_and_unambiguous(self) -> None:
        authority_consume = current_run()
        add_current_hybrid_task(authority_consume)
        authority_id = authority_consume["tasks"][0]["authority_identities"][0]
        authority_consume["tasks"][0]["consumes"] = [authority_id]
        self.assertTrue(AUDIT.audit_coordination_state(authority_consume)["valid"])

        duplicate_task_consume = deepcopy(authority_consume)
        duplicate_task_consume["tasks"][0]["consumes"] = [authority_id, authority_id]
        self.assert_audit_error(
            duplicate_task_consume,
            "task task_report.consumes duplicates identity",
        )

        duplicate_candidate_consume = deepcopy(authority_consume)
        duplicate_candidate_consume["candidates"][0]["consumes"] = [
            authority_id,
            authority_id,
        ]
        self.assert_audit_error(
            duplicate_candidate_consume,
            "candidate candidate_report_001.consumes duplicates identity",
        )

        unknown_candidate = deepcopy(authority_consume)
        unknown_candidate["tasks"][0]["consumes"] = ["candidate_missing_001"]
        self.assert_audit_error(
            unknown_candidate,
            "task task_report.consumes identity candidate_missing_001 is neither a "
            "known candidate nor a declared authority",
        )

        ambiguous = current_run()
        _, _, candidate_id = add_current_hybrid_task(ambiguous)
        ambiguous["tasks"][0]["consumes"] = [candidate_id]
        ambiguous["tasks"][0]["authority_identities"].append(candidate_id)
        ambiguous["candidates"][0]["authority_identities"].append(candidate_id)
        for item in ambiguous["evidence"]:
            item["authority_identities"].append(candidate_id)
        ambiguous["reviews"][0]["packet"]["authority"]["identities"].append(
            candidate_id
        )
        _refresh_packet_digest(ambiguous["reviews"][0])
        self.assert_audit_error(
            ambiguous,
            "task task_report.consumes identity candidate_report_001 is ambiguous "
            "between candidate and declared authority",
        )

        wrong_forward_pointer = current_run()
        add_current_hybrid_task(wrong_forward_pointer)
        wrong_forward_pointer["attempts"][0]["candidate_id"] = "candidate_missing_001"
        self.assert_audit_error(
            wrong_forward_pointer,
            "attempt attempt_report_001.candidate_id references unknown candidate "
            "candidate_missing_001",
        )

        wrong_reverse_pointer = current_run()
        add_current_hybrid_task(wrong_reverse_pointer)
        wrong_reverse_pointer["attempts"][0].pop("candidate_id")
        self.assert_audit_error(
            wrong_reverse_pointer,
            "candidate candidate_report_001.produced_by attempt_report_001 is not linked "
            "back by attempt.candidate_id",
        )

        noncurrent_return = current_run()
        add_current_hybrid_task(noncurrent_return)
        criteria = deepcopy(noncurrent_return["tasks"][0]["acceptance_criteria"])
        authorities = deepcopy(noncurrent_return["tasks"][0]["authority_identities"])
        identity = {"method": "sha256", "value": "digest-shadow"}
        noncurrent_return["attempts"].insert(
            0,
            {
                "attempt_id": "attempt_report_shadow",
                "task_id": "task_report",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_producer",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T00:20:00Z",
                "first_wait_at": "2026-09-01T00:20:10Z",
                "return_event_received_at": "2026-09-01T00:21:00Z",
                "return_cursor": "cursor_shadow",
                "returned_at": "2026-09-01T00:21:10Z",
                "return_reconciled_at": "2026-09-01T00:21:20Z",
                "return_reconciled_by": COORDINATOR_ID,
                "candidate_id": "candidate_shadow_001",
            },
        )
        noncurrent_return["attempts"][1].update(
            {
                "retry_of": "attempt_report_shadow",
                "retry_reason": "continue after reconciling the shadow return",
                "pre_retry_audit": {
                    "native_state_checked": True,
                    "candidate_locations_checked": True,
                    "side_effects_disposition": "reused",
                    "evidence": ["shadow return reconciled before retry"],
                },
            }
        )
        noncurrent_return["candidates"].append(
            {
                "candidate_id": "candidate_shadow_001",
                "kind": "document",
                "location": "results/shadow.xlsx",
                "scope": "synthetic shadow report",
                "produced_by": "attempt_report_001",
                "consumes": [],
                "identity": identity,
                "authority_identities": authorities,
                "acceptance_criteria": criteria,
                "observed_at": "2026-09-01T00:22:00Z",
                "review_required": False,
            }
        )
        for index, criterion in enumerate(criteria, start=1):
            noncurrent_return["evidence"].append(
                evidence_row(
                    evidence_id=f"evidence_shadow_{index:03d}",
                    candidate_id="candidate_shadow_001",
                    criterion=criterion,
                    candidate_identity=identity,
                    authority_identities=authorities,
                    observed_at="2026-09-01T00:22:00Z",
                )
            )
        error = self.assert_audit_error(
            noncurrent_return,
            "attempt attempt_report_shadow.candidate_id candidate_shadow_001 does not "
            "match candidate.produced_by",
        )
        self.assertIn(
            "candidate candidate_shadow_001.produced_by attempt_report_001 is not linked "
            "back by attempt.candidate_id",
            error.errors,
        )

    def test_legacy_schema_is_readable_but_not_current_contract_conformant(self) -> None:
        run = empty_run()
        report = AUDIT.audit_coordination_state(run)
        self.assertEqual("legacy_readable_only", report["contract_conformance"])
        self.assertFalse(report["current_contract_ready"])
        self.assert_audit_error(
            run,
            "current structural fail_closed_v2 conformance requires run.schema_version 2 provenance",
            require_current_contract=True,
        )

    def test_retry_requires_prior_identity_reason_and_pre_retry_audit(self) -> None:
        run = empty_run()
        run["tasks"].append(
            {
                "task_id": "task_demo",
                "status": "running",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_demo_002",
            }
        )
        run["attempts"].extend(
            [
                {
                    "attempt_id": "attempt_demo_001",
                    "task_id": "task_demo",
                    "owner": "worker_a",
                    "delivered_at": "2026-08-25T01:00:00Z",
                    "returned_at": "2026-08-25T01:01:00Z",
                },
                {
                    "attempt_id": "attempt_demo_002",
                    "task_id": "task_demo",
                    "owner": "worker_a",
                    "delivered_at": "2026-08-25T01:02:00Z",
                    "retry_of": "attempt_demo_001",
                    "retry_reason": "resume after a verified tool failure",
                },
            ]
        )

        self.assert_audit_error(run, "pre_retry_audit must be an object")

        run["attempts"][1]["pre_retry_audit"] = {
            "native_state_checked": True,
            "candidate_locations_checked": True,
            "side_effects_disposition": "none",
            "evidence": ["native task returned a concrete tool error"],
        }
        report = AUDIT.audit_coordination_state(run)
        self.assertTrue(report["valid"])

    def test_uncertain_attempt_requires_recovery_and_blocks_closure(self) -> None:
        run = empty_run()
        run["tasks"].append(
            {
                "task_id": "task_demo",
                "status": "running",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_demo_001",
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_demo_001",
                "task_id": "task_demo",
                "owner": "worker_a",
                "delivered_at": "2026-08-25T01:00:00Z",
                "uncertain_at": "2026-08-25T01:05:00Z",
            }
        )
        run["active_work"].append(
            {
                "active_id": "active_demo",
                "kind": "task",
                "owner": "worker_a",
                "task_id": "task_demo",
                "attempt_id": "attempt_demo_001",
                "writes": ["output/demo.txt"],
                "isolation_key": None,
            }
        )

        self.assert_audit_error(run, "require a recovery capsule")

        recovery = recovery_capsule(
            active=["active_demo"], uncertain=["attempt_demo_001"]
        )
        report = AUDIT.audit_coordination_state(run, recovery=recovery)
        self.assertEqual(["attempt_demo_001"], report["unresolved_uncertainty"])
        self.assert_audit_error(
            run,
            "closure requires an empty active_work list",
            recovery=recovery,
            closure=True,
        )

        run["attempts"][0]["reconciled_at"] = "2026-08-25T01:06:00Z"
        run["tasks"][0]["status"] = "superseded"
        run["active_work"] = []
        report = AUDIT.audit_coordination_state(run, closure=True)
        self.assertTrue(report["closure_ready"])

    def test_stale_candidate_cannot_be_latest_result(self) -> None:
        run = empty_run()
        _, candidate_id, _ = add_accepted_task(run, "task_source")
        run["supersedes"].append(
            {
                "subject_id": candidate_id,
                "replacement_id": "candidate_source_002",
                "reason": "authoritative input changed",
            }
        )

        self.assert_audit_error(
            run,
            "latest_result candidate is stale",
            latest_result=latest_result(candidate_id),
        )

        run["tasks"][0]["status"] = "superseded"
        report = AUDIT.audit_coordination_state(
            run, latest_result=latest_result(None)
        )
        self.assertIn(candidate_id, report["stale_candidates"])

    def test_current_result_requires_complete_pointer_identity(self) -> None:
        run = empty_run()
        _, candidate_id, _ = add_accepted_task(run, "task_source")

        for missing_field, expected_error in (
            (
                "run_id",
                "latest_result.run_id must be a non-empty string when candidate_id is set",
            ),
            (
                "result_manifest",
                "latest_result.result_manifest must be a non-empty string when candidate_id is set",
            ),
            (
                "source_digest",
                "latest_result.source_digest must be a non-empty string when candidate_id is set",
            ),
        ):
            pointer = latest_result(candidate_id)
            pointer[missing_field] = None
            self.assert_audit_error(run, expected_error, latest_result=pointer)

        self.assert_audit_error(
            run,
            "latest_result with a non-null candidate_id requires project_root artifact verification",
            latest_result=latest_result(candidate_id),
        )

        null_report = AUDIT.audit_coordination_state(
            run, latest_result=latest_result(None)
        )
        self.assertTrue(null_report["valid"])

        partial_null = latest_result(None)
        partial_null["source_digest"] = "stray-digest"
        self.assert_audit_error(
            run,
            "latest_result.source_digest must be null when candidate_id is null",
            latest_result=partial_null,
        )

        invalid_candidate_type = latest_result(None)
        invalid_candidate_type["candidate_id"] = []
        self.assert_audit_error(
            run,
            "latest_result.candidate_id must be null or a non-empty string",
            latest_result=invalid_candidate_type,
        )

        missing_key = latest_result(None)
        missing_key.pop("source_digest")
        self.assert_audit_error(
            run,
            "latest_result must contain exactly these fields; missing: source_digest",
            latest_result=missing_key,
        )

        extra_key = latest_result(None)
        extra_key["verdict"] = "current"
        self.assert_audit_error(
            run,
            "latest_result must contain exactly these fields; unsupported: verdict",
            latest_result=extra_key,
        )

        with isolated_parent() as parent:
            for malformed_pointer in ([], "not-an-object", 1):
                for root in (None, parent):
                    with self.subTest(
                        malformed_pointer=malformed_pointer,
                        root=bool(root),
                    ):
                        self.assert_audit_error(
                            run,
                            "latest_result must be an object",
                            latest_result=malformed_pointer,
                            project_root=root,
                        )
            for field, malformed in (
                ("candidate_id", []),
                ("run_id", {}),
                ("result_manifest", []),
                ("source_digest", {}),
            ):
                for root in (None, parent):
                    with self.subTest(field=field, root=bool(root)):
                        pointer = latest_result(candidate_id)
                        pointer[field] = malformed
                        self.assert_audit_error(
                            run,
                            f"latest_result.{field} must be a non-empty string when candidate_id is set",
                            latest_result=pointer,
                            project_root=root,
                        )

    def test_cli_malformed_latest_result_returns_json_error_without_type_crash(self) -> None:
        with isolated_parent() as parent:
            run_path = parent / "run.json"
            latest_path = parent / "latest_result.json"
            run_path.write_text(json.dumps(empty_run()), encoding="utf-8")
            malformed = latest_result(None)
            malformed["candidate_id"] = {"not": "a scalar"}
            latest_path.write_text(json.dumps(malformed), encoding="utf-8")

            for include_root in (False, True):
                with self.subTest(include_root=include_root):
                    argv = [
                        "--run",
                        str(run_path),
                        "--latest-result",
                        str(latest_path),
                    ]
                    if include_root:
                        argv.extend(["--project-root", str(parent)])
                    error_output = StringIO()
                    with redirect_stderr(error_output):
                        exit_code = AUDIT.main(argv)
                    self.assertEqual(2, exit_code)
                    payload = json.loads(error_output.getvalue())
                    self.assertFalse(payload["valid"])
                    self.assertIn(
                        "latest_result.candidate_id must be a non-empty string when candidate_id is set",
                        payload["errors"],
                    )

    def test_malformed_reference_values_return_audit_errors_without_type_crash(self) -> None:
        for malformed in ([], {}):
            with self.subTest(reference="attempt.task_id", malformed=malformed):
                run = current_run()
                add_current_hybrid_task(run)
                run["attempts"][0]["task_id"] = malformed
                self.assert_audit_error(
                    run,
                    f"attempt attempt_report_001 references unknown task_id: {malformed}",
                )

            with self.subTest(reference="attempt.candidate_id", malformed=malformed):
                run = current_run()
                add_current_hybrid_task(run)
                run["attempts"][0]["candidate_id"] = malformed
                self.assert_audit_error(
                    run,
                    "attempt attempt_report_001.candidate_id must be null or a "
                    "non-empty string",
                )

            with self.subTest(reference="attempt.retry_of", malformed=malformed):
                run = current_run()
                add_current_hybrid_task(run)
                run["attempts"][0]["retry_of"] = malformed
                self.assert_audit_error(
                    run,
                    f"attempt attempt_report_001 references unknown retry_of: "
                    f"{malformed}",
                )

            with self.subTest(reference="evidence.candidate_id", malformed=malformed):
                run = current_run()
                add_current_hybrid_task(run)
                run["evidence"][0]["candidate_id"] = malformed
                self.assert_audit_error(
                    run,
                    f"evidence evidence_report_001 references unknown candidate_id: "
                    f"{malformed}",
                )

        with isolated_parent() as parent:
            run = current_run()
            add_current_hybrid_task(run)
            run["attempts"][0]["task_id"] = []
            run_path = parent / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            error_output = StringIO()
            with redirect_stderr(error_output):
                exit_code = AUDIT.main(["--run", str(run_path)])
            self.assertEqual(2, exit_code)
            payload = json.loads(error_output.getvalue())
            self.assertFalse(payload["valid"])
            self.assertIn(
                "attempt attempt_report_001 references unknown task_id: []",
                payload["errors"],
            )

    def test_malformed_authority_elements_fail_closed_in_api_and_cli(self) -> None:
        cases = (
            ("task", [], "task task_report.authority_identities"),
            ("task", {}, "task task_report.authority_identities"),
            ("candidate", [], "candidate candidate_report_001.authority_identities"),
            ("candidate", {}, "candidate candidate_report_001.authority_identities"),
        )
        for record_kind, malformed, label in cases:
            def malformed_run() -> dict:
                run = current_run()
                add_current_hybrid_task(run)
                collection = (
                    run["tasks"] if record_kind == "task" else run["candidates"]
                )
                collection[0]["authority_identities"] = [malformed]
                return run

            expected = f"{label} must be a list of non-empty strings"
            with self.subTest(
                surface="api", record_kind=record_kind, malformed=malformed
            ):
                self.assert_audit_error(
                    malformed_run(), expected, require_current_contract=True
                )

            with self.subTest(
                surface="cli", record_kind=record_kind, malformed=malformed
            ):
                with isolated_parent() as parent:
                    run_path = parent / "run.json"
                    run_path.write_text(
                        json.dumps(malformed_run()), encoding="utf-8"
                    )
                    error_output = StringIO()
                    with redirect_stderr(error_output):
                        exit_code = AUDIT.main(
                            [
                                "--run",
                                str(run_path),
                                "--require-current-contract",
                            ]
                        )
                    self.assertEqual(2, exit_code)
                    payload = json.loads(error_output.getvalue())
                    self.assertFalse(payload["valid"])
                    self.assertIn(expected, payload["errors"])

    def test_staged_chain_enforces_one_unlocked_dependency_safe_stage(self) -> None:
        run = empty_run()
        run["chains"] = [
            {
                "chain_id": "chain_demo",
                "mode": "staged",
                "unlocked_stage_id": "stage_002",
                "stage_outline": [
                    {"stage_id": "stage_001", "status": "succeeded"},
                    {"stage_id": "stage_002", "status": "pending"},
                    {"stage_id": "stage_003", "status": "pending"},
                ],
            }
        ]
        self.assertTrue(AUDIT.audit_coordination_state(run)["valid"])

        run["chains"][0]["stage_outline"][0]["status"] = "failed"
        run["chains"][0]["stage_outline"][1]["status"] = "running"
        error = self.assert_audit_error(run, "advanced before dependency stage_001 succeeded")
        self.assertIn(
            "stage chain_demo/stage_002 was unlocked before dependency stage_001 succeeded",
            error.errors,
        )

        run["chains"][0]["stage_outline"][2]["status"] = "running"
        self.assert_audit_error(run, "more than one running stage")

    def test_direct_mode_is_outside_the_coordinator(self) -> None:
        run = empty_run()
        run["chains"] = [{"chain_id": "chain_demo", "mode": "direct"}]

        self.assert_audit_error(run, "unsupported mode: direct")

    def test_pending_stage_blocks_closure_even_without_tasks(self) -> None:
        run = empty_run()
        run["chains"] = [
            {
                "chain_id": "chain_demo",
                "mode": "staged",
                "unlocked_stage_id": "stage_001",
                "stage_outline": [{"stage_id": "stage_001", "status": "pending"}],
            }
        ]
        error = self.assert_audit_error(
            run, "closure requires chain chain_demo to have no unlocked stage", closure=True
        )
        self.assertFalse(error.report["closure_ready"])
        self.assertEqual(["chain_demo/stage_001"], error.report["nonterminal_stages"])

    def test_project_root_audit_verifies_result_files_and_source_identity(self) -> None:
        with isolated_parent() as parent:
            source = parent / "source.json"
            output = parent / "output.md"
            source.write_text('{"synthetic": true}\n', encoding="utf-8")
            output.write_text("synthetic result\n", encoding="utf-8")

            run = empty_run()
            _, candidate_id, _ = add_accepted_task(run, "task_source")
            output_digest = sha256(output)
            run["candidates"][0]["identity"] = {
                "method": "sha256",
                "value": output_digest,
            }
            manifest = {
                "schema_version": 1,
                "binding_id": run["binding_id"],
                "batch_id": run["batch_id"],
                "run_id": run["run_id"],
                "source_manifest": "source.json",
                "source_digest": {"method": "sha256", "value": sha256(source)},
                "current_candidate_id": candidate_id,
                "outputs": [
                    {
                        "location": "output.md",
                        "identity": {"method": "sha256", "value": output_digest},
                    }
                ],
            }
            (parent / "result_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            pointer = latest_result(candidate_id)
            pointer["result_manifest"] = "result_manifest.json"
            pointer["source_digest"] = sha256(source)

            report = AUDIT.audit_coordination_state(
                run, latest_result=pointer, project_root=parent
            )
            self.assertTrue(report["valid"])

            unrelated_output = deepcopy(run)
            unrelated_output["candidates"][0]["identity"] = {
                "method": "sha256",
                "value": hashlib.sha256(b"unrelated output").hexdigest(),
            }
            self.assert_audit_error(
                unrelated_output,
                "published current candidate sha256 is not represented exactly by a verified result output",
                latest_result=pointer,
                project_root=parent,
            )

            unsupported_published_identity = deepcopy(run)
            unsupported_published_identity["candidates"][0]["identity"] = {
                "method": "git_commit",
                "value": "0123456789abcdef0123456789abcdef01234567",
            }
            self.assert_audit_error(
                unsupported_published_identity,
                "published current candidate identity must use sha256",
                latest_result=pointer,
                project_root=parent,
            )

            output.write_text("changed result\n", encoding="utf-8")
            self.assert_audit_error(
                run,
                "sha256 does not match the actual output",
                latest_result=pointer,
                project_root=parent,
            )

    def test_supersession_propagates_to_descendants_only(self) -> None:
        run = empty_run()
        _, source_candidate, _ = add_accepted_task(run, "task_source")
        add_accepted_task(run, "task_join", depends_on=["task_source"])
        add_accepted_task(run, "task_independent")
        run["supersedes"].append(
            {
                "subject_id": source_candidate,
                "replacement_id": "candidate_source_002",
                "reason": "source replacement",
            }
        )

        error = self.assert_audit_error(run, "affected task task_source")
        self.assertEqual(
            ["task_join", "task_source"], error.report["stale_tasks"]
        )

        for task in run["tasks"]:
            if task["task_id"] in {"task_source", "task_join"}:
                task["status"] = "superseded"
        report = AUDIT.audit_coordination_state(run)
        self.assertNotIn("task_independent", report["stale_tasks"])

    def test_superseded_attempt_stales_its_task_and_candidate(self) -> None:
        run = empty_run()
        attempt_id, candidate_id, _ = add_accepted_task(run, "task_source")
        run["supersedes"].append(
            {
                "subject_id": attempt_id,
                "replacement_id": "attempt_source_002",
                "reason": "the earlier attempt used replaced authority",
            }
        )

        error = self.assert_audit_error(run, "affected task task_source")
        self.assertIn(candidate_id, error.report["stale_candidates"])

    def test_run_supersedes_is_the_only_typed_acyclic_supersession_authority(self) -> None:
        candidate_local = current_run()
        add_current_hybrid_task(candidate_local)
        candidate_local["candidates"][0]["supersedes"] = "candidate_report_000"
        self.assert_audit_error(
            candidate_local,
            "candidate candidate_report_001 has unsupported fields: supersedes",
        )

        unknown = current_run()
        add_current_hybrid_task(unknown)
        unknown["supersedes"] = [
            {
                "subject_id": "candidate_report_001",
                "replacement_id": "candidate_missing_002",
                "reason": "synthetic replacement",
            }
        ]
        self.assert_audit_error(
            unknown,
            "supersedes[0].replacement_id references unknown identity: candidate_missing_002",
        )

        cyclic = current_run()
        _, attempt_id, _ = add_current_hybrid_task(cyclic)
        cyclic["attempts"].append(
            {
                "attempt_id": "attempt_report_cycle",
                "task_id": "task_report",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_cycle",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T01:09:00Z",
                "first_wait_at": "2026-09-01T01:09:10Z",
            }
        )
        cyclic["supersedes"] = [
            {
                "subject_id": attempt_id,
                "replacement_id": "attempt_report_cycle",
                "reason": "synthetic first edge",
            },
            {
                "subject_id": "attempt_report_cycle",
                "replacement_id": attempt_id,
                "reason": "synthetic cycle edge",
            },
        ]
        self.assert_audit_error(
            cyclic,
            "run.supersedes contains a cycle",
        )

    def test_overlapping_writers_must_be_serialized_or_isolated(self) -> None:
        run = empty_run()
        run["active_work"] = [
            {
                "active_id": "active_a",
                "kind": "worktree",
                "owner": "worker_a",
                "writes": [r"C:\project\output"],
                "isolation_key": None,
            },
            {
                "active_id": "active_b",
                "kind": "worktree",
                "owner": "worker_b",
                "writes": [r"C:\project\output\report.md"],
                "isolation_key": None,
            },
        ]

        self.assert_audit_error(run, "overlapping writes without distinct isolation")

        isolated = deepcopy(run)
        isolated["active_work"][0]["isolation_key"] = "worktree_a"
        isolated["active_work"][1]["isolation_key"] = "worktree_b"
        self.assertTrue(AUDIT.audit_coordination_state(isolated)["valid"])

        serialized = deepcopy(run)
        serialized["active_work"] = serialized["active_work"][:1]
        self.assertTrue(AUDIT.audit_coordination_state(serialized)["valid"])

    def test_write_overlap_detects_filesystem_roots(self) -> None:
        self.assertTrue(AUDIT._writes_overlap("/", "/project/output"))
        self.assertTrue(AUDIT._writes_overlap("C:/", "C:/project/output"))
        self.assertFalse(AUDIT._writes_overlap("C:/project-a", "C:/project-b"))

    def test_attempt_supersession_paths_cannot_bridge_tasks(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        run["attempts"].insert(
            0,
            {
                "attempt_id": "attempt_report_000",
                "task_id": "task_report",
                "owner": "worker_a",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_report_000",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T00:10:00Z",
                "first_wait_at": "2026-09-01T00:10:10Z",
                "uncertain_at": "2026-09-01T00:11:00Z",
                "reconciled_at": "2026-09-01T00:12:00Z",
            },
        )
        run["tasks"].append(
            {
                "task_id": "task_bridge",
                "status": "superseded",
                "owner_surface": "user_visible_task",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_bridge_001",
                "authority_identities": ["authority_bridge_v1"],
                "acceptance_criteria": [
                    {
                        "criterion_id": "criterion_bridge",
                        "requirement": "bridge remains isolated",
                    }
                ],
            }
        )
        run["attempts"].append(
            {
                "attempt_id": "attempt_bridge_001",
                "task_id": "task_bridge",
                "owner": "worker_bridge",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_bridge",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T00:20:00Z",
                "first_wait_at": "2026-09-01T00:20:10Z",
                "return_event_received_at": "2026-09-01T00:21:00Z",
                "return_cursor": "cursor_bridge",
                "returned_at": "2026-09-01T00:22:00Z",
                "return_reconciled_at": "2026-09-01T00:23:00Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )
        run["supersedes"] = [
            {
                "subject_id": "attempt_report_000",
                "replacement_id": "attempt_bridge_001",
                "reason": "invalid cross-task bridge",
            },
            {
                "subject_id": "attempt_bridge_001",
                "replacement_id": "attempt_report_001",
                "reason": "invalid transitive bridge",
            },
        ]

        self.assert_audit_error(
            run,
            "supersedes[0] attempt subject and replacement must stay within one task_id",
        )

    def test_candidate_supersession_uses_strict_observed_at_chronology(self) -> None:
        run = current_run()
        _, _, subject_id = add_current_accepted_task(
            run, "subject", hour=1, status="superseded"
        )
        _, _, replacement_id = add_current_accepted_task(
            run, "replacement", hour=2, status="succeeded"
        )
        run["supersedes"] = [
            {
                "subject_id": subject_id,
                "replacement_id": replacement_id,
                "reason": "a newly observed candidate replaces the prior identity",
            }
        ]
        self.assertTrue(AUDIT.audit_coordination_state(run)["valid"])

        observed_but_unaccepted_replacement = deepcopy(run)
        observed_but_unaccepted_replacement["tasks"][1]["status"] = "failed"
        observed_but_unaccepted_replacement["attempts"][1].pop("accepted_at")
        observed_but_unaccepted_replacement["attempts"][1].pop("accepted_by")
        self.assertTrue(
            AUDIT.audit_coordination_state(observed_but_unaccepted_replacement)[
                "valid"
            ]
        )

        backward = deepcopy(run)
        backward["tasks"][0]["status"] = "succeeded"
        backward["tasks"][1]["status"] = "superseded"
        backward["supersedes"][0].update(
            {"subject_id": replacement_id, "replacement_id": subject_id}
        )
        self.assert_audit_error(
            backward,
            "candidate supersession chronology requires replacement candidate "
            f"{subject_id}.observed_at to be strictly after subject candidate "
            f"{replacement_id}.observed_at",
        )

        equal = deepcopy(run)
        equal["candidates"][1]["observed_at"] = equal["candidates"][0][
            "observed_at"
        ]
        self.assert_audit_error(equal, "candidate supersession chronology")

        missing = deepcopy(run)
        missing["candidates"][0].pop("observed_at")
        self.assert_audit_error(
            missing, "requires both canonical candidate observed_at timestamps"
        )

    def test_push_return_target_native_identity_is_independent(self) -> None:
        def build(target_thread: str) -> dict:
            run = current_run()
            add_current_hybrid_task(run)
            attempt = run["attempts"][0]
            attempt["return_mode"] = "push"
            attempt["return_contract_version"] = "push_v1"
            attempt.pop("first_wait_at")
            attempt.pop("return_cursor")
            run["coordinator_return_target"] = {
                "task_id": target_thread,
                "host_id": "host_main",
            }
            attempt["push_target"] = deepcopy(run["coordinator_return_target"])
            attempt["push_capability"] = {
                "name": "send_message_to_thread",
                "verified_at": "2026-09-01T00:40:00Z",
                "evidence": ["the exact coordinator target was probed"],
            }
            attempt["push_preflight_at"] = "2026-09-01T00:50:00Z"
            return run

        self.assertTrue(
            AUDIT.audit_coordination_state(build("thread_coordinator"))["valid"]
        )
        self.assert_audit_error(
            build("thread_producer"),
            "native task identity must differ from the coordinator return target",
        )
        self.assert_audit_error(
            build("thread_reviewer"),
            "native task identity must differ from the coordinator return target",
        )

        mixed_mode = current_run()
        add_current_hybrid_task(mixed_mode)
        mixed_mode["coordinator_return_target"] = {
            "task_id": "thread_reviewer",
            "host_id": "host_main",
        }
        mixed_mode["tasks"].append(
            {
                "task_id": "task_push_history",
                "status": "superseded",
                "owner_surface": "user_visible_task",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": "attempt_push_history_001",
                "authority_identities": ["authority_push_history"],
                "acceptance_criteria": [
                    {
                        "criterion_id": "criterion_push_history",
                        "requirement": "push history is reconciled",
                    }
                ],
            }
        )
        mixed_mode["attempts"].append(
            {
                "attempt_id": "attempt_push_history_001",
                "task_id": "task_push_history",
                "owner": "worker_push_history",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "push",
                "return_contract_version": "push_v1",
                "worker_thread_id": "thread_push_history",
                "worker_host_id": "host_main",
                "push_target": deepcopy(mixed_mode["coordinator_return_target"]),
                "push_capability": {
                    "name": "send_message_to_thread",
                    "verified_at": "2026-09-01T00:01:00Z",
                    "evidence": ["the coordinator target was verified"],
                },
                "push_preflight_at": "2026-09-01T00:02:00Z",
                "delivered_at": "2026-09-01T00:03:00Z",
                "return_event_received_at": "2026-09-01T00:04:00Z",
                "returned_at": "2026-09-01T00:05:00Z",
                "return_reconciled_at": "2026-09-01T00:06:00Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )
        self.assert_audit_error(
            mixed_mode,
            "review review_001 native task identity must differ from the coordinator "
            "return target",
        )

    def test_retry_delivery_strictly_follows_prior_uncertainty_reconciliation_across_statuses(self) -> None:
        def build(status: str, *, prior_reconciled_at: str) -> dict:
            run = current_run(creation_contract="automatic_v1")
            run["tasks"].append(
                {
                    "task_id": "task_retry",
                    "status": status,
                    "owner_surface": "internal_subagent",
                    "depends_on": [],
                    "consumes": [],
                    "current_attempt_id": "attempt_retry_002",
                    "authority_identities": ["authority_retry_v1"],
                    "acceptance_criteria": [
                        {
                            "criterion_id": "criterion_retry",
                            "requirement": "retry state is reconciled",
                        }
                    ],
                }
            )
            run["attempts"] = [
                {
                    "attempt_id": "attempt_retry_001",
                    "task_id": "task_retry",
                    "owner": "worker_retry_old",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "automatic",
                    "return_contract_version": "automatic_v1",
                    "automatic_return": {
                        "surface": "internal_subagent",
                        "parent_coordinator_id": COORDINATOR_ID,
                        "worker_native_id": "worker_retry_old",
                    },
                    "delivered_at": "2026-09-01T01:00:00Z",
                    "return_event_received_at": "2026-09-01T01:00:20Z",
                    "returned_at": "2026-09-01T01:00:30Z",
                    "return_reconciled_at": "2026-09-01T01:00:40Z",
                    "return_reconciled_by": COORDINATOR_ID,
                    "uncertain_at": "2026-09-01T01:01:00Z",
                    "reconciled_at": prior_reconciled_at,
                },
                {
                    "attempt_id": "attempt_retry_002",
                    "task_id": "task_retry",
                    "owner": "worker_retry_new",
                    "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                    "return_mode": "automatic",
                    "return_contract_version": "automatic_v1",
                    "automatic_return": {
                        "surface": "internal_subagent",
                        "parent_coordinator_id": COORDINATOR_ID,
                        "worker_native_id": "worker_retry_new",
                    },
                    "delivered_at": "2026-09-01T01:04:00Z",
                    "return_event_received_at": "2026-09-01T01:05:00Z",
                    "returned_at": "2026-09-01T01:05:10Z",
                    "return_reconciled_at": "2026-09-01T01:05:20Z",
                    "return_reconciled_by": COORDINATOR_ID,
                    "retry_of": "attempt_retry_001",
                    "retry_reason": "resume only after uncertainty reconciliation",
                    "pre_retry_audit": {
                        "native_state_checked": True,
                        "candidate_locations_checked": True,
                        "side_effects_disposition": "none",
                        "evidence": ["native state and candidate locations were inspected"],
                    },
                },
            ]
            return run

        expected = (
            "attempt attempt_retry_002 delivery must be strictly after retry_of "
            "attempt attempt_retry_001 uncertainty reconciliation"
        )
        for status in ("running", "needs_input", "blocked", "failed", "superseded"):
            for chronology in ("equal", "after"):
                with self.subTest(status=status, chronology=chronology):
                    reconciled_at = (
                        "2026-09-01T01:04:00Z"
                        if chronology == "equal"
                        else "2026-09-01T01:04:30Z"
                    )
                    run = build(status, prior_reconciled_at=reconciled_at)
                    self.assert_audit_error(run, expected)
                    if status == "superseded":
                        self.assert_audit_error(run, expected, closure=True)

        valid = build(
            "superseded", prior_reconciled_at="2026-09-01T01:03:59Z"
        )
        self.assertTrue(
            AUDIT.audit_coordination_state(valid, closure=True)["closure_ready"]
        )

    def test_mixed_mode_coordinator_target_is_distinct_from_every_visible_producer(self) -> None:
        task_event = current_run()
        add_current_hybrid_task(task_event)
        task_event["coordinator_return_target"] = {
            "task_id": "thread_producer",
            "host_id": "host_main",
        }
        self.assert_audit_error(
            task_event,
            "attempt attempt_report_001 native task identity must differ from the "
            "coordinator return target",
            closure=True,
        )

        manual = current_run()
        add_current_hybrid_task(manual)
        manual_attempt = manual["attempts"][0]
        manual_attempt["return_mode"] = "manual"
        manual_attempt["return_contract_version"] = "manual_v1"
        manual_attempt.pop("first_wait_at")
        manual_attempt.pop("return_cursor")
        manual_attempt.pop("return_event_received_at")
        manual_attempt.update(
            {
                "manual_disclosed_at": "2026-09-01T00:50:00Z",
                "manual_disclosure_evidence": [
                    "manual relay was disclosed before delivery"
                ],
            }
        )
        manual["coordinator_return_target"] = {
            "task_id": "thread_producer",
            "host_id": "host_main",
        }
        self.assert_audit_error(
            manual,
            "attempt attempt_report_001 native task identity must differ from the "
            "coordinator return target",
            closure=True,
        )

        different_host = current_run()
        add_current_hybrid_task(different_host)
        different_host["coordinator_return_target"] = {
            "task_id": "thread_producer",
            "host_id": "host_other",
        }
        self.assertTrue(
            AUDIT.audit_coordination_state(different_host, closure=True)[
                "closure_ready"
            ]
        )

        malformed = current_run()
        add_current_hybrid_task(malformed)
        malformed["coordinator_return_target"] = {
            "task_id": "thread_coordinator",
            "host_id": "host_main",
            "alias": "symbolic-name",
        }
        self.assert_audit_error(
            malformed,
            "run.coordinator_return_target has unsupported fields: alias",
        )

        historical = current_run()
        add_current_hybrid_task(historical)
        historical["coordinator_return_target"] = {
            "task_id": "thread_historical",
            "host_id": "host_main",
        }
        historical["tasks"].append(
            {
                "task_id": "task_historical",
                "status": "superseded",
                "owner_surface": "user_visible_task",
                "depends_on": [],
                "consumes": [],
                "current_attempt_id": None,
                "authority_identities": ["authority_historical"],
                "acceptance_criteria": [
                    {
                        "criterion_id": "criterion_historical",
                        "requirement": "historical work is reconciled",
                    }
                ],
            }
        )
        historical["attempts"].append(
            {
                "attempt_id": "attempt_historical_001",
                "task_id": "task_historical",
                "owner": "worker_historical",
                "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                "return_mode": "task_event",
                "return_contract_version": "task_event_v1",
                "worker_thread_id": "thread_historical",
                "worker_host_id": "host_main",
                "delivered_at": "2026-09-01T00:10:00Z",
                "first_wait_at": "2026-09-01T00:10:10Z",
                "return_event_received_at": "2026-09-01T00:11:00Z",
                "return_cursor": "cursor_historical",
                "returned_at": "2026-09-01T00:11:10Z",
                "return_reconciled_at": "2026-09-01T00:11:20Z",
                "return_reconciled_by": COORDINATOR_ID,
            }
        )
        self.assert_audit_error(
            historical,
            "attempt attempt_historical_001 native task identity must differ from "
            "the coordinator return target",
        )

    def test_current_candidate_requires_exact_typed_artifact_metadata(self) -> None:
        for kind in (
            "git",
            "file",
            "directory_manifest",
            "dataset",
            "document",
            "message_result",
        ):
            with self.subTest(valid_kind=kind):
                run = current_run()
                add_current_hybrid_task(run)
                run["candidates"][0]["kind"] = kind
                self.assertTrue(AUDIT.audit_coordination_state(run)["valid"])

        invalid_cases = (
            ("kind", None, "kind must be one of"),
            ("kind", "invented_kind", "kind must be one of"),
            ("kind", "", "kind must be one of"),
            ("kind", True, "kind must be one of"),
            ("kind", [], "kind must be one of"),
            ("kind", {}, "kind must be one of"),
            ("location", None, "location must be a non-empty string"),
            ("location", "", "location must be a non-empty string"),
            ("location", True, "location must be a non-empty string"),
            ("scope", None, "scope must be a non-empty string"),
            ("scope", "", "scope must be a non-empty string"),
            ("scope", True, "scope must be a non-empty string"),
            (
                "observed_at",
                None,
                "observed_at must be a non-empty ISO-8601 timestamp",
            ),
            (
                "observed_at",
                True,
                "observed_at must be a non-empty ISO-8601 timestamp",
            ),
        )
        for field, value, expected in invalid_cases:
            with self.subTest(field=field, value=value):
                run = current_run()
                add_current_hybrid_task(run)
                if value is None:
                    run["candidates"][0].pop(field)
                else:
                    run["candidates"][0][field] = value
                self.assert_audit_error(
                    run,
                    f"candidate candidate_report_001.{expected}",
                )

    def test_acceptance_evidence_observer_is_coordinator_or_qualifying_current_reviewer(self) -> None:
        coordinator_observed = current_run()
        add_current_hybrid_task(coordinator_observed)
        self.assertTrue(
            AUDIT.audit_coordination_state(coordinator_observed, closure=True)[
                "closure_ready"
            ]
        )

        reviewer_observed = current_run()
        add_current_hybrid_task(reviewer_observed)
        for row in reviewer_observed["evidence"]:
            row["observed_by"] = "reviewer_b"
        self.assertTrue(
            AUDIT.audit_coordination_state(reviewer_observed, closure=True)[
                "closure_ready"
            ]
        )

        for observer in ("worker_a", "unrelated_observer"):
            with self.subTest(observer=observer):
                run = current_run()
                add_current_hybrid_task(run)
                run["evidence"][0]["observed_by"] = observer
                self.assert_audit_error(
                    run,
                    f"evidence evidence_report_001.observed_by {observer} is not "
                    "authorized for candidate candidate_report_001",
                )

        nonqualifying = current_run()
        add_current_hybrid_task(nonqualifying)
        nonqualifying["evidence"][0]["observed_by"] = "reviewer_b"
        nonqualifying["reviews"][0]["reviewer_actions"]["mutated_candidate"] = True
        self.assert_audit_error(
            nonqualifying,
            "evidence evidence_report_001.observed_by reviewer_b is not authorized "
            "for candidate candidate_report_001",
        )

        stale = current_run()
        add_current_hybrid_task(stale)
        adverse = add_adverse_review(
            stale, failed_criterion=True, open_finding=True
        )
        adverse["review_status"] = "superseded"
        adverse["resolution"] = {
            "replacement_review_id": "review_001",
            "resolved_by": COORDINATOR_ID,
            "resolved_at": "2026-09-01T01:07:30Z",
            "reason": "fresh re-performance closes the stale review",
            "criterion_resolutions": [
                {
                    "criterion_id": "criterion_accuracy",
                    "requirement": "values tie to source",
                    "evidence_ids": ["evidence_report_001"],
                }
            ],
        }
        stale["evidence"][0]["observed_by"] = "reviewer_c"
        self.assert_audit_error(
            stale,
            "evidence evidence_report_001.observed_by reviewer_c is not authorized "
            "for candidate candidate_report_001",
        )

    def test_current_tasks_reject_local_supersession_and_unknown_fields(self) -> None:
        for field, value in (
            ("supersedes", "task_old"),
            ("unsupported_extension", "fail-open metadata"),
        ):
            with self.subTest(field=field):
                run = current_run()
                add_current_hybrid_task(run)
                run["tasks"][0][field] = value
                self.assert_audit_error(
                    run,
                    f"task task_report has unsupported fields: {field}",
                )

        for malformed_status in ([], {}):
            with self.subTest(malformed_status=malformed_status):
                run = current_run()
                add_current_hybrid_task(run)
                run["tasks"][0]["status"] = malformed_status
                self.assert_audit_error(
                    run,
                    f"task task_report has unsupported status: {malformed_status}",
                )

    def test_attempt_bound_active_work_has_one_matching_accountable_owner(self) -> None:
        def build() -> dict:
            run = current_run()
            for index, owner in ((1, "worker_active_a"), (2, "worker_active_b")):
                task_id = f"task_active_{index}"
                attempt_id = f"attempt_active_{index}_001"
                run["tasks"].append(
                    {
                        "task_id": task_id,
                        "status": "running",
                        "owner_surface": "user_visible_task",
                        "depends_on": [],
                        "consumes": [],
                        "current_attempt_id": attempt_id,
                        "authority_identities": [f"authority_active_{index}"],
                        "acceptance_criteria": [
                            {
                                "criterion_id": f"criterion_active_{index}",
                                "requirement": f"active result {index} is correct",
                            }
                        ],
                    }
                )
                run["attempts"].append(
                    {
                        "attempt_id": attempt_id,
                        "task_id": task_id,
                        "owner": owner,
                        "skill_commit_at_dispatch": CURRENT_SKILL_COMMIT,
                        "return_mode": "task_event",
                        "return_contract_version": "task_event_v1",
                        "worker_thread_id": f"thread_active_{index}",
                        "worker_host_id": "host_main",
                        "delivered_at": f"2026-09-01T01:0{index}:00Z",
                        "first_wait_at": f"2026-09-01T01:0{index}:10Z",
                    }
                )
            return run

        mismatch = build()
        mismatch["active_work"] = [
            {
                "active_id": "active_mismatch",
                "kind": "task",
                "owner": "worker_other",
                "task_id": "task_active_1",
                "attempt_id": "attempt_active_1_001",
                "writes": ["out/active-1"],
                "isolation_key": None,
            }
        ]
        self.assert_audit_error(
            mismatch,
            "active work active_mismatch.owner must match attempt "
            "attempt_active_1_001.owner",
        )

        partial_binding = build()
        partial_binding["active_work"] = [
            {
                "active_id": "active_partial",
                "kind": "task",
                "owner": "worker_active_a",
                "attempt_id": "attempt_active_1_001",
                "writes": ["out/active-1"],
                "isolation_key": None,
            }
        ]
        self.assert_audit_error(
            partial_binding,
            "active work active_partial.task_id is required when attempt_id is set",
        )

        duplicate = build()
        duplicate["active_work"] = [
            {
                "active_id": "active_parent",
                "kind": "task",
                "owner": "worker_active_a",
                "task_id": "task_active_1",
                "attempt_id": "attempt_active_1_001",
                "writes": ["out/shared"],
                "isolation_key": "isolation_parent",
            },
            {
                "active_id": "active_nested",
                "kind": "command",
                "owner": "worker_active_a",
                "task_id": "task_active_1",
                "attempt_id": "attempt_active_1_001",
                "writes": ["out/shared/report.json"],
                "isolation_key": "isolation_nested",
            },
        ]
        self.assert_audit_error(
            duplicate,
            "active work active_nested duplicates accountable attempt "
            "task_active_1/attempt_active_1_001 already claimed by active_parent",
        )

        isolated = build()
        isolated["active_work"] = [
            {
                "active_id": "active_a",
                "kind": "task",
                "owner": "worker_active_a",
                "task_id": "task_active_1",
                "attempt_id": "attempt_active_1_001",
                "writes": ["out/shared"],
                "isolation_key": "worktree_a",
            },
            {
                "active_id": "active_b",
                "kind": "task",
                "owner": "worker_active_b",
                "task_id": "task_active_2",
                "attempt_id": "attempt_active_2_001",
                "writes": ["out/shared/report.json"],
                "isolation_key": "worktree_b",
            },
        ]
        self.assertTrue(AUDIT.audit_coordination_state(isolated)["valid"])

    def test_superseded_authority_stales_bound_candidates_and_descendants(self) -> None:
        run = current_run()
        add_current_hybrid_task(run)
        old_authority = "authority_v1@sha256:source"
        new_authority = "authority_v2@sha256:source"
        authorities = [old_authority, new_authority]
        run["tasks"][0]["authority_identities"] = deepcopy(authorities)
        run["candidates"][0]["authority_identities"] = deepcopy(authorities)
        for item in run["evidence"]:
            item["authority_identities"] = deepcopy(authorities)
        run["reviews"][0]["packet"]["authority"]["identities"] = deepcopy(
            authorities
        )
        _refresh_packet_digest(run["reviews"][0])
        run["tasks"].append(
            {
                "task_id": "task_descendant",
                "status": "pending",
                "owner_surface": "user_visible_task",
                "depends_on": ["task_report"],
                "consumes": [],
                "current_attempt_id": None,
                "authority_identities": [new_authority],
                "acceptance_criteria": [
                    {
                        "criterion_id": "criterion_descendant",
                        "requirement": "descendant uses current authority",
                    }
                ],
            }
        )
        run["supersedes"] = [
            {
                "subject_id": old_authority,
                "replacement_id": new_authority,
                "reason": "the source authority was replaced",
            }
        ]

        error = self.assert_audit_error(
            run, "succeeded task task_report uses stale candidate candidate_report_001"
        )
        self.assertIn(
            "affected task task_report must be marked superseded", error.errors
        )
        self.assertIn(
            "affected task task_descendant must be marked superseded", error.errors
        )

    def test_write_claims_use_safe_posix_lexical_canonicalization(self) -> None:
        for left in (
            "out/a/../shared",
            "out//shared/.",
            "OUT/shared",
        ):
            with self.subTest(left=left):
                run = empty_run()
                run["active_work"] = [
                    {
                        "active_id": "active_a",
                        "kind": "worktree",
                        "owner": "worker_a",
                        "writes": [left],
                        "isolation_key": None,
                    },
                    {
                        "active_id": "active_b",
                        "kind": "worktree",
                        "owner": "worker_b",
                        "writes": ["out/shared/report.md"],
                        "isolation_key": None,
                    },
                ]
                self.assert_audit_error(
                    run,
                    "active work active_a and active_b have overlapping writes without distinct isolation",
                )

        escaped = empty_run()
        escaped["active_work"] = [
            {
                "active_id": "active_escape",
                "kind": "worktree",
                "owner": "worker_a",
                "writes": ["out/../../shared"],
                "isolation_key": None,
            }
        ]
        self.assert_audit_error(
            escaped,
            "active work active_escape.writes[0] escapes its lexical root",
        )

        colon_path = empty_run()
        colon_path["active_work"] = [
            {
                "active_id": "active_colon_a",
                "kind": "worktree",
                "owner": "worker_a",
                "writes": ["out:shared"],
                "isolation_key": None,
            },
            {
                "active_id": "active_colon_b",
                "kind": "worktree",
                "owner": "worker_b",
                "writes": ["out:shared/report.md"],
                "isolation_key": None,
            },
        ]
        self.assert_audit_error(
            colon_path,
            "active work active_colon_a and active_colon_b have overlapping writes",
        )

    def test_project_root_canonicalizes_relative_and_windows_absolute_write_claims(self) -> None:
        def active(active_id: str, owner: str, write: str) -> dict:
            return {
                "active_id": active_id,
                "kind": "worktree",
                "owner": owner,
                "writes": [write],
                "isolation_key": None,
            }

        windows = empty_run()
        windows["active_work"] = [
            active("active_relative", "worker_a", "results"),
            active(
                "active_absolute",
                "worker_b",
                "D:/project/results/report.xlsx",
            ),
        ]
        self.assert_audit_error(
            windows,
            "active work active_absolute and active_relative have overlapping writes",
            project_root="D:/project",
            latest_result=latest_result(None),
        )

        posix = empty_run()
        posix["active_work"] = [
            active("active_relative", "worker_a", "results"),
            active("active_absolute", "worker_b", "/project/results/report.xlsx"),
        ]
        self.assert_audit_error(
            posix,
            "active work active_absolute and active_relative have overlapping writes",
            project_root="/project",
        )

        mixed_without_root = empty_run()
        mixed_without_root["active_work"] = deepcopy(windows["active_work"])
        self.assert_audit_error(
            mixed_without_root,
            "active_work mixes relative and absolute filesystem write claims without project_root",
        )

    def test_write_claim_canonicalization_preserves_safe_compatibility_and_rejects_escape(self) -> None:
        def active(active_id: str, owner: str, write: str) -> dict:
            return {
                "active_id": active_id,
                "kind": "worktree",
                "owner": owner,
                "writes": [write],
                "isolation_key": None,
            }

        all_relative = empty_run()
        all_relative["active_work"] = [
            active("active_a", "worker_a", "out/a"),
            active("active_b", "worker_b", "out/b"),
        ]
        self.assertTrue(AUDIT.audit_coordination_state(all_relative)["valid"])

        all_absolute = empty_run()
        all_absolute["active_work"] = [
            active("active_a", "worker_a", "D:/project/out/a"),
            active("active_b", "worker_b", "D:/project/out/b"),
        ]
        self.assertTrue(AUDIT.audit_coordination_state(all_absolute)["valid"])

        opaque = empty_run()
        opaque["active_work"] = [
            active("active_a", "worker_a", "table:orders"),
            active("active_b", "worker_b", "table:customers"),
        ]
        self.assertTrue(AUDIT.audit_coordination_state(opaque)["valid"])

        for claim, expected in (
            ("../outside", "escapes its lexical root"),
            ("D:project/results", "must not use a drive-relative path"),
            ("D:/outside/report.xlsx", "escapes project_root"),
        ):
            with self.subTest(claim=claim):
                escaped = empty_run()
                escaped["active_work"] = [active("active_escape", "worker_a", claim)]
                self.assert_audit_error(
                    escaped,
                    expected,
                    project_root="D:/project",
                )

        root_only = empty_run()
        report = AUDIT.audit_coordination_state(
            root_only,
            latest_result=latest_result(None),
            project_root="D:/project",
        )
        self.assertTrue(report["valid"])

    def test_unc_write_helpers_preserve_the_server_share_anchor(self) -> None:
        escaping = "//server/share/../target"
        safe_alias = "//SERVER//share/folder/../target"
        descendant = r"\\server\share\target\report.xlsx"

        for escaping_claim in (
            escaping,
            "//server/share/folder/../../target",
        ):
            with self.subTest(escaping_claim=escaping_claim):
                self.assertTrue(
                    AUDIT._write_claim_escapes_lexical_root(escaping_claim)
                )
                self.assertEqual(
                    "//server/share/target",
                    AUDIT._normalize_write(escaping_claim),
                )
        self.assertFalse(AUDIT._write_claim_escapes_lexical_root(safe_alias))
        self.assertEqual("//server/share/target", AUDIT._normalize_write(safe_alias))
        self.assertTrue(AUDIT._writes_overlap(escaping, descendant))
        self.assertEqual("/project/out", AUDIT._normalize_write("///project//out"))
        self.assertFalse(
            AUDIT._write_claim_escapes_lexical_root("////project/out")
        )
        self.assertTrue(
            AUDIT._write_claim_escapes_lexical_root("///../project/out")
        )
        self.assertFalse(
            AUDIT._writes_overlap(
                "//server/share_a/target",
                "//server/share_b/target/report.xlsx",
            )
        )
        for malformed in ("//", "//server", "//server/./out", "//?/C:/out"):
            with self.subTest(malformed=malformed):
                self.assertTrue(
                    AUDIT._write_claim_escapes_lexical_root(malformed)
                )
                errors: list[str] = []
                self.assertEqual(
                    (None, "invalid_unc"),
                    AUDIT._canonicalize_write_claim(
                        malformed,
                        project_root=None,
                        label="claim",
                        errors=errors,
                    ),
                )
                self.assertEqual(
                    ["claim must identify a standard UNC server and share"],
                    errors,
                )

    def test_drive_write_helpers_preserve_root_after_safe_collapse(self) -> None:
        for alias in (
            "D:/",
            "D://",
            "D:///",
            "D:/.",
            "D:/./",
            "D:/folder/..",
            "D:/folder/../",
            r"D:\folder\..",
        ):
            with self.subTest(alias=alias):
                self.assertFalse(AUDIT._write_claim_escapes_lexical_root(alias))
                self.assertEqual("d:/", AUDIT._normalize_write(alias))
                self.assertEqual(("drive", "d:"), AUDIT._write_path_anchor(alias))

        self.assertEqual(
            "d:/bar",
            AUDIT._normalize_write("D:/folder/../bar"),
        )
        self.assertTrue(
            AUDIT._write_claim_escapes_lexical_root("D:/folder/../../bar")
        )

    def test_drive_root_aliases_resolve_and_overlap(self) -> None:
        def active(active_id: str, owner: str, write: str) -> dict:
            return {
                "active_id": active_id,
                "kind": "worktree",
                "owner": owner,
                "writes": [write],
                "isolation_key": None,
            }

        for project_root, write in (
            ("D:/", "."),
            ("D:/", "folder/.."),
            ("D:/", "D://"),
            ("D:/", "D:/."),
            ("D:/", "D:/folder/.."),
            ("D://", "out"),
            ("D:/.", "out"),
        ):
            with self.subTest(project_root=project_root, write=write):
                run = empty_run()
                run["active_work"] = [active("active_drive", "worker_a", write)]
                self.assertTrue(
                    AUDIT.audit_coordination_state(
                        run,
                        project_root=project_root,
                    )["valid"]
                )

        overlap = empty_run()
        overlap["active_work"] = [
            active("active_root", "worker_a", "D:/folder/.."),
            active("active_descendant", "worker_b", "D:/bar"),
        ]
        self.assert_audit_error(
            overlap,
            "active work active_descendant and active_root have overlapping writes",
            project_root="D:/",
        )

        escape = empty_run()
        escape["active_work"] = [
            active("active_escape", "worker_a", "D:/folder/../../bar")
        ]
        self.assert_audit_error(
            escape,
            "active work active_escape.writes[0] escapes its lexical root",
            project_root="D:/",
        )

    def test_unc_write_claims_fail_closed_and_resolve_against_project_root(self) -> None:
        def active(active_id: str, owner: str, write: str) -> dict:
            return {
                "active_id": active_id,
                "kind": "worktree",
                "owner": owner,
                "writes": [write],
                "isolation_key": None,
            }

        root_escape = empty_run()
        root_escape["active_work"] = [
            active("active_escape", "worker_a", r"\\server\share\..\target"),
            active(
                "active_descendant",
                "worker_b",
                r"\\server\share\target\report.xlsx",
            ),
        ]
        self.assert_audit_error(
            root_escape,
            "active work active_escape.writes[0] escapes its lexical root",
        )

        safe_alias = empty_run()
        safe_alias["active_work"] = [
            active(
                "active_alias",
                "worker_a",
                r"\\server\share\folder\..\target",
            ),
            active(
                "active_descendant",
                "worker_b",
                "//SERVER/share/target/report.xlsx",
            ),
        ]
        self.assert_audit_error(
            safe_alias,
            "active work active_alias and active_descendant have overlapping writes",
        )

        for repeated_root, descendant_path in (
            ("///project/out", "/project/out/report.xlsx"),
            ("////server/share/out", "/server/share/out/report.xlsx"),
        ):
            with self.subTest(repeated_root=repeated_root):
                repeated_separators = empty_run()
                repeated_separators["active_work"] = [
                    active("active_alias", "worker_a", repeated_root),
                    active("active_descendant", "worker_b", descendant_path),
                ]
                self.assert_audit_error(
                    repeated_separators,
                    "active work active_alias and active_descendant have overlapping writes",
                )

        rooted = empty_run()
        rooted["active_work"] = [
            active("active_relative", "worker_a", "results"),
            active(
                "active_absolute",
                "worker_b",
                r"\\server\share\project\results\report.xlsx",
            ),
        ]
        self.assert_audit_error(
            rooted,
            "active work active_absolute and active_relative have overlapping writes",
            project_root=r"\\server\share\project",
        )

        for outside_claim in (
            r"\\server\share\project2\report.xlsx",
            r"\\server\other\project\report.xlsx",
            r"\\other\share\project\report.xlsx",
        ):
            with self.subTest(outside_claim=outside_claim):
                outside_root = empty_run()
                outside_root["active_work"] = [
                    active("active_outside", "worker_a", outside_claim)
                ]
                self.assert_audit_error(
                    outside_root,
                    "active work active_outside.writes[0] escapes project_root",
                    project_root=r"\\server\share\project",
                )

        different_shares = empty_run()
        different_shares["active_work"] = [
            active("active_a", "worker_a", r"\\server\share_a\target"),
            active("active_b", "worker_b", r"\\server\share_b\target"),
        ]
        self.assertTrue(AUDIT.audit_coordination_state(different_shares)["valid"])

        for malformed_root in ("//", "//server", "//?/C:/project"):
            with self.subTest(malformed_root=malformed_root):
                invalid_root = empty_run()
                invalid_root["active_work"] = [
                    active("active_relative", "worker_a", "results")
                ]
                self.assert_audit_error(
                    invalid_root,
                    "project_root must be an absolute, lexically unambiguous filesystem path",
                    project_root=malformed_root,
                )

        cross_namespace = empty_run()
        cross_namespace["active_work"] = [
            active("active_unc", "worker_a", "//server/share/out")
        ]
        self.assert_audit_error(
            cross_namespace,
            "active work active_unc.writes[0] escapes project_root",
            project_root="/",
        )

    def test_project_root_preserves_authority_descendant_conflicts(self) -> None:
        def active(active_id: str, owner: str, write: str) -> dict:
            return {
                "active_id": active_id,
                "kind": "worktree",
                "owner": owner,
                "writes": [write],
                "isolation_key": None,
            }

        for descendant in (
            "table:orders/partition",
            "/project/table:orders/partition",
        ):
            with self.subTest(descendant=descendant):
                run = empty_run()
                run["active_work"] = [
                    active("active_token", "worker_a", "table:orders"),
                    active("active_descendant", "worker_b", descendant),
                ]
                self.assert_audit_error(
                    run,
                    "active work active_descendant and active_token have overlapping writes",
                    project_root="/project",
                )

        exact_aliases = (
            ("/project", "/project/table:orders"),
            ("/project", "table:orders/"),
            ("/project", "table:orders/."),
            ("/project", "table:orders/sub/.."),
            ("/project", "./table:orders/"),
            ("D:/project", "D:/project/table:orders"),
            ("//server/share/project", "//server/share/project/table:orders"),
        )
        for project_root, alias in exact_aliases:
            with self.subTest(project_root=project_root, alias=alias):
                run = empty_run()
                run["active_work"] = [
                    active("active_token", "worker_a", "table:orders"),
                    active("active_alias", "worker_b", alias),
                ]
                self.assert_audit_error(
                    run,
                    "active work active_alias and active_token have overlapping writes",
                    project_root=project_root,
                )

        for invalid_claim in ("1:/project/out", "1:project/out", "1:token"):
            with self.subTest(invalid_claim=invalid_claim):
                invalid_drive = empty_run()
                invalid_drive["active_work"] = [
                    active("active_invalid_drive", "worker_a", invalid_claim)
                ]
                self.assert_audit_error(
                    invalid_drive,
                    "must use an ASCII letter for a Windows drive path",
                )


class NotifyReturnContractTests(unittest.TestCase):
    """The notify contract must be a peer of task_event, not a looser mode."""

    def assert_audit_error(self, run: dict, expected: str, **kwargs) -> None:
        with self.assertRaises(AUDIT.CoordinationAuditError) as raised:
            AUDIT.audit_coordination_state(run, **kwargs)
        self.assertIn(expected, "\n".join(raised.exception.errors))

    def notify_run(self) -> dict:
        run = current_run(creation_contract="notify_v1")
        add_current_hybrid_task(run)
        convert_to_notify(run)
        return run

    def test_notify_run_passes_fail_closed_closure(self) -> None:
        report = AUDIT.audit_coordination_state(
            self.notify_run(), closure=True, require_current_contract=True
        )
        self.assertTrue(report["valid"])
        self.assertTrue(report["closure_ready"])
        self.assertTrue(report["current_contract_ready"])
        self.assertEqual("fail_closed_v2", report["contract_conformance"])

    def test_delivered_notify_requires_return_armed_at(self) -> None:
        run = self.notify_run()
        run["attempts"][0].pop("return_armed_at")
        self.assert_audit_error(
            run,
            "attempt attempt_report_001.return_armed_at must be a non-empty "
            "ISO-8601 timestamp",
        )

    def test_notify_delivery_must_strictly_precede_arming(self) -> None:
        run = self.notify_run()
        run["attempts"][0]["return_armed_at"] = run["attempts"][0]["delivered_at"]
        self.assert_audit_error(run, "attempt attempt_report_001 arming")

    def test_notify_arming_must_precede_return_event(self) -> None:
        run = self.notify_run()
        run["attempts"][0]["return_armed_at"] = "2026-09-01T01:05:00Z"
        self.assert_audit_error(run, "attempt attempt_report_001 return event")

    def test_notify_attempt_rejects_task_event_wait_fields(self) -> None:
        for field, value in (
            ("first_wait_at", "2026-09-01T01:00:10Z"),
            ("return_cursor", "cursor_producer_001"),
        ):
            with self.subTest(field=field):
                run = self.notify_run()
                run["attempts"][0][field] = value
                self.assert_audit_error(
                    run,
                    f"attempt attempt_report_001 has unsupported fields: {field}",
                )

    def test_notify_requires_a_user_visible_surface(self) -> None:
        run = self.notify_run()
        run["tasks"][0]["owner_surface"] = "internal_subagent"
        self.assert_audit_error(
            run, "return mode notify requires task task_report.owner_surface"
        )

    def test_delivered_notify_requires_native_worker_identity(self) -> None:
        for field in ("worker_thread_id", "worker_host_id"):
            with self.subTest(field=field):
                run = self.notify_run()
                run["attempts"][0][field] = ""
                self.assert_audit_error(
                    run,
                    f"attempt attempt_report_001.{field} is required for "
                    "delivered notify work",
                )

    def test_notify_contract_version_must_match_its_mode(self) -> None:
        run = self.notify_run()
        run["attempts"][0]["return_contract_version"] = "task_event_v1"
        self.assert_audit_error(
            run, "attempt attempt_report_001.return_contract_version must be notify_v1"
        )

    def test_review_may_return_through_notify(self) -> None:
        run = self.notify_run()
        self.assertEqual(
            "notify", run["reviews"][0]["packet"]["return_contract"]["return_mode"]
        )
        self.assertTrue(AUDIT.audit_coordination_state(run)["valid"])

    def test_review_contract_version_must_match_its_mode(self) -> None:
        run = self.notify_run()
        run["reviews"][0]["packet"]["return_contract"][
            "return_contract_version"
        ] = "task_event_v1"
        _refresh_packet_digest(run["reviews"][0])
        self.assert_audit_error(run, "review review_001 return contract must be notify_v1")

    def test_notify_attempt_cannot_claim_contract_migration(self) -> None:
        run = self.notify_run()
        run["attempts"][0]["contract_migration"] = {
            "from_attempt_id": "attempt_report_000",
            "from_skill_commit": "legacy",
            "from_return_contract_version": "push_v1",
            "to_skill_commit": CURRENT_SKILL_COMMIT,
            "to_return_contract_version": "notify_v1",
            "migrated_at": "2026-09-01T00:59:00Z",
            "reason": "surface changed",
            "evidence": ["native state reconciled"],
        }
        self.assert_audit_error(
            run,
            "attempt attempt_report_001.contract_migration is only valid for "
            "task_event_v1",
        )


if __name__ == "__main__":
    unittest.main()

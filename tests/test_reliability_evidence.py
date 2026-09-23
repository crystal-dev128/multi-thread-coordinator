"""Executable evidence checks for the recovery forward scenarios.

These exercise existing validators, not an LLM or native task runtime.
"""
from contextlib import ExitStack
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from test_audit_coordination_state import (
    AUDIT, REPO_ROOT, add_current_accepted_task, current_run,
    isolated_parent, latest_result, sha256,
)


class ReliabilityEvidenceTests(unittest.TestCase):
    def test_exact_paths_and_copy_parity_work_without_directory_enumeration(self):
        with isolated_parent() as root:
            source = root / "source.json"
            output = root / "attachment.txt"
            stable = root / "stable.txt"
            source.write_bytes(b'{"synthetic_source": "v1"}\n')
            output.write_bytes(b"synthetic attachment\n")
            # Copy from the exact known path, just as the recovery brief permits.
            with ExitStack() as stack:
                for method in ("iterdir", "glob", "rglob"):
                    stack.enter_context(patch.object(Path, method, side_effect=PermissionError("listing unavailable")))
                stack.enter_context(patch("os.scandir", side_effect=PermissionError("listing unavailable")))
                with self.assertRaises(PermissionError):
                    list(root.iterdir())
                shutil.copyfile(output, stable)
                self.assertEqual(sha256(output), sha256(stable))
                run = current_run()
                _, _, candidate_id = add_current_accepted_task(run, "attachment", hour=1)
                identity = {"method": "sha256", "value": sha256(stable)}
                run["candidates"][0]["identity"] = identity
                run["candidates"][0]["location"] = "stable.txt"
                run["evidence"][0]["candidate_identity"] = identity
                manifest = {
                    "schema_version": 1,
                    "binding_id": run["binding_id"], "batch_id": run["batch_id"],
                    "run_id": run["run_id"], "source_manifest": "source.json",
                    "source_digest": {"method": "sha256", "value": sha256(source)},
                    "current_candidate_id": candidate_id,
                    "outputs": [{"location": "stable.txt", "identity": identity,
                                 "digest_parity_with": "attachment.txt"}],
                }
                (root / "result_manifest.json").write_text(json.dumps(manifest))
                pointer = latest_result(candidate_id)
                pointer.update(result_manifest="result_manifest.json", source_digest=sha256(source))
                args = dict(latest_result=pointer, project_root=root, closure=True,
                            require_current_contract=True)
                self.assertTrue(AUDIT.audit_coordination_state(run, **args)["closure_ready"])
                for file, error in (
                    (source, "source_manifest sha256 does not match source_digest"),
                    (stable, "sha256 does not match the actual output"),
                    (output, "does not have digest parity"),
                ):
                    original = file.read_bytes()
                    with self.subTest(file=file.name):
                        file.write_bytes(original + b"changed\n")
                        with self.assertRaises(AUDIT.CoordinationAuditError) as caught:
                            AUDIT.audit_coordination_state(run, **args)
                        self.assertTrue(any(error in item for item in caught.exception.errors))
                    file.write_bytes(original)
                self.assertTrue(AUDIT.audit_coordination_state(run, **args)["closure_ready"])
                output.unlink()
                with self.assertRaises(AUDIT.CoordinationAuditError):
                    AUDIT.audit_coordination_state(run, **args)

    def test_source_precision_reperformance_accepts_correct_and_rejects_rounded_inputs(self):
        with isolated_parent() as root:
            fixture = REPO_ROOT / "tests/fdd_scenarios/existing_workflow/workflow"
            workflow = root / "workflow"
            shutil.copytree(fixture, workflow)
            (workflow / "data/revenue.csv").write_text(
                "period,month,revenue\nQ1 2025,2025-01,3.0049\nQ1 2026,2026-01,4.0098\n"
            )
            results = workflow / "results"
            results.mkdir(exist_ok=True)
            (results / "request_limitations.md").write_text(
                "net_debt: source confirmation and debt mapping are not implemented in this Workflow\n"
            )
            # Independent oracle: preserve source precision until the final boundary.
            exact = (Decimal("4.0098") - Decimal("3.0049")) / Decimal("3.0049") * 100
            rounded_inputs = (Decimal("4.01") - Decimal("3.00")) / Decimal("3.00") * 100
            self.assertEqual("33.44", f"{exact:.2f}")
            self.assertEqual("33.67", f"{rounded_inputs:.2f}")
            candidate = {
                "module": "revenue_summary", "current_period": "Q1 2026",
                "comparative_period": "Q1 2025", "current_revenue": "4.01",
                "comparative_revenue": "3.00", "change_amount": "1.00",
                "change_pct": f"{exact:.2f}", "currency": "LCU",
            }
            spec = importlib.util.spec_from_file_location("precision_workflow", workflow / "scripts/validate_outputs.py")
            validator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(validator)
            summary = results / "current_revenue_summary.json"
            summary.write_text(json.dumps(candidate))
            self.assertEqual([], validator.validate())
            for incorrect in (f"{rounded_inputs:.2f}", "33.54"):
                with self.subTest(incorrect=incorrect):
                    candidate["change_pct"] = incorrect
                    summary.write_text(json.dumps(candidate))
                    self.assertTrue(any("revenue summary mismatch" in e for e in validator.validate()))


if __name__ == "__main__":
    unittest.main()

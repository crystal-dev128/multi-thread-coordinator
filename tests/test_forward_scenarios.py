from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = REPO_ROOT / "tests" / "forward_scenarios"
AUDIT_SCRIPT = (
    REPO_ROOT
    / "multi-thread-coordinator"
    / "scripts"
    / "audit_coordination_state.py"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ForwardScenarioFixtureTests(unittest.TestCase):
    def test_staged_fixture_reproduces_then_resolves_delimiter_failure(self) -> None:
        workspace = REPO_ROOT / f".test-forward-{uuid.uuid4().hex}"
        try:
            shutil.copytree(SCENARIOS / "staged", workspace)
            source_digest = sha256(workspace / "orders.psv")
            importer_digest = sha256(workspace / "import_orders.py")

            failed = subprocess.run(
                [
                    sys.executable,
                    "import_orders.py",
                    "--source",
                    "orders.psv",
                    "--config",
                    "config.json",
                    "--output",
                    "summary.json",
                ],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, failed.returncode)
            self.assertIn("missing required columns", failed.stderr)

            (workspace / "config.json").write_text(
                json.dumps({"delimiter": "|"}, indent=2) + "\n", encoding="utf-8"
            )
            passed = subprocess.run(
                [
                    sys.executable,
                    "import_orders.py",
                    "--source",
                    "orders.psv",
                    "--config",
                    "config.json",
                    "--output",
                    "summary.json",
                ],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, passed.returncode, passed.stderr)
            self.assertEqual(
                {
                    "order_count": 3,
                    "regional_totals": {"North": "25.50", "South": "12.00"},
                    "total_amount": "37.50",
                },
                json.loads((workspace / "summary.json").read_text(encoding="utf-8")),
            )
            self.assertEqual(source_digest, sha256(workspace / "orders.psv"))
            self.assertEqual(importer_digest, sha256(workspace / "import_orders.py"))
        finally:
            if workspace.exists():
                shutil.rmtree(workspace)

    def test_parallel_join_fixture_has_independent_inputs_and_known_join(self) -> None:
        north = json.loads(
            (SCENARIOS / "parallel_join" / "north.json").read_text(encoding="utf-8")
        )
        south = json.loads(
            (SCENARIOS / "parallel_join" / "south.json").read_text(encoding="utf-8")
        )
        north_total = sum(item["duration_hours"] for item in north["programs"])
        south_total = sum(item["duration_hours"] for item in south["programs"])
        self.assertEqual(4.0, north_total)
        self.assertEqual(3.0, south_total)
        self.assertEqual(7.0, north_total + south_total)
        self.assertTrue(
            {item["title"] for item in north["programs"]}.isdisjoint(
                {item["title"] for item in south["programs"]}
            )
        )

    def test_recovery_fixture_requires_reconciliation_before_closure(self) -> None:
        scenario = SCENARIOS / "recovery"
        candidate = (scenario / "outputs" / "candidate.txt").read_text(encoding="utf-8")
        self.assertEqual(1, candidate.count("operation_id=op-001"))
        failed = subprocess.run(
            [
                sys.executable,
                str(AUDIT_SCRIPT),
                "--run",
                str(scenario / "run.json"),
                "--latest-result",
                str(scenario / "latest_result.json"),
                "--recovery",
                str(scenario / "recovery.json"),
                "--closure",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, failed.returncode)
        report = json.loads(failed.stderr)
        self.assertFalse(report["valid"])
        self.assertEqual(["attempt_write_001"], report["unresolved_uncertainty"])

    def test_change_fixture_declares_explicit_authority_replacement(self) -> None:
        v1 = json.loads(
            (SCENARIOS / "change_review" / "authority_v1.json").read_text(
                encoding="utf-8"
            )
        )
        v2 = json.loads(
            (SCENARIOS / "change_review" / "authority_v2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(v1["authority_id"], v2["replaces"])
        self.assertEqual(100.0, v1["revenue"])
        self.assertEqual(100.0, v2["revenue"])
        self.assertEqual((80.0, 20.0), (v1["cost"], v1["margin"]))
        self.assertEqual((85.0, 15.0), (v2["cost"], v2["margin"]))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = REPO_ROOT / "tests" / "fdd_scenarios"


class SyntheticFddScenarioTests(unittest.TestCase):
    def test_adopted_folder_inputs_produce_the_expected_bounded_metrics(self) -> None:
        scenario = SCENARIOS / "adopted_folder"
        with (scenario / "monthly_financials.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            monthly = list(csv.DictReader(handle))
        revenue = sum((Decimal(row["revenue"]) for row in monthly), Decimal("0"))
        cogs = sum((Decimal(row["cogs"]) for row in monthly), Decimal("0"))
        gross_profit = revenue - cogs

        self.assertEqual(Decimal("310.00"), revenue)
        self.assertEqual(Decimal("193.00"), cogs)
        self.assertEqual(Decimal("117.00"), gross_profit)
        self.assertEqual(Decimal("37.74"), (gross_profit / revenue * 100).quantize(Decimal("0.01")))
        self.assertEqual(
            Decimal("-10.00"), Decimal(monthly[-1]["revenue"]) - Decimal(monthly[0]["revenue"])
        )

        with (scenario / "working_capital.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            positions = {row["position"]: row for row in csv.DictReader(handle)}

        def net_working_capital(position: str) -> Decimal:
            row = positions[position]
            return (
                Decimal(row["accounts_receivable"])
                + Decimal(row["inventory"])
                - Decimal(row["accounts_payable"])
            )

        opening = net_working_capital("opening")
        closing = net_working_capital("closing")
        self.assertEqual(Decimal("60.00"), opening)
        self.assertEqual(Decimal("75.00"), closing)
        self.assertEqual(Decimal("15.00"), closing - opening)

    def test_existing_workflow_fixture_enforces_supported_and_unsupported_modules(self) -> None:
        workflow = SCENARIOS / "existing_workflow" / "workflow"
        config = json.loads((workflow / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(["revenue_summary"], config["supported_modules"])
        self.assertEqual(
            "source confirmation and debt mapping are not implemented in this Workflow",
            config["unsupported_modules"]["net_debt"],
        )
        self.assertEqual("coordinator", config["write_rules"]["single_writer"])
        self.assertEqual(
            {"results/current_revenue_summary.json", "results/request_limitations.md"},
            set(config["write_rules"]["allowed_outputs"]),
        )

    def test_existing_workflow_native_validator_rejects_missing_then_accepts_exact_outputs(self) -> None:
        workspace = REPO_ROOT / f".test-fdd-{uuid.uuid4().hex}"
        workflow = workspace / "workflow"
        try:
            shutil.copytree(SCENARIOS / "existing_workflow" / "workflow", workflow)
            missing = subprocess.run(
                [sys.executable, "scripts/validate_outputs.py"],
                cwd=workflow,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, missing.returncode)
            missing_report = json.loads(missing.stdout)
            self.assertIn(
                "missing results/current_revenue_summary.json", missing_report["errors"]
            )
            self.assertIn("missing results/request_limitations.md", missing_report["errors"])

            results = workflow / "results"
            results.mkdir()
            summary = {
                "module": "revenue_summary",
                "current_period": "Q1 2026",
                "comparative_period": "Q1 2025",
                "current_revenue": "330.00",
                "comparative_revenue": "270.00",
                "change_amount": "60.00",
                "change_pct": "22.22",
                "currency": "LCU",
            }
            (results / "current_revenue_summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
            (results / "request_limitations.md").write_text(
                "# Request limitations\n\n"
                "The requested `net_debt` module is not supported because source "
                "confirmation and debt mapping are not implemented in this Workflow.\n",
                encoding="utf-8",
            )

            passed = subprocess.run(
                [sys.executable, "scripts/validate_outputs.py"],
                cwd=workflow,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
            self.assertEqual({"valid": True, "errors": []}, json.loads(passed.stdout))
        finally:
            if workspace.exists():
                shutil.rmtree(workspace)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Validate the synthetic Workflow's authorized outputs."""

from __future__ import annotations

import csv
from decimal import Decimal
import json
from pathlib import Path
import sys


WORKFLOW_ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _expected_summary() -> dict:
    rules = _load_json(WORKFLOW_ROOT / "rules" / "revenue_rules.json")
    totals: dict[str, Decimal] = {}
    with (WORKFLOW_ROOT / "data" / "revenue.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            totals[row["period"]] = totals.get(row["period"], Decimal("0")) + Decimal(
                row["revenue"]
            )

    current_period = rules["current_period"]
    comparative_period = rules["comparative_period"]
    current = totals[current_period]
    comparative = totals[comparative_period]
    change = current - comparative
    change_pct = change / comparative * Decimal("100")
    return {
        "module": "revenue_summary",
        "current_period": current_period,
        "comparative_period": comparative_period,
        "current_revenue": f"{current:.2f}",
        "comparative_revenue": f"{comparative:.2f}",
        "change_amount": f"{change:.2f}",
        "change_pct": f"{change_pct:.2f}",
        "currency": rules["currency"],
    }


def validate() -> list[str]:
    errors: list[str] = []
    summary_path = WORKFLOW_ROOT / "results" / "current_revenue_summary.json"
    limitation_path = WORKFLOW_ROOT / "results" / "request_limitations.md"
    if not summary_path.is_file():
        errors.append("missing results/current_revenue_summary.json")
    else:
        observed = _load_json(summary_path)
        expected = _expected_summary()
        if observed != expected:
            errors.append(
                "revenue summary mismatch: "
                + json.dumps({"expected": expected, "observed": observed}, sort_keys=True)
            )

    if not limitation_path.is_file():
        errors.append("missing results/request_limitations.md")
    else:
        limitation = limitation_path.read_text(encoding="utf-8")
        required = (
            "net_debt",
            "source confirmation and debt mapping are not implemented in this Workflow",
        )
        for text in required:
            if text not in limitation:
                errors.append(f"limitation report is missing: {text}")

    forbidden = ["AGENT_WORKSPACE", "HUMAN_PORTAL", "RESULTS"]
    for name in forbidden:
        if (WORKFLOW_ROOT.parent / name).exists():
            errors.append(f"forbidden generic directory exists: {name}")
    return errors


def main() -> int:
    errors = validate()
    report = {"valid": not errors, "errors": errors}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

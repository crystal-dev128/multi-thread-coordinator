#!/usr/bin/env python3
"""Import a tiny synthetic order file using an external delimiter config."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path


def build_summary(source: Path, config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    delimiter = config["delimiter"]
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        required = {"order_id", "region", "amount"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"missing required columns; observed={reader.fieldnames}")
        rows = list(reader)

    regional: dict[str, Decimal] = {}
    total = Decimal("0")
    for row in rows:
        amount = Decimal(row["amount"])
        total += amount
        regional[row["region"]] = regional.get(row["region"], Decimal("0")) + amount

    return {
        "order_count": len(rows),
        "total_amount": f"{total:.2f}",
        "regional_totals": {
            region: f"{amount:.2f}" for region, amount in sorted(regional.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = build_summary(Path(args.source), Path(args.config))
    Path(args.output).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

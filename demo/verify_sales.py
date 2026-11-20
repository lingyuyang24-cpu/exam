"""Independent deterministic oracle. Never sent to the model as an expected answer."""
import csv
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def totals(path, completed_only=False):
    result = defaultdict(Decimal)
    with Path(path).open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if completed_only and row["status"] != "已完成":
                continue
            result[row["region"]] += Decimal(row["quantity"]) * Decimal(row["unit_price"])
    return {region: str(value) for region, value in sorted(result.items())}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path)
    parser.add_argument("--completed-only", action="store_true")
    args = parser.parse_args()
    expected = totals(Path(__file__).parent / "inputs/sales.csv", args.completed_only)
    if args.actual:
        with args.actual.open(encoding="utf-8-sig") as file:
            actual = {r["region"]: r["total_sales"] for r in csv.DictReader(file)}
        assert set(actual) == set(expected), (actual, expected)
        assert all(Decimal(actual[k]) == Decimal(v) for k, v in expected.items()), (actual, expected)
    print(json.dumps({"scope": "completed" if args.completed_only else "all", "regions": expected,
                      "total": str(sum(map(Decimal, expected.values()))),
                      "comparison": "passed" if args.actual else "expected values only"}, ensure_ascii=False, indent=2))

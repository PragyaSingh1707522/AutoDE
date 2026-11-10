"""Small deterministic baseline benchmark for the implemented CSV profiler."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent


def evaluate():
    data = json.loads((ROOT / "scenarios.json").read_text(encoding="utf-8"))
    correct = total = 0
    for scenario in data["scenarios"]:
        file = ROOT / scenario["input"]
        if not file.exists():
            continue
        with file.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
        passed = len(rows) == scenario.get("expected_rows", len(rows)) and set(scenario.get("expected_columns", reader.fieldnames or [])) == set(reader.fieldnames or [])
        total += 1
        correct += int(passed)
    rate = correct / total if total else 0
    print(json.dumps({"evaluated_scenarios": total, "pipeline_correctness_rate": rate, "text_to_sql_accuracy": None, "note": "Text-to-SQL benchmark is unavailable until SQL analyst is implemented."}, indent=2))


if __name__ == "__main__":
    evaluate()

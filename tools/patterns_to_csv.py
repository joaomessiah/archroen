"""
Converts data/patterns/chronology_patterns.json to a human-readable CSV.

Usage:
    python tools/patterns_to_csv.py [input.json] [output.csv]

Defaults:
    input:  data/patterns/chronology_patterns.json
    output: data/patterns/chronology_patterns_review.csv
"""

import csv
import json
import re
import sys
from pathlib import Path

DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "data" / "patterns" / "chronology_patterns.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "patterns" / "chronology_patterns_review.csv"

COLUMNS = [
    "CHRONOLOGY_ID",
    "Phase Code",
    "Preferred Label",
    "Description",
    "Match Terms",
    "Date Start",
    "Date End",
]


def extract_terms(regex: str) -> list[str]:
    """Pull individual match terms out of a \\b(?:term1|term2|...)\\b pattern."""
    m = re.match(r"^\\b\(\?:(.+)\)\\b$", regex)
    if not m:
        return [regex]
    raw_terms = m.group(1).split("|")
    return [re.sub(r"\\(.)", r"\1", t) for t in raw_terms]


def format_date(value: int) -> str:
    if value < 0:
        return f"{abs(value)} BCE"
    return f"AD {value}"


def main():
    """CLI: dump a chronology patterns JSON file to a human-readable review CSV."""
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT

    with open(input_path, encoding="utf-8") as f:
        patterns = json.load(f)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for p in patterns:
            terms = extract_terms(p.get("regex", ""))
            writer.writerow({
                "CHRONOLOGY_ID": p.get("chronology_id", ""),
                "Phase Code": p.get("phase_code", ""),
                "Preferred Label": p.get("preferred_label", ""),
                "Description": p.get("description", ""),
                "Match Terms": "; ".join(terms),
                "Date Start": format_date(p["date_start"]) if p.get("date_start") is not None else "",
                "Date End": format_date(p["date_end"]) if p.get("date_end") is not None else "",
            })

    print(f"Exported {len(patterns)} entries → {output_path}")


if __name__ == "__main__":
    main()

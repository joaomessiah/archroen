"""
Generates data/patterns/chronology_patterns.json from data/vocabularies/chronology_vocab.csv.

Usage:
    python tools/generate_chronology_patterns.py [path/to/chronology_vocab.csv]

Default CSV path: ../data/vocabularies/chronology_vocab.csv (relative to this script).
"""

import csv
import json
import re
import sys
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "vocabularies" / "chronology_vocab.csv"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "patterns" / "chronology_patterns.json"

TERM_COLUMNS = [
    "Code",
    "Phase Name (EN)",
    "Phase (NL)",
    "Historical keyword (EN)",
    "Historical keyword (NL)",
]

DATE_STRING_COLUMNS = [
    "Start (BCE/CE)",
    "End (BCE/CE)",
    "Start (BC/AD)",
    "End (BC/AD)",
]


def make_regex(terms: list[str]) -> str:
    escaped = [re.escape(t) for t in terms]
    return r"\b(?:" + "|".join(escaped) + r")\b"


def generate_patterns(csv_path: Path) -> list[dict]:
    """Build the period/chronology detection patterns from the chronology vocabulary CSV (one
    pattern per period term, carrying its canonical id and ARCHIS date range)."""
    patterns = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            chronology_id = row["CHRONOLOGY_ID"].strip()
            phase_code = row["Code"].strip()
            date_start = int(row["Start (numeric)"])
            date_end = int(row["End (numeric)"])
            preferred_label = row["Phase Name (EN)"].strip()

            terms = []
            seen = set()
            for col in TERM_COLUMNS + DATE_STRING_COLUMNS:
                val = row.get(col, "").strip()
                if val and val.lower() not in seen:
                    terms.append(val)
                    seen.add(val.lower())

            if not terms:
                continue

            patterns.append({
                "pattern_id": f"chronology_{chronology_id}",
                "chronology_id": chronology_id,
                "phase_code": phase_code,
                "description": f"{row['Phase Name (EN)'].strip()} / {row['Phase (NL)'].strip()}",
                "regex": make_regex(terms),
                "canonical_hint": chronology_id,
                "preferred_label": preferred_label,
                "date_start": date_start,
                "date_end": date_end,
            })

    return patterns


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    patterns = generate_patterns(csv_path)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(patterns)} patterns → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

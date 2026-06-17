"""
Generates data/patterns/century_patterns.json from data/vocabularies/century_vocab.csv.

Single-century entries are read from the CSV. Adjacent-pair range entries
(e.g. "2nd and 3rd centuries AD") are generated automatically for all
centuries defined in the CSV, because the first ordinal in such phrases
is never followed by "centur" and would otherwise go undetected.

Usage:
    python tools/generate_century_patterns.py [path/to/century_vocab.csv]

Default CSV path: ../data/vocabularies/century_vocab.csv (relative to this script).

CSV columns:
    pattern_id, description, regex, canonical_hint, preferred_label,
    date_start, date_end
"""

import csv
import json
import sys
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "vocabularies" / "century_vocab.csv"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "patterns" / "century_patterns.json"

EN_ORD = {
    1: ("1st", "first"), 2: ("2nd", "second"), 3: ("3rd", "third"),
    4: ("4th", "fourth"), 5: ("5th", "fifth"), 6: ("6th", "sixth"),
    7: ("7th", "seventh"), 8: ("8th", "eighth"), 9: ("9th", "ninth"),
    10: ("10th", "tenth"), 11: ("11th", "eleventh"), 12: ("12th", "twelfth"),
    13: ("13th", "thirteenth"), 14: ("14th", "fourteenth"), 15: ("15th", "fifteenth"),
    16: ("16th", "sixteenth"), 17: ("17th", "seventeenth"), 18: ("18th", "eighteenth"),
    19: ("19th", "nineteenth"), 20: ("20th", "twentieth"), 21: ("21st", "twenty-first"),
}

NL_ORD = {
    1:  ("1e", "1ste", "eerste"),   2:  ("2e", "tweede"),    3:  ("3e", "derde"),
    4:  ("4e", "vierde"),           5:  ("5e", "vijfde"),     6:  ("6e", "zesde"),
    7:  ("7e", "zevende"),          8:  ("8e", "achtste"),    9:  ("9e", "negende"),
    10: ("10e", "tiende"),          11: ("11e", "elfde"),     12: ("12e", "twaalfde"),
    13: ("13e", "dertiende"),       14: ("14e", "veertiende"),15: ("15e", "vijftiende"),
    16: ("16e", "zestiende"),       17: ("17e", "zeventiende"),18:("18e", "achttiende"),
    19: ("19e", "negentiende"),     20: ("20e", "twintigste"),21: ("21e", "eenentwintigste"),
}


def _nl_pat(n: int) -> str:
    return "|".join(NL_ORD[n])


def _bc_range_regex(n: int, m: int) -> str:
    en_n, en_nw = EN_ORD[n]
    en_m, en_mw = EN_ORD[m]
    return (
        rf"\b(?:{en_n}|{en_nw})\s+and\s+(?:{en_m}|{en_mw})\s+centur(?:y|ies)\s+(?:BC|BCE)\b"
        rf"|\b(?:{_nl_pat(n)})\s+en\s+(?:{_nl_pat(m)})\s+eeuw\s+(?:v\.?\s*Chr\.?|voor\s+Chr\.?)\b"
    )


def _ad_range_regex(n: int, m: int) -> str:
    en_n, en_nw = EN_ORD[n]
    en_m, en_mw = EN_ORD[m]
    return (
        rf"\b(?:{en_n}|{en_nw})\s+and\s+(?:{en_m}|{en_mw})\s+centur(?:y|ies)(?:\s+(?:AD|CE))?\b"
        rf"|\b(?:{_nl_pat(n)})\s+en\s+(?:{_nl_pat(m)})\s+eeuw(?:\s+(?:n\.?\s*Chr\.?))?\b"
    )


def _generate_ranges(single_patterns: list[dict]) -> list[dict]:
    """Generate adjacent-pair century-range patterns (e.g. "2nd and 3rd centuries AD") from the
    single-century patterns, handled separately for BC and AD. These are generated rather than
    listed because the first ordinal in such a phrase is not followed by "century" and would
    otherwise go undetected."""
    bc = sorted(
        [p for p in single_patterns if p["pattern_id"].endswith("_bc")],
        key=lambda p: p["date_start"],
    )
    ad = sorted(
        [p for p in single_patterns if p["pattern_id"].endswith("_ad")],
        key=lambda p: p["date_start"],
    )

    ranges = []

    for i in range(len(bc) - 1):
        a, b = bc[i], bc[i + 1]
        na = int(a["pattern_id"].split("_")[1])
        nb = int(b["pattern_id"].split("_")[1])
        en_a = EN_ORD[na][0]
        en_b = EN_ORD[nb][0]
        ranges.append({
            "pattern_id": f"century_range_{na}_{nb}_bc",
            "description": f"{en_a}–{en_b} century BC range (EN + NL)",
            "regex": _bc_range_regex(na, nb),
            "canonical_hint": f"CENTURY_RANGE_{na}_{nb}_BC",
            "preferred_label": f"{en_a}–{en_b} century BC",
            "date_start": a["date_start"],
            "date_end": b["date_end"],
        })

    for i in range(len(ad) - 1):
        a, b = ad[i], ad[i + 1]
        na = int(a["pattern_id"].split("_")[1])
        nb = int(b["pattern_id"].split("_")[1])
        en_a = EN_ORD[na][0]
        en_b = EN_ORD[nb][0]
        ranges.append({
            "pattern_id": f"century_range_{na}_{nb}_ad",
            "description": f"{en_a}–{en_b} century AD range (EN + NL)",
            "regex": _ad_range_regex(na, nb),
            "canonical_hint": f"CENTURY_RANGE_{na}_{nb}_AD",
            "preferred_label": f"{en_a}–{en_b} century AD",
            "date_start": a["date_start"],
            "date_end": b["date_end"],
        })

    return ranges


def generate_patterns(csv_path: Path) -> list[dict]:
    """Build the full century pattern list from the vocabulary CSV: the single-century entries
    plus the auto-generated adjacent-pair ranges (see `_generate_ranges`)."""
    singles = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            singles.append({
                "pattern_id": row["pattern_id"].strip(),
                "description": row["description"].strip(),
                "regex": row["regex"].strip(),
                "canonical_hint": row["canonical_hint"].strip(),
                "preferred_label": row["preferred_label"].strip(),
                "date_start": int(row["date_start"]),
                "date_end": int(row["date_end"]),
            })
    return singles + _generate_ranges(singles)


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

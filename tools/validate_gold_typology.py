#!/usr/bin/env python3
"""Validate a gold-standard file's Typology column against the typology master.

For every Typology value in a gold CSV, this resolves it against the master
(typology_code + all_forms + abbreviations) and sorts each into one of three
states. The two "needs action" states are surfaced as their own columns so they
can be triaged and acted on directly:

  - resolved_code : matched cleanly -> the canonical master code to keep
  - master_gap    : looks like a real typology but is absent from the master
                    -> candidate to ADD to the master (do NOT blank in gold)
  - not_typology  : looks descriptive, not a type -> candidate to BLANK in gold

The split between the last two is a heuristic guess to speed up review; it is
not authoritative. A value is guessed to be a real typology when it carries a
known type-series name (Alzey, Holwerda, Niederbieber/NB, Dragendorff/Drag,
Trier, Mayen, ...) and/or a number. Always eyeball the two action columns.

Comparison qualifiers (cf., vgl., type, -achtig, ...) are stripped before
lookup so 'Alzey 28 cf.' resolves to 'Alzey 28'. The stripped qualifier is
reported in its own column.

Usage:
    python3 validate_gold_typology.py <gold.csv> [more_gold.csv ...]
    python3 validate_gold_typology.py --master path/to/master.csv <gold.csv>
    python3 validate_gold_typology.py --out-dir path/to/dir <gold.csv>

Writes <gold-stem>.csv (same name as the input) into
outputs/gold_standard_validations/ and prints a summary.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MASTER = HERE.parent / "data" / "vocabularies" / "pottery_vocab_master.csv"
DEFAULT_OUT_DIR = HERE.parent / "outputs" / "gold_standard_validations"

# Multilingual comparison / approximation qualifiers stripped before lookup.
# Latin cf. crosses languages; the rest are NL/DE/FR native forms.
QUALIFIER_RE = re.compile(
    r"\b(?:cf\.?|vgl\.?|sim\.?|var\.?|type|typ|proche\s+de|aehnlich|ähnlich)\b"
    r"|-?achtig\b",
    re.IGNORECASE,
)

# Type-series names used only to GUESS whether an unmatched value is a real
# typology (master gap) versus a description. Extend as your corpus grows.
TYPE_SERIES_RE = re.compile(
    r"\b(?:alzey|holwerda|niederbieber|nb|dragendorff|drag|trier|mayen|"
    r"stuart|brunsting|gose|chenet|hofheim|hbw|bw|fg)\b",
    re.IGNORECASE,
)


def normalize(value: str) -> tuple[str, str]:
    """Return (cleaned_value, stripped_qualifier)."""
    quals = QUALIFIER_RE.findall(value)
    cleaned = QUALIFIER_RE.sub(" ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;")
    return cleaned, " ".join(q.strip() for q in quals if q.strip())


def load_master(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (code_index, form_index) mapping lowercase key -> canonical code."""
    code_index: dict[str, str] = {}
    form_index: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = (row.get("typology_code") or "").strip()
            if not code:
                continue
            code_index[code.lower()] = code
            for col in ("all_forms", "abbreviations"):
                for variant in (row.get(col) or "").split("|"):
                    variant = variant.strip()
                    if variant:
                        form_index.setdefault(variant.lower(), code)
    return code_index, form_index


def classify(raw: str, code_index, form_index) -> dict:
    """Resolve one gold Typology value against the master index and sort it into one of three
    states: `matched` (resolved to a canonical code), `master_gap` (looks like a real type but is
    absent from the master → candidate to ADD), or `not_typology` (descriptive, not a type →
    candidate to BLANK in the gold). Returns the per-value annotation row."""
    cleaned, qualifier = normalize(raw)
    key = cleaned.lower()
    resolved = code_index.get(key) or form_index.get(key) or ""
    looks_like_type = bool(TYPE_SERIES_RE.search(cleaned)) or bool(
        re.search(r"\d", cleaned)
    )
    return {
        "typology_raw": raw,
        "typology_normalized": cleaned,
        "stripped_qualifier": qualifier,
        "resolved_code": resolved,
        "master_gap": "" if resolved else (cleaned if looks_like_type else ""),
        "not_typology": "" if resolved else ("" if looks_like_type else cleaned),
        "status": "matched"
        if resolved
        else ("master_gap" if looks_like_type else "not_typology"),
    }


def validate_file(gold_path: Path, code_index, form_index, out_dir: Path) -> Path:
    """Classify every distinct Typology value in one gold CSV and write an annotated CSV with the
    resolved_code / master_gap / not_typology columns for triage. Returns the output path."""
    rows_out = []
    seen = set()
    with gold_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = (row.get("Typology") or "").strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            rows_out.append(classify(raw, code_index, form_index))

    rows_out.sort(key=lambda r: (r["status"], r["typology_normalized"].lower()))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{gold_path.stem}.csv"
    fields = [
        "typology_raw",
        "typology_normalized",
        "stripped_qualifier",
        "resolved_code",
        "master_gap",
        "not_typology",
        "status",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    counts = {"matched": 0, "master_gap": 0, "not_typology": 0}
    for r in rows_out:
        counts[r["status"]] += 1
    print(f"\n{gold_path.name}: {len(rows_out)} unique typology values")
    print(f"  matched      : {counts['matched']}")
    print(f"  master_gap?  : {counts['master_gap']}  (review -> add to master)")
    print(f"  not_typology?: {counts['not_typology']}  (review -> blank in gold)")
    for r in rows_out:
        if r["status"] != "matched":
            print(f"    [{r['status']}] {r['typology_raw']!r}")
    print(f"  -> {out_path}")
    return out_path


def main(argv: list[str]) -> int:
    """CLI: validate one or more gold-standard files' Typology columns against the typology master,
    writing an annotated CSV per input for triage. Returns a process exit code."""
    args = list(argv)
    master = DEFAULT_MASTER
    out_dir = DEFAULT_OUT_DIR
    if "--master" in args:
        i = args.index("--master")
        master = Path(args[i + 1])
        del args[i : i + 2]
    if "--out-dir" in args:
        i = args.index("--out-dir")
        out_dir = Path(args[i + 1])
        del args[i : i + 2]
    if not args:
        print(__doc__)
        return 1
    code_index, form_index = load_master(master)
    print(f"master: {master.name} ({len(code_index)} codes, {len(form_index)} forms)")
    for gold in args:
        validate_file(Path(gold), code_index, form_index, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

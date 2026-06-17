"""
Convert a pottery vocabulary CSV into data/patterns/pottery_patterns.json (the regex
detection patterns consumed by Layer 3).

Supports two input formats (auto-detected from headers):
  legacy     — pottery_nl_en.csv (typology_nl, typology_en, pot_name_nl, pot_name_en, start_date, end_date)
  normalized — pottery_vocab_normalized.csv (typology_code, pot_name_en, pot_name_nl, date_start, date_end)

Usage:
    python3 tools/csv_to_patterns.py <input.csv> <output.json>
    # current build: tools/csv_to_patterns.py data/vocabularies/pottery_vocab_normalized.csv data/patterns/pottery_patterns.json
"""

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# Single-word typology codes that are too common to use as patterns.
_STOPWORD_CODES = {
    "open", "gesloten", "closed", "type", "vorm", "form", "onbepaald",
    "unknown", "overig", "other", "diversen", "various", "algemeen",
    "general", "fragment", "fragmenten", "rand", "bodem", "wand",
}


def _is_safe_code(code: str) -> bool:
    """Return False for single-word codes that are too generic to match reliably."""
    words = code.split()
    if len(words) == 1 and words[0].lower() in _STOPWORD_CODES:
        return False
    # Single-word code with no digit is risky unless it's a known technical term
    if len(words) == 1 and not re.search(r'\d', code):
        # Allow known archaeological proper-noun codes (e.g. "Gauloise", "Dressel")
        if not re.match(r'^[A-Z]', code):
            return False
    return True


def _normalise_code(code: str) -> str:
    """Turn 'Alzei 27' → 'ALZEI_27' for use as canonical_hint."""
    return re.sub(r'[^A-Z0-9]+', '_', code.upper()).strip('_')


def _base_code(typology: str) -> str:
    """Strip subtype suffix: 'Alzei 27:dekselgeul' → 'Alzei 27'."""
    return typology.split(':')[0].strip()


def _escape_for_regex(text: str) -> str:
    """Escape a literal string for use inside a regex alternation."""
    return re.escape(text)


def _code_regex(code: str) -> str:
    # Uses [\s\-]*(type\s+)? between tokens so both "Niederbieber 97" and
    # "Niederbieber type 97" match, and OCR line-breaks don't break matching.
    # Slashes within tokens (e.g. "18/31", "211/Brunsting") get optional
    # whitespace on each side so "18 / 31" also matches.
    parts = code.split()
    escaped = [re.escape(p).replace("/", r"\s*/\s*") for p in parts]
    return r'[\s\-]*(?:type\s+)?'.join(escaped)


# Only include pot names that start with a proper noun or known named ware.
# Single generic words like "aardewerk", "kom", "beker" must NOT become patterns.
_NAMED_POT_RE = re.compile(
    r'^(terra\s+(?:sigillata|nigra|rubra)'   # "terra sigillata/nigra/rubra ..."
    r'|samian\b'                              # "Samian ware"
    r'|arretin[e]?\b'                         # "arretine ware" (EN)
    r'|african\s+red\s+slip\b'               # "African Red Slip ware"
    r'|argonnian\s+terra\s+sigillata\b'      # "Argonnian terra sigillata"
    r'|(?:arretijns?e?|gaulois|belgisch)\b'    # named production traditions (NL)
    r'|majolica|faience|steengoed'            # late-period named wares
    r')',
    re.IGNORECASE,
)


# "terra sigillata" + bare vessel word with no qualifier is too generic to use as
# a regex alias — it matches any sentence mentioning terra sigillata and floods
# the output with duplicates. Require a geographic/production qualifier (e.g.
# "Argonnian", "South Gaulish") or a specific ware variant (nigra, rubra).
_GENERIC_TS_RE = re.compile(
    r'^terra\s+sigillata'
    # optional vessel-form word in EN or NL — with or without it, still too generic
    r'(?:\s+(?:form|bowl|cup|plate|jar|jug|dish|beaker|pot|krater|flask|flagon|'
    r'kom|beker|bord|schaal|kruik|kan|fles|vorm|type))?\s*$',
    re.IGNORECASE,
)


def _is_named_pot(name: str) -> bool:
    """Return True only for named wares specific enough to use as a regex alias."""
    name = name.strip()
    if _GENERIC_TS_RE.match(name):
        return False
    return bool(_NAMED_POT_RE.match(name))


def _name_regex(name: str) -> str:
    """Build a regex fragment for a multi-word pot name."""
    parts = re.split(r'[\s,]+', name.strip())
    parts = [p for p in parts if p]
    return r'[\s,]+'.join(re.escape(p) for p in parts)


def _detect_csv_format(csv_path: Path) -> str:
    """Return 'normalized' if CSV uses typology_code column, else 'legacy'."""
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        headers = csv.DictReader(f).fieldnames or []
    return 'normalized' if 'typology_code' in headers else 'legacy'


def build_patterns_from_normalized(csv_path: Path) -> list:
    """Build patterns from pottery_vocab_normalized.csv.

    Each row has an all_forms column (pipe-separated) listing every variant that
    should be detectable: individual codes, combined forms, and all orderings.
    The regex matches all of them so "Stuart 211", "Brunsting 9", and
    "Stuart 211/Brunsting 9" all resolve to the same canonical entry.
    """
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    patterns = []
    for idx, row in enumerate(rows, start=1):
        code        = row['typology_code'].strip()
        pot_name_en = row['pot_name_en'].strip()
        pot_name_nl = row['pot_name_nl'].strip()
        date_start  = int(row['date_start'])
        date_end    = int(row['date_end'])

        if not _is_safe_code(code):
            continue

        canonical = _normalise_code(code)

        # Build regex alternations:
        #   1. Every typology code form (from all_forms)
        #   2. Every abbreviation (from abbreviations column, e.g. "NB 89", "Drag. 37")
        #   3. Named pot aliases from EN/NL/DE/FR names

        all_forms = [f.strip() for f in row.get('all_forms', code).split('|') if f.strip()]
        if not all_forms:
            all_forms = [code]

        abbreviations = [a.strip() for a in row.get('abbreviations', '').split('|') if a.strip()]

        alts: set[str] = set()
        for form in all_forms:
            alts.add(_code_regex(form))
        for abbr in abbreviations:
            alts.add(_code_regex(abbr))

        pot_name_de = row.get('pot_name_de', '').strip()
        pot_name_fr = row.get('pot_name_fr', '').strip()
        for name in (pot_name_en, pot_name_nl, pot_name_de, pot_name_fr):
            if _is_named_pot(name):
                alts.add(_name_regex(name))

        regex = r'\b(?:' + '|'.join(sorted(alts, key=len, reverse=True)) + r')\b'

        patterns.append({
            "pattern_id":      f"csv_pottery_{idx:04d}",
            "type_id":         f"CSV_{idx:04d}",
            "code":            canonical,
            "category":        "pottery_form",
            "description":     pot_name_en,
            "regex":           regex,
            "canonical_hint":  canonical,
            "preferred_label": pot_name_en,
            "ware_type":       row.get('ware_type', ''),
            "vessel_form":     row.get('vessel_form', ''),
            "date_start":      date_start,
            "date_end":        date_end,
        })

    return patterns


def build_patterns(csv_path: Path) -> list:
    """Build the regex detection pattern specs from a pottery vocabulary CSV: group rows by
    base typology + date range, collect every NL/EN name and typology variant per group, and
    emit one pattern (with a canonical hint and the group's date range) per group."""
    rows = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Group rows by (base_typology_nl, start_date, end_date).
    # Collect all NL/EN names and typology variants per group.
    groups: dict[tuple, dict] = defaultdict(lambda: {
        'base_nl': '', 'base_en': '',
        'names_nl': set(), 'names_en': set(),
        'typos_nl': set(), 'typos_en': set(),
        'start': 0, 'end': 0,
    })

    for row in rows:
        base_nl = _base_code(row['typology_nl'])
        base_en = _base_code(row['typology_en'])
        key = (base_nl, row['start_date'], row['end_date'])
        g = groups[key]
        g['base_nl'] = base_nl
        g['base_en'] = base_en
        g['start'] = int(row['start_date'])
        g['end'] = int(row['end_date'])
        if row['pot_name_nl']:
            g['names_nl'].add(row['pot_name_nl'].strip())
        if row['pot_name_en']:
            g['names_en'].add(row['pot_name_en'].strip())
        g['typos_nl'].add(row['typology_nl'].strip())
        g['typos_en'].add(row['typology_en'].strip())

    patterns = []
    seen_codes = set()

    for idx, ((base_nl, start_str, end_str), g) in enumerate(groups.items(), start=1):
        base_en = g['base_en']

        # Deduplicate: if NL and EN base codes are the same string, only add once
        primary_code = base_nl
        if primary_code in seen_codes:
            continue
        seen_codes.add(primary_code)

        # Skip typology codes too generic to match reliably
        if not _is_safe_code(primary_code):
            continue

        canonical = _normalise_code(primary_code)

        # Build regex alternation parts
        alts = set()

        # 1. Base typology codes (NL and EN)
        alts.add(_code_regex(base_nl))
        if base_en and base_en != base_nl:
            alts.add(_code_regex(base_en))

        # 2. Specific pot names (NL and EN) — only if recognisably named
        for name in g['names_nl']:
            if _is_named_pot(name):
                alts.add(_name_regex(name))
        for name in g['names_en']:
            if _is_named_pot(name):
                alts.add(_name_regex(name))

        # Sort longest first so more specific patterns win
        sorted_alts = sorted(alts, key=len, reverse=True)
        regex = r'\b(?:' + '|'.join(sorted_alts) + r')\b'

        # Representative human-readable label: prefer EN base code
        label = base_en if base_en else base_nl

        patterns.append({
            "pattern_id": f"csv_pottery_{idx:04d}",
            "type_id": f"CSV_{idx:04d}",
            "code": canonical,
            "category": "pottery_form",
            "description": label,
            "regex": regex,
            "canonical_hint": canonical,
            "preferred_label": label,
            "date_start": g['start'],
            "date_end": g['end'],
        })

    return patterns


def main():
    """CLI: convert a pottery vocabulary CSV into data/patterns/pottery_patterns.json (input
    format auto-detected from its headers)."""
    if len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} <input.csv> <output.json>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    fmt = _detect_csv_format(csv_path)
    patterns = build_patterns_from_normalized(csv_path) if fmt == 'normalized' else build_patterns(csv_path)
    print(f"Detected format: {fmt} — {len(patterns)} patterns")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(patterns)} patterns → {out_path}")


if __name__ == '__main__':
    main()

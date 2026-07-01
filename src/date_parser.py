"""
Regex-based date expression extractor for Layer 6 Part 2.

Extracts chronological signals from a context string and returns structured
date ranges. Patterns are processed in priority order (compound before single,
explicit before century before broad) with span overlap tracking to avoid
double-counting the same stretch of text.
"""

import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_ORDINAL_EN: Dict[str, int] = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9, "10th": 10,
}
_ORDINAL_WORD_EN: Dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21,
}
# Dutch numeric ordinals up to the 21st century, in all common suffix spellings
# ("1e", "3de", "13de", "20ste"). Medieval reports use 11e–15e/-de centuries, so the
# old 1e–10e range was too small (e.g. "13de eeuw" went unparsed).
_ORDINAL_NL: Dict[str, int] = {
    f"{_n}{_suf}": _n for _n in range(1, 22) for _suf in ("e", "de", "ste")
}
# Dutch ordinal WORDS — common in older reports ("eerste eeuw", "de eerste eeuwen
# onzer jaartelling"). The numeric _ORDINAL_NL above does not cover these.
_ORDINAL_WORD_NL: Dict[str, int] = {
    "eerste": 1, "tweede": 2, "derde": 3, "vierde": 4, "vijfde": 5,
    "zesde": 6, "zevende": 7, "achtste": 8, "negende": 9, "tiende": 10,
}
_QUALIFIER_EN: Dict[str, str] = {
    "early": "early", "mid": "mid", "middle": "mid", "late": "late",
}
_QUALIFIER_NL: Dict[str, str] = {
    "vroeg": "early", "midden": "mid", "laat": "late",
}

# Keys are lowercase; first match wins. Derived from the single source of truth (src/periods.py)
# so the qualified-Roman dates stay in sync with the prompt/gazetteer/chron_vocab. Only the Roman
# SUB-periods (early/middle/late) are included — bare "Roman" is deliberately excluded here so it
# doesn't over-match every "Roman" mention in context (the detection regex below requires a
# qualifier; this list only supplies the date for the matched text).
from src.periods import PERIODS as _PERIODS  # noqa: E402
_QUAL = ("vroeg", "laat", "midden", "early", "late", "mid", "middle")
_BROAD_PERIODS: List[Tuple[str, int, int]] = [
    (t, p.start, p.end) for p in _PERIODS
    if p.code in ("ROMV", "ROMM", "ROML")          # qualified-Roman sub-periods only (no bare Roman)
    for t in p.terms if any(q in t for q in _QUAL)  # only "<qualifier> roman" forms the regex detects
]

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# --- Explicit year expressions (require an era marker) ---

# Prefix form: "AD 70", "AD 70–120", "BC 50"
_YEAR_PREFIX_RE = re.compile(
    r"\b(AD|BC)\s*(\d{1,4})(?:\s*[-–—]\s*(\d{1,4}))?\b",
    re.IGNORECASE,
)

# Suffix form: "70 CE", "70 AD", "70–120 AD", "50 BC", "19-16 BC", "50 BCE", "70 n.Chr.", "50 v.Chr."
# Order matters: BCE before BC so the longer match wins.
# Uses (?!\w) instead of \b at the end because n.Chr./v.Chr. end with '.'
_YEAR_SUFFIX_RE = re.compile(
    r"\b(\d{1,4})(?:\s*[-–—]\s*(\d{1,4}))?\s*(CE|BCE|BC|AD|n\.Chr\.|v\.Chr\.)(?!\w)",
    re.IGNORECASE,
)

# Shared ordinal alternation strings used across patterns below
_EN_ORD = r"1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th"
# Longest-first so "13de" wins over "1" / "3de" at the same position.
_NL_ORD = "|".join(sorted(_ORDINAL_NL.keys(), key=len, reverse=True))

# --- Compound century ranges (process BEFORE single century to claim the span) ---

# English: "2nd and 3rd centuries AD", "1st to 3rd century CE", "2nd–3rd century BC"
_CENTURY_EN_COMPOUND_RE = re.compile(
    r"\b(" + _EN_ORD + r")"
    r"(?:\s*[-–—]\s*|\s+and\s+|\s+to\s+|\s+through\s+)"
    r"(" + _EN_ORD + r")\s+centur(?:y|ies)(?:\s*(AD|CE|BC|BCE))?\b",
    re.IGNORECASE,
)

# Dutch: "2e en 3e eeuw", "2e–3e eeuw n.Chr.", "2e–3e eeuw v.Chr."
# Uses (?!\w) instead of \b at the end because n.Chr./v.Chr. end with '.' (a
# non-word char), making \b impossible to satisfy after the era marker.
_CENTURY_NL_COMPOUND_RE = re.compile(
    r"\b(" + _NL_ORD + r")"
    # connectors: "2e-3e", "2e en 3e", "14de tot (de) 15de", and elliptical hedges
    # "13de, wellicht 14de eeuw"
    r"(?:\s*[-–—]\s*|\s+en\s+|\s+tot(?:\s+de)?\s+"
    r"|\s*,?\s*(?:wellicht|mogelijk|misschien|vermoedelijk|of)\s+)"
    r"(" + _NL_ORD + r")\s+eeuw(?:\s*(n\.Chr\.|v\.Chr\.))?(?!\w)",
    re.IGNORECASE,
)

# Dutch adjective form: "vroeg-4e-eeuws", "4e-eeuwse", "laat-3e-eeuwse"
# \s* handles OCR line-break hyphenation: "vroeg-4e-\neeeuws"
_CENTURY_NL_ADJ_RE = re.compile(
    r"\b(vroeg|midden|laat)?\s*-?\s*(" + _NL_ORD + r")\s*-\s*eeuws?e?\b",
    re.IGNORECASE,
)

# Dutch "midden van de Xe eeuw" — mid-century construction
_CENTURY_NL_MIDDEN_RE = re.compile(
    r"\bmidden\s+van\s+de\s+(" + _NL_ORD + r")\s+eeuw\b",
    re.IGNORECASE,
)

# Dutch ordinal-WORD centuries: "eerste eeuw n.Chr.", "late tweede eeuw",
# "(de) eerste eeuwen onzer jaartelling" (after normalize_archaic → "n.Chr.").
# Group 4 captures the plural "eeuwen", read as "the first centuries" (the named
# century plus the two following, e.g. "eerste eeuwen" → 1–300 AD).
_NL_ORD_WORD = "|".join(_ORDINAL_WORD_NL.keys())
_CENTURY_NL_WORD_RE = re.compile(
    r"\b(vroege?|midden|late?)?\s*-?\s*(" + _NL_ORD_WORD + r")\s+(eeuw|eeuwen)"
    r"(?:\s*(n\.Chr\.|v\.Chr\.))?(?!\w)",
    re.IGNORECASE,
)

# --- Single century expressions ---

# English: "2nd century AD", "late 3rd century CE", "3rd century BC"
# Group 3 captures the era marker so the caller can detect BC/BCE.
_CENTURY_EN_RE = re.compile(
    r"\b(early|mid(?:dle)?|late)?\s*(" + _EN_ORD + r")\s+centur(?:y|ies)(?:\s*(AD|CE|BC|BCE))?\b",
    re.IGNORECASE,
)

# Dutch: "2e eeuw n.Chr.", "laat-3e eeuw", "2e eeuw v.Chr."
# Group 3 captures the era marker so the caller can detect v.Chr.
# Uses (?!\w) instead of \b at the end because n.Chr./v.Chr. end with '.' (a
# non-word char), making \b impossible to satisfy after the era marker.
_CENTURY_NL_RE = re.compile(
    r"\b(vroeg|midden|laat)?\s*-?\s*(" + _NL_ORD + r")\s+eeuw(?:\s*(n\.Chr\.|v\.Chr\.))?(?!\w)",
    re.IGNORECASE,
)

# English compound ordinal-word ranges: "third and fourth centuries AD", "first to third century BCE"
_ORDINAL_WORD_ALT = (
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|twenty-first"
)
_CENTURY_EN_WORD_COMPOUND_RE = re.compile(
    r"\b(" + _ORDINAL_WORD_ALT + r")"
    r"(?:\s*[-–—]\s*|\s+and\s+|\s+to\s+|\s+through\s+)"
    r"(" + _ORDINAL_WORD_ALT + r")"
    r"\s+centur(?:y|ies)(?:\s*(?:AD|CE|BC|BCE))?\b",
    re.IGNORECASE,
)

# English ordinal-word centuries: "first century BCE", "late second century AD"
_CENTURY_EN_WORD_RE = re.compile(
    r"\b(early|mid(?:dle)?|late)?\s*"
    r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|"
    r"eighteenth|nineteenth|twentieth|twenty-first)\s+"
    r"centur(?:y|ies)(?:\s*(?:AD|CE|BC|BCE))?\b",
    re.IGNORECASE,
)

# --- Broad period labels (conservative: require a qualifier OR "period/periode") ---
_BROAD_PERIOD_RE = re.compile(
    r"\b(?:"
    r"(?:early|late|mid(?:dle)?|vroeg|laat|midden)\s*-?\s*"
    r"(?:Roman(?:\s+period)?|[Rr]omeins(?:e)?(?:\s+periode)?)"
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _century_to_range(n: int, qualifier: Optional[str] = None, bce: bool = False) -> Tuple[int, int]:
    if bce:
        # No year 0: nth century BC spans -n*100 .. -((n-1)*100)-1
        # (e.g. 1st century BC = 100 BC..1 BC = -100..-1).
        start = -n * 100
        end = -(n - 1) * 100 - 1
        if qualifier == "early":
            return start, start + 50
        if qualifier == "late":
            return start + 50, end
        return start, end
    # No year 0: nth century AD spans (n-1)*100+1 .. n*100
    # (e.g. 1st century = 1..100, 2nd century = 101..200).
    start = (n - 1) * 100 + 1
    end = n * 100
    if qualifier == "early":
        return start, start + 50
    if qualifier == "mid":
        return start + 25, end - 25  # middle half of the century
    if qualifier == "late":
        return start + 50, end
    return start, end  # no qualifier = full century


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_date_signals(text: str) -> List[Dict]:
    """
    Extract structured date signals from *text* using regex patterns.

    Returns a list of dicts, each with:
        expression  — raw matched text
        start       — integer year (negative = BCE)
        end         — integer year
        date_type   — "explicit_range" | "century_expression" | "broad_period"
        precision   — "high" | "medium" | "low"
        source      — always "context_sentence"
    """
    signals: List[Dict] = []
    occupied: List[Tuple[int, int]] = []  # char spans already claimed

    def _claim(match: re.Match, start_yr: int, end_yr: int, date_type: str, precision: str) -> None:
        """Record a date signal for this match, unless its character span overlaps one already
        claimed. Because patterns are run in priority order (compound century → explicit year →
        single century → broad period), this "first claim wins" rule stops a broad/inner pattern
        from re-counting a stretch of text a more specific one already consumed."""
        ms, me = match.start(), match.end()
        if any(_spans_overlap(ms, me, os, oe) for os, oe in occupied):
            return
        occupied.append((ms, me))
        signals.append({
            "expression": match.group(0).strip(),
            "start": min(start_yr, end_yr),
            "end": max(start_yr, end_yr),
            "date_type": date_type,
            "precision": precision,
            "source": "context_sentence",
        })

    # 0. Dutch adjective and midden-van-de constructions (claim span before compound/single)
    for m in _CENTURY_NL_ADJ_RE.finditer(text):
        qual_raw = (m.group(1) or "").lower()
        ord_raw = m.group(2).lower()
        n = _ORDINAL_NL.get(ord_raw)
        if n is None:
            continue
        qual = _QUALIFIER_NL.get(qual_raw)
        start, end = _century_to_range(n, qual)
        _claim(m, start, end, "century_expression", "medium")

    for m in _CENTURY_NL_MIDDEN_RE.finditer(text):
        ord_raw = m.group(1).lower()
        n = _ORDINAL_NL.get(ord_raw)
        if n is None:
            continue
        start, end = _century_to_range(n, "mid")
        _claim(m, start, end, "century_expression", "medium")

    # 1. Compound century ranges (highest priority — claim span before singles)
    for m in _CENTURY_EN_COMPOUND_RE.finditer(text):
        n1 = _ORDINAL_EN.get(m.group(1).lower())
        n2 = _ORDINAL_EN.get(m.group(2).lower())
        if n1 and n2:
            era = (m.group(3) or "").upper()
            bce = era in ("BC", "BCE")
            if bce:
                s1, _ = _century_to_range(max(n1, n2), bce=True)
                _, e2 = _century_to_range(min(n1, n2), bce=True)
            else:
                s1, _ = _century_to_range(min(n1, n2))
                _, e2 = _century_to_range(max(n1, n2))
            _claim(m, s1, e2, "century_expression", "medium")

    for m in _CENTURY_EN_WORD_COMPOUND_RE.finditer(text):
        n1 = _ORDINAL_WORD_EN.get(m.group(1).lower())
        n2 = _ORDINAL_WORD_EN.get(m.group(2).lower())
        if n1 and n2:
            full_match = m.group(0)
            bce = bool(re.search(r"\b(?:BC|BCE)\b", full_match, re.IGNORECASE))
            if bce:
                # Higher ordinal = earlier (more negative) for BCE
                s1, _ = _century_to_range(max(n1, n2), bce=True)
                _, e2 = _century_to_range(min(n1, n2), bce=True)
            else:
                s1, _ = _century_to_range(min(n1, n2))
                _, e2 = _century_to_range(max(n1, n2))
            _claim(m, s1, e2, "century_expression", "medium")

    for m in _CENTURY_NL_COMPOUND_RE.finditer(text):
        n1 = _ORDINAL_NL.get(m.group(1).lower())
        n2 = _ORDINAL_NL.get(m.group(2).lower())
        if n1 and n2:
            era = (m.group(3) or "").lower().replace(".", "").replace(" ", "")
            bce = "vchr" in era
            if bce:
                s1, _ = _century_to_range(max(n1, n2), bce=True)
                _, e2 = _century_to_range(min(n1, n2), bce=True)
            else:
                s1, _ = _century_to_range(min(n1, n2))
                _, e2 = _century_to_range(max(n1, n2))
            _claim(m, s1, e2, "century_expression", "medium")

    # 2. Explicit year expressions (prefix form: "AD 70", "AD 70–120")
    for m in _YEAR_PREFIX_RE.finditer(text):
        era = m.group(1).upper()
        yr1 = int(m.group(2))
        yr2 = int(m.group(3)) if m.group(3) else yr1
        if era == "BC":
            yr1, yr2 = -yr1, -yr2
        _claim(m, yr1, yr2, "explicit_range", "high")

    # 3. Explicit year expressions (suffix form: "70 AD", "19-16 BC", "70 n.Chr.", "50 v.Chr.")
    for m in _YEAR_SUFFIX_RE.finditer(text):
        yr1 = int(m.group(1))
        yr2 = int(m.group(2)) if m.group(2) else yr1
        marker = m.group(3).lower().replace(".", "").replace(" ", "")
        # Negate for BCE/BC and Dutch/German v.Chr.; "bce" check comes first since "bc" ⊂ "bce"
        if "bce" in marker or "vchr" in marker or marker == "bc":
            yr1, yr2 = -yr1, -yr2
        _claim(m, yr1, yr2, "explicit_range", "high")

    # 4. Single English century expressions
    for m in _CENTURY_EN_RE.finditer(text):
        qual_raw = (m.group(1) or "").lower()
        ord_raw = m.group(2).lower()
        n = _ORDINAL_EN.get(ord_raw)
        if n is None:
            continue
        era = (m.group(3) or "").upper()
        bce = era in ("BC", "BCE")
        qual = _QUALIFIER_EN.get(qual_raw)
        start, end = _century_to_range(n, qual, bce=bce)
        _claim(m, start, end, "century_expression", "medium")

    # 5. Single Dutch century expressions
    for m in _CENTURY_NL_RE.finditer(text):
        qual_raw = (m.group(1) or "").lower()
        ord_raw = m.group(2).lower()
        n = _ORDINAL_NL.get(ord_raw)
        if n is None:
            continue
        era = (m.group(3) or "").lower().replace(".", "").replace(" ", "")
        bce = "vchr" in era
        qual = _QUALIFIER_NL.get(qual_raw)
        start, end = _century_to_range(n, qual, bce=bce)
        _claim(m, start, end, "century_expression", "medium")

    # 5b. Dutch ordinal-WORD century expressions ("eerste eeuw n.Chr.",
    #     "de eerste eeuwen onzer jaartelling" → plural read as a 3-century span)
    for m in _CENTURY_NL_WORD_RE.finditer(text):
        qual_raw = (m.group(1) or "").lower()
        n = _ORDINAL_WORD_NL.get(m.group(2).lower())
        if n is None:
            continue
        plural = m.group(3).lower() == "eeuwen"
        era = (m.group(4) or "").lower().replace(".", "").replace(" ", "")
        bce = "vchr" in era
        qual = "early" if qual_raw.startswith("vroeg") else \
               "late" if qual_raw.startswith("laat") or qual_raw == "late" else \
               "mid" if qual_raw == "midden" else None
        start, end = _century_to_range(n, qual, bce=bce)
        if plural and not bce:
            # "the first centuries" — extend through the two following centuries.
            end = end + 200
        _claim(m, start, end, "century_expression", "medium")

    # 6. Ordinal-word English century expressions ("first century BCE", "late second century AD")
    for m in _CENTURY_EN_WORD_RE.finditer(text):
        qual_raw = (m.group(1) or "").lower()
        word_raw = m.group(2).lower()
        n = _ORDINAL_WORD_EN.get(word_raw)
        if n is None:
            continue
        full_match = m.group(0)
        bce = bool(re.search(r"\b(?:BC|BCE)\b", full_match, re.IGNORECASE))
        qual = _QUALIFIER_EN.get(qual_raw)
        start, end = _century_to_range(n, qual, bce=bce)
        _claim(m, start, end, "century_expression", "medium")

    # 7. Broad period labels
    for m in _BROAD_PERIOD_RE.finditer(text):
        key = re.sub(r"\s+", " ", m.group(0).lower()).strip()
        for period_key, ps, pe in _BROAD_PERIODS:
            if period_key in key:
                _claim(m, ps, pe, "broad_period", "low")
                break

    return signals


# ---------------------------------------------------------------------------
# LLM-assisted date extraction (Part 3 fallback)
# ---------------------------------------------------------------------------

_LLM_DATE_PROMPT = """\
You are an archaeological date parser for Roman-period excavation reports from the Netherlands (ca. 12 BCE – 450 CE). Read the context sentence below.

Term found: {term}
Context sentence: {context}

Does the context sentence contain a date expression? A date expression must include:
- a year number AND an era marker (AD, BC, CE, BCE, n.Chr., v.Chr.), OR
- an ordinal century word AND "century" or "eeuw", OR
- a named Roman sub-period: Early Roman, Middle Roman, Late Roman, vroeg-Romeins, midden-Romeins, laat-Romeins

If the sentence contains NO such expression, respond with:
{{"has_date": false, "expressions": []}}

If it does, copy the exact phrase from the sentence verbatim and parse its year range.
Rules:
- "text" MUST be copied character-for-character from the context sentence — never paraphrase or invent.
- Use negative integers for BCE/BC dates (e.g., -50 for 50 BCE).

Respond with JSON only, no explanation:
{{"has_date": true, "expressions": [{{"text": "<verbatim phrase>", "start_year": <integer>, "end_year": <integer>}}]}}
"""


def extract_dates_llm(context_text: str, term: str) -> list:
    """
    Use the LLM to extract date expressions that regex did not capture.
    Returns a list of signal dicts in the same format as extract_date_signals.
    """
    import json
    from src.llm_client import call_llm

    prompt = _LLM_DATE_PROMPT.format(
        term=term,
        context=" ".join(context_text.split()),
    )

    raw = call_llm(prompt)

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        parsed = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return []

    if not parsed.get("has_date", False):
        return []

    _DATE_KEYWORDS = re.compile(
        r"\d|roman|vroeg|laat|midden|early|late|middle|eeuw|century|centur",
        re.IGNORECASE,
    )
    _MAX_EXPR_CHARS = 60
    _MAX_EXPR_WORDS = 8

    signals = []
    for expr in parsed.get("expressions", []):
        text = expr.get("text", "").strip()
        start_yr = expr.get("start_year")
        end_yr = expr.get("end_year")
        if not text or start_yr is None or end_yr is None:
            continue
        # Reject whole-sentence pastes and other over-long extractions
        if len(text) > _MAX_EXPR_CHARS or len(text.split()) > _MAX_EXPR_WORDS:
            continue
        # Reject expressions with no digit or date keyword — likely hallucinated
        if not _DATE_KEYWORDS.search(text):
            continue
        try:
            s = int(start_yr)
            e = int(end_yr)
        except (TypeError, ValueError):
            continue
        signals.append({
            "expression": text,
            "start": min(s, e),
            "end": max(s, e),
            "date_type": "llm_extracted",
            "precision": "medium",
            "source": "llm",
        })

    return signals

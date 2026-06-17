"""
SINGLE SOURCE OF TRUTH for archaeological PERIOD and EMPEROR date ranges.

Every place that maps a period/emperor word to a year range derives from PERIODS, so the values
can never drift apart:
  - the hybrid prompt's date-conversion block      -> prompt_period_block()
  - the hybrid deterministic period gazetteer       -> gazetteer()
  - date_parser's broad-period date mapping         -> imports PERIODS
  - the rule pipeline's period vocabulary           -> period_overrides()  (load_chron_vocab)

Composition:
  - ABR/ARCHIS period codes (ROM, ROMV, ROMVA, … ME, MEV, … MEL) with their canonical ARCHIS
    dates + many EN/NL synonyms are loaded from data/vocabularies/period_vocab.json (generated from the
    curated code list; ARCHIS dates per code, emperor terms excluded).
  - Emperor reigns and the pre-Roman / named-dynasty periods are kept here as literals.

Emperors keep their REIGN dates and WIN over period-code terms (so "Augustan" -> -27..14, not the
ROMVA period date). Edit ABR dates in the JSON (or its generator), emperors/pre-Roman here.
"""
import json
import re
from collections import namedtuple
from pathlib import Path

_VOCAB_DIR = Path(__file__).resolve().parent.parent / "data" / "vocabularies"
_VOCAB_PATH = _VOCAB_DIR / "period_vocab.json"     # ABR period codes (ROM*/ME*) + synonyms
_EMPEROR_PATH = _VOCAB_DIR / "emperor_vocab.json"  # emperor reigns + dynasties (canonical)

Period = namedtuple("Period", "label start end kind prompt code terms")

# Periods NOT in the ABR period code list (pre-Roman + named medieval dynasties) — kept here.
_EXTRA = [
    ("Merovingian", 450, 750, ["merovingisch", "merovingian", "merowingisch", "mérovingien"]),
    ("Carolingian", 750, 900, ["karolingisch", "carolingian", "carolingien"]),
    ("Iron Age", -800, -12, ["ijzertijd", "iron age", "eisenzeit", "âge du fer"]),
    ("Early Iron Age", -800, -500, ["vroege ijzertijd", "vroeg-ijzertijd", "early iron age"]),
    ("Middle Iron Age", -500, -250, ["midden-ijzertijd", "midden ijzertijd", "middle iron age"]),
    ("Late Iron Age", -250, -12, ["late ijzertijd", "laat-ijzertijd", "late iron age"]),
    ("Bronze Age", -2000, -800, ["bronstijd", "bronze age", "bronzezeit", "âge du bronze"]),
    ("Neolithic", -5300, -2000, ["neolithicum", "neolithic", "neolithikum", "néolithique"]),
]


def roman_overlaps(start, end):
    """True if a find is in Roman scope: undated, or its [start, end] overlaps ROMAN_WINDOW.

    ROMAN_WINDOW is a tunable setting (config); this is the logic that applies it, shared by
    the pottery summary, the hybrid extractor, and the evaluators. Imported lazily so this
    low-level module stays importable without config on the path.
    """
    from config import ROMAN_WINDOW

    def _i(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None
    s, e = _i(start), _i(end)
    if s is None and e is None:
        return True                       # undated -> keep
    ws, we = ROMAN_WINDOW
    lo = s if s is not None else -10**9
    hi = e if e is not None else 10**9
    # STRICT (positive-width) overlap: a mere boundary touch does not count, so a Medieval find
    # 450..1500 (meeting the window only at the point 450) is dropped, while a late-Roman find
    # ending at 450 — but starting earlier — still overlaps and is kept.
    return lo < we and hi > ws


def _has_date(start, end) -> bool:
    """True if the find carries at least one parseable date endpoint."""
    def _i(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None
    return _i(start) is not None or _i(end) is not None


def nonroman_label(text) -> bool:
    """True if `text` clearly names a SOLE non-Roman period (Medieval, Iron Age, ...) with NO Roman
    mention. The Roman mention is a veto, so a span like 'Roman to Medieval' is never flagged. Used
    only as a dates-subordinate secondary gate (see roman_in_scope) — never to date a find."""
    from config import NONROMAN_PERIOD_MARKERS, ROMAN_MARKERS
    t = (text or "").lower()
    if not t:
        return False
    if any(rm in t for rm in ROMAN_MARKERS):
        return False                      # any Roman mention -> keep (protects Roman->Medieval spans)
    return any(nm in t for nm in NONROMAN_PERIOD_MARKERS)


def roman_in_scope(start, end, text: str = "") -> bool:
    """Full scope test = the date gate (roman_overlaps) PLUS a secondary label gate. Dates take
    precedence: a find with any real date is judged solely by roman_overlaps (so every Roman-
    overlapping find is kept regardless of label); the label gate only drops a find that is fully
    UNDATED and clearly names a sole non-Roman period. Shared by output and the scorers."""
    from config import POTTERY_DROP_NONROMAN_LABELS
    if not roman_overlaps(start, end):
        return False
    if POTTERY_DROP_NONROMAN_LABELS and not _has_date(start, end) and nonroman_label(text):
        return False
    return True


def _load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def _load():
    items = []
    # emperors + dynasties (canonical reigns)
    for v in _load_json(_EMPEROR_PATH, []):
        if v.get("terms"):
            items.append(Period(v["label"], v["start"], v["end"], v["kind"],
                                bool(v.get("prompt")), None, v["terms"]))
    # ABR period codes (ROM*/ME*) + synonyms
    for code, v in _load_json(_VOCAB_PATH, {}).items():
        if v.get("terms"):
            items.append(Period(v.get("label_en") or code, v["start"], v["end"],
                                "period", bool(v.get("prompt")), code, v["terms"]))
    # pre-Roman + named medieval dynasties (not ABR-coded)
    items += [Period(l, s, e, "period", True, None, t) for l, s, e, t in _EXTRA]
    items.sort(key=lambda p: p.end - p.start)   # narrowest first -> specific wins in the gazetteer
    return items


PERIODS = _load()


def gazetteer():
    """[(compiled_regex, start, end)] for the hybrid's own-quote period backfill — narrowest first,
    so the first match wins (a sub-period term beats the broad one; emperors beat the Roman period)."""
    out = []
    for p in PERIODS:
        if not p.terms:
            continue
        rx = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in p.terms) + r")\b", re.IGNORECASE)
        out.append((rx, p.start, p.end))
    return out


def period_overrides():
    """{term: (start, end)} for every synonym — used by the rule pipeline's period vocabulary.
    Period codes are added narrowest-first (setdefault), then emperors overwrite so emperor words
    keep their reign dates."""
    out = {}
    for p in PERIODS:
        if p.kind != "emperor":
            for t in p.terms:
                out.setdefault(t, (p.start, p.end))
    for p in PERIODS:
        if p.kind == "emperor":
            for t in p.terms:
                out[t] = (p.start, p.end)
    return out


def prompt_period_block():
    """Generated period/emperor date lines for the hybrid prompt (so it can't drift). Lists only the
    prompt-level periods (broad + mid codes, not every A/B sub-code) + emperor reigns."""
    per = sorted([p for p in PERIODS if p.prompt and p.kind != "emperor"], key=lambda p: p.start)
    pline = "; ".join(f'"{p.label}" = {p.start}..{p.end}' for p in per)
    emp = ", ".join(f"{p.label} {p.start}..{p.end}"
                    for p in sorted([p for p in PERIODS if p.kind == "emperor" and p.prompt],
                                    key=lambda p: p.start))
    return f"{pline}; emperor reigns ({emp})"

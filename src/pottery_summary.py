"""Pottery summary — the report-level "which pots were found" deliverable.

Consolidates the per-record pipeline output into one row per distinct pottery find
for a report: deduplicates prose-vs-table re-mentions, enriches each find with
canonical names and dates from the pottery vocabulary, resolves the find's site, and
applies the Roman-period scope filter. Optional LLM passes handle ambiguous dedup,
context classification, and find consolidation (coreference). Writes one
<report>.csv per report (the pottery summary) to the destination passed by the caller.
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.cleaner import normalize_archaic
from src.pottery_extractor import _VESSEL_FORM_RE
from src.hybrid_extractor import _date_certainty, _overall, _roman_period_clamp   # shared helpers


# Maximum character distance between a descriptive name and a typology code
# in the same sentence for them to be considered one pottery entity.
_PAIR_DISTANCE_THRESHOLD = 120

# "<vessel> of form/type <code>" — the explicit vessel word names the find's form.
_VESSEL_OF_FORM_RE = re.compile(
    r"\b(plate|bowl|cup|dish|beaker|jar|jug|flagon|flask|bottle|lid|mortarium|amphora"
    r"|krater|tankard|urn)s?\s+of\s+(?:form|type)\b",
    re.IGNORECASE,
)
# CSV pot names too generic to be worth keeping when a more specific cue exists.
_GENERIC_POT_NAMES = {"pottery", "aardewerk", "ceramics", "ceramic", "keramiek",
                      "vessel", "vessels", ""}

# Catalogue/find-number prefixing a typology code on its own entry line, e.g.
# "--/89-0-0/8128, Drag. 29 (Fig. 22.6).". In such a catalogue the find IS identified by
# its number, so that number (not the CSV ware name) is the Pot_name the gold records.
# Matched as "<number>," immediately before the code, anchored at the end of the slice.
_CATALOGUE_NUM_TAIL_RE = re.compile(r"((?:-{1,2}/)?\d[\d./+\- ]*?\d)\s*,\s*$")
# A pure find-catalogue number used as a pottery name ("--/27-3-17/5260", "702-19/7-0-11"):
# only digits, slashes, dots, dashes, spaces (no letters). Used to collapse repeats.
_CATALOGUE_NAME_RE = re.compile(r"[\d./+\- ]*\d[\d./+\- ]*")
# Out-of-scope contexts for an UNTYPED ware mention: a bibliography citation ("…, pp. 154-156")
# or an early-modern section ("Nieuwe tijd: musketkogels…"). Deliberately excludes
# "Middeleeuwen/medieval" — those finds are in scope (see old_rep_2 medieval gold).
_OUT_OF_SCOPE_RE = re.compile(r"(?i)\bnieuwe tijd\b|\bpp\.\s*\d")

# Pattern IDs that are pottery typology codes (from the CSV).
_TYPOLOGY_PREFIX = "csv_pottery_"

# Pattern IDs that are chronology/century records — not pottery, skip entirely.
_SKIP_PREFIXES = ("chronology_", "century_")

# Canonical hints for site-type records that should not appear as pottery.
_SKIP_CANONICALS = {"VILLA_RUSTICA", "C_015", "C_018"}

# Pattern categories that are not pottery vessel types.
_SKIP_CATEGORIES = {"site_type"}

# Context labels to exclude — purely irrelevant records (medieval stray finds,
# post-medieval pottery, etc.) are still shown but clearly labelled.
_EXCLUDE_CATEGORIES = {"site_type"}


def _normalise_code(code: str) -> str:
    return re.sub(r'[^A-Z0-9]+', '_', code.upper()).strip('_')


# ── Table-reference dedup ─────────────────────────────────────────────────────
# A pot listed in a finds TABLE is sometimes also mentioned in the surrounding
# prose (a figure caption, a recap, "this type ..."). Such a prose mention is a
# back-reference to the table entry, not a separate find, and must not produce a
# second output row. We suppress a prose row only when (a) the SAME canonical pot
# already appears as a TABULAR-origin row on the same page and (b) the prose row
# carries a reference signal — never when two table rows repeat (a genuine second
# tabular entry) nor across pages/chapters (likely a distinct find).

# Tokens that betray a flattened finds table (NL/EN headers, totals, "Tabel 6.6").
_TABLE_SIGNATURE_RE = re.compile(
    r'\b(?:materiaal|categorie|vormtype|eindtotaal|aantal|totaal|'
    r'tabel\s*\d|table\s*\d|fabric|count)\b',
    re.IGNORECASE,
)

# Signals that a prose sentence is referring back to / illustrating an item
# already introduced, rather than reporting a new find.
_REFERENCE_MARKER_RE = re.compile(
    r'\bafb\.?\b|\bfig\.?\b|\bfiguur\b|\btabel\b|\bplaat\b|\bpl\.|\bzie\b|\bvgl\.?\b'
    r'|\(vnr|\bvan (?:het|dit) type\b|\bdit type\b|\bgenoemde\b|\bbovengenoemd\w*'
    r'|\baforementioned\b|\bthe same type\b|\bsee (?:fig|table|plate|tabel)\b',
    re.IGNORECASE,
)


def _numeric_line_ratio(text: str) -> float:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0.0
    numeric = sum(1 for ln in lines if re.fullmatch(r'\d+', ln))
    return numeric / len(lines)


def _is_tabular_origin(text: str) -> bool:
    """True when a row's source text looks like a flattened finds table rather
    than prose — used to tell a table entry from a prose mention of it."""
    if not text:
        return False
    hits = {m.group(0).lower() for m in _TABLE_SIGNATURE_RE.finditer(text)}
    if len(hits) >= 2:
        return True
    # A dense column of bare counts (MAI/aantal cells) is also tabular.
    return _numeric_line_ratio(text) >= 0.3 and len(text.splitlines()) >= 5


def _has_reference_marker(text: str) -> bool:
    return bool(_REFERENCE_MARKER_RE.search(text or ""))


_LLM_REFERENCE_PROMPT = """\
You are an expert archaeologist reading an excavation report.
The pottery type "{pottery_name}" (typology: {typology}) is already listed in a
finds TABLE in this report. The PROSE passage below also mentions this type.

Decide which it is:
  "reference" : the prose merely refers back to / describes / illustrates the item
                already in the table (e.g. a figure caption, a recap, "this type …").
  "new_find"  : the prose reports a SEPARATE, additional find of this type — from a
                different feature, context, layer, or chapter — that should be
                counted on its own.

When genuinely unsure, answer "new_find" (keep the row).
Return ONLY a JSON object, nothing else:
{{"verdict": "reference" | "new_find", "reasoning": "<one sentence>"}}

Prose passage: {prose}
"""


def _llm_is_reference(pottery_name: str, typology: str, prose: str) -> bool:
    """LLM fallback for ambiguous prose: True if it merely references a table entry."""
    from src.llm_client import call_llm

    raw = call_llm(_LLM_REFERENCE_PROMPT.format(
        pottery_name=pottery_name or "—",
        typology=typology or "—",
        prose=(prose or "")[:500],
    ))
    parsed = _extract_json_object(raw)
    if not parsed:
        return False  # conservative: keep the row
    return str(parsed.get("verdict", "")).strip().lower() == "reference"


def _dedup_table_references(rows: List[Dict], use_llm: bool = False) -> Tuple[List[Dict], int]:
    """Suppress prose rows that merely reference a same-page tabular finding of the
    same pot. Deterministic reference markers decide first; ambiguous prose (no
    marker) is sent to the LLM only when ``use_llm`` is set. Returns (kept, n_dropped)."""
    for r in rows:
        r["_tabular"] = _is_tabular_origin(r.get("original_text", ""))

    groups: Dict[Tuple, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        canon = (r.get("typology") or r.get("pottery") or "").strip().lower()
        if not canon:
            continue
        key = (r.get("report_id", ""), str(r.get("page", "")), canon)
        groups[key].append(i)

    suppressed: set = set()
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        has_tabular = any(rows[i]["_tabular"] for i in idxs)
        if not has_tabular:
            continue  # two prose mentions, or two table rows → never collapse here
        for i in idxs:
            if rows[i]["_tabular"]:
                continue  # never drop a table entry
            text = rows[i].get("original_text", "")
            is_ref = _has_reference_marker(text)
            if not is_ref and use_llm:
                is_ref = _llm_is_reference(rows[i].get("pottery", ""),
                                           rows[i].get("typology", ""), text)
            if is_ref:
                suppressed.add(i)

    kept = [r for i, r in enumerate(rows) if i not in suppressed]
    return kept, len(suppressed)


def build_csv_lookup(csv_path: Path) -> Dict[str, str]:
    """
    Build a mapping from canonical_hint (e.g. CHENET_320) to the most
    representative English pot name from the reference CSV.
    Supports both legacy format (typology_nl) and normalized format (typology_code).
    """
    counts: Dict[str, Counter] = defaultdict(Counter)
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            base_raw = row.get('typology_code') or row.get('typology_nl', '')
            base = base_raw.split(':')[0].strip()
            key = _normalise_code(base)
            name = row['pot_name_en'].strip()
            if name:
                counts[key][name] += 1

    # Pick the most common pot name for each key; capitalise first letter.
    return {
        key: counter.most_common(1)[0][0].capitalize()
        for key, counter in counts.items()
    }


def _site_from_spaced_heading(section_title: str) -> str:
    """Collapse a letter-spaced bulletin heading into a site name.

    "A M B I J." → "Ambij", "E I J G E L S H O V E N." → "Eijgelshoven".
    Returns "" when the title is not a letter-spaced heading (e.g. a normal
    section heading or "Unlabeled Section").
    """
    t = (section_title or "").strip().rstrip(".").strip()
    if not t:
        return ""
    tokens = t.split()
    # A letter-spaced heading is all single-character tokens.
    if len(tokens) >= 3 and all(len(tok) == 1 and tok.isalpha() for tok in tokens):
        collapsed = "".join(tokens).capitalize()
        # Bulletin section labels ("BERICHTEN") are not findspots.
        if collapsed.lower() in {"berichten", "mededelingen", "inhoud", "vondstmeldingen",
                                 "kroniek", "literatuur", "boekbespreking", "varia",
                                 "register", "colofon", "redactie"}:
            return ""
        return collapsed
    return ""


def _is_pottery_record(record: Dict) -> bool:
    pid = record.get("pattern_id", "")
    if any(pid.startswith(p) for p in _SKIP_PREFIXES):
        return False
    if record.get("canonical_hint") in _SKIP_CANONICALS:
        return False
    return True


def _is_typology_record(record: Dict) -> bool:
    return record.get("pattern_id", "").startswith(_TYPOLOGY_PREFIX)


def _is_generic_form(record: Dict) -> bool:
    """A bare generic / indeterminate form token captured as a finds-table row
    ("pot", "beker", "onbekend", "indet"). These are findings in their own right but
    carry no typological date, so they are emitted standalone and left undated."""
    if _is_typology_record(record):
        return False
    from src.pottery_extractor import GENERIC_FORM_TOKENS
    term = re.sub(r'\s+', ' ', str(record.get("term_raw", "") or "")).strip().rstrip('?').strip().lower()
    return term in GENERIC_FORM_TOKENS


def _char_distance(a: Dict, b: Dict) -> int:
    """Minimum gap between two records' character spans."""
    a_start, a_end = a.get("start_char", 0), a.get("end_char", 0)
    b_start, b_end = b.get("start_char", 0), b.get("end_char", 0)
    if a_end <= b_start:
        return b_start - a_end
    if b_end <= a_start:
        return a_start - b_end
    return 0  # overlapping



# Synonym normalization: maps period-suffix words to a canonical form so that
# "Claudische tijd", "Claudische tijdvak", "Claudian era" etc. all resolve to
# the same vocabulary entry. Applied to BOTH the input text and the vocab keys.
# Dutch synonyms → "periode"; English synonyms → "period".
_SYNONYM_REPLACEMENTS = [
    # Dutch plurals first (longer match → must come before singular)
    (re.compile(r'\btijdvakken\b', re.IGNORECASE), 'periodes'),
    (re.compile(r'\btijdperken\b', re.IGNORECASE), 'periodes'),
    (re.compile(r'\btijden\b',     re.IGNORECASE), 'periodes'),
    # Dutch singulars
    (re.compile(r'\btijdvak\b',    re.IGNORECASE), 'periode'),
    (re.compile(r'\btijdperk\b',   re.IGNORECASE), 'periode'),
    (re.compile(r'\btijd\b',       re.IGNORECASE), 'periode'),
    # English plurals first
    (re.compile(r'\bepochs\b',     re.IGNORECASE), 'periods'),
    (re.compile(r'\beras\b',       re.IGNORECASE), 'periods'),
    (re.compile(r'\bages\b',       re.IGNORECASE), 'periods'),
    # English singulars
    (re.compile(r'\bepoch\b',      re.IGNORECASE), 'period'),
    (re.compile(r'\bera\b',        re.IGNORECASE), 'period'),
    (re.compile(r'\bage\b',        re.IGNORECASE), 'period'),
]


def _normalize_period_terms(text: str) -> str:
    for pattern, replacement in _SYNONYM_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def load_chron_vocab(path: Path = None) -> Dict[str, Dict]:
    """Period-keyword -> {start, end} vocabulary for the rule pipeline, built ENTIRELY from the
    single source of truth (src/periods.py: ABR period codes + emperors/dynasties + pre-Roman).
    The legacy data/chron_vocab.json has been removed. `path` is accepted for backward-compatible
    call sites but ignored."""
    from src.periods import period_overrides
    return {_normalize_period_terms(t): {"start": s, "end": e}
            for t, (s, e) in period_overrides().items()}


def _match_chron_vocab(text: str, vocab: Dict[str, Dict]) -> Optional[Tuple[int, int]]:
    """
    Scan text for period keyword matches from chron_vocab.
    Both text and vocab keys are pre-normalized to canonical period-suffix forms.
    Returns the narrowest matching date range, or None if no match.
    """
    norm_text = _normalize_period_terms(text)
    spans = []   # (match_start, match_end, year_start, year_end)
    for keyword, dates in vocab.items():
        for m in re.finditer(r'\b' + re.escape(keyword) + r'\b', norm_text, re.IGNORECASE):
            spans.append((m.start(), m.end(), dates["start"], dates["end"]))
    if not spans:
        return None
    # Period RANGE: "<period A> t/m|tot (en met) <period B>" (e.g. "Romeinse tijd t/m Volle
    # Middeleeuwen") spans from A's start to B's end. The nearest period term on each side of
    # the connector is used; this wins over a single narrowest match, which would otherwise
    # return only period B and lose the early start.
    for cm in re.finditer(r"\b(?:t/m|tot en met|tot)\b", norm_text, re.IGNORECASE):
        before = [s for s in spans if s[1] <= cm.start()]
        after = [s for s in spans if s[0] >= cm.end()]
        if before and after:
            a = max(before, key=lambda s: s[1])   # nearest period before the connector
            b = min(after, key=lambda s: s[0])    # nearest period after it
            if b[3] > a[2]:                        # sane forward range
                return a[2], b[3]
    # Otherwise the narrowest single period.
    _, _, start, end = min(spans, key=lambda s: s[3] - s[2])
    return start, end


_LLM_POTTERY_CONTEXT_PROMPT = """\
You are an expert in Roman and medieval archaeology of the Low Countries (Netherlands, Belgium, Germany).
Analyze this passage from an excavation report that mentions a pottery type.

Determine:
1. find_status — how is this pottery mentioned?
   "present"    : a SPECIFIC find actually recovered/excavated at THIS site
   "absent"     : explicitly NOT found, or mentioned negatively
   "comparison" : used as a comparison/parallel, OR a GENERAL statement about the pottery
                  type/period rather than a specific find here — e.g. how the fabric weathers,
                  where the type generally occurs, or which periods it spans ("dit type
                  aardewerk verweert snel", "prehistorisch aardewerk komt voor in…"). If the
                  passage discusses the ware in general and does not assert a concrete find at
                  this site, it is NOT "present".
   "citation"   : appears only in a bibliographic reference, footnote, or author name
   "uncertain"  : genuinely unclear from the passage

2. date_start / date_end — the production/use date of THIS pottery, in integer years (negative = BCE).
   Base it ONLY on chronological phrases written in the passage about THIS find — do NOT use general
   or textbook knowledge of when the type is usually made. Convert period phrases to years using EXACTLY
   these conventions (Xe eeuw = the Xth century AD):
     - "Xe eeuw" / "Xth century" -> (X-1)*100 .. X*100        (4e eeuw = 300-400)
     - "vroege/begin Xe eeuw"    -> (X-1)*100 .. (X-1)*100+50 (vroege 4e = 300-350)
     - "midden Xe eeuw"          -> (X-1)*100+25 .. X*100-25  (midden 4e = 325-375)
     - "late/laat Xe eeuw"       -> (X-1)*100+50 .. X*100     (late 4e = 350-400)
     - "Romeinse tijd" = -12..450; "Laat-Romeinse"/"Late Roman" = 275..450; "Vroeg-Romeins" = 1..150
     - a comparison ("parallellen ... in een <period> nederzetting") dates THIS find to that period
   IGNORE dates that describe other things (coins/munten, other finds, percentages/statistics). If the
   passage states no period for THIS find, return null for both.

3. mention_role — is this a SPECIFIC individual find, or a GENERAL recap mention?
   "specific" : reports one particular excavated object/fragment, usually "een/a <object>" with detail
                (e.g. "een rand van een wrijfschaal met verticale rand", "a wandfragment van een dolium")
   "general"  : a recap, total/count, interpretation, figure caption, footnote, or collective statement
                about finds already described elsewhere — NOT a new individual find. Examples:
                "vijf stukken van voorraadvaten (amfoor en dolium) en twee van wrijfschalen",
                "De fragmenten van voorraadvaten en wrijfschalen wijzen op een opslagfunctie",
                "Wrijfschalen hadden een ruwe bodem", "Het aardewerk is goed herkenbaar".

Return ONLY a JSON object — no text outside it:
{{"find_status": "...", "date_start": <int or null>, "date_end": <int or null>, "mention_role": "specific|general", "find_reasoning": "<one sentence explaining the find_status decision>", "date_reasoning": "<one sentence explaining why these dates were chosen, or 'no date evidence in passage' if null>"}}

Pottery type: {pottery_name}
Typology code: {typology}
Sentence: {sentence}
Wider context: {context}
"""

_LLM_POTTERY_DATE_PROMPT = """\
You are an expert in Roman and medieval archaeology of the Low Countries (Netherlands, Belgium).
Given a pottery type name, provide the typical production and use date range for that type in this regional context.

Return ONLY a JSON object with no explanation:
{{"start": <integer year>, "end": <integer year>}}

Use negative integers for BCE dates (e.g., -50 for 50 BCE).
If you cannot determine the date range with reasonable confidence, return:
{{"start": null, "end": null}}

Pottery type: {pottery_name}
"""


def _extract_json_object(raw: str) -> Optional[Dict]:
    """Best-effort extraction of a single JSON object from a raw LLM response.

    llama3.2 frequently emits malformed JSON; this recovers from the common
    cases observed in practice:
      - a trailing extra brace or text after the object (e.g. '...}}')  → brace
        balancing keeps only the first complete object
      - an unterminated object (truncated, missing the final '}')       → the
        open string/braces are closed
      - a trailing comma before a closing brace/bracket                 → removed
      - a malformed numeric range as a value (e.g. "date_end": 3000-100) → null

    Returns the parsed dict, or None if nothing usable can be recovered.
    """
    if not raw or "{" not in raw:
        return None
    start = raw.index("{")

    # Walk from the first '{' and stop at its matching '}', ignoring braces
    # that appear inside string literals.
    depth = 0
    in_str = False
    esc = False
    end = None
    for i in range(start, len(raw)):
        c = raw[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is not None:
        snippet = raw[start:end]
    else:
        # Truncated object: close any open string and the unbalanced braces.
        snippet = raw[start:].rstrip().rstrip(",")
        if in_str:
            snippet += '"'
        snippet += "}" * max(depth, 1)

    # Try progressively more aggressive repairs; return the first that parses.
    no_trailing_comma = re.sub(r",\s*([}\]])", r"\1", snippet)
    range_to_null = re.sub(r":\s*-?\d+\s*-\s*-?\d+\b", ": null", no_trailing_comma)
    # Missing comma between two adjacent string tokens (e.g. '"...ware," "date_reasoning"').
    missing_comma = re.sub(r'"\s+"', '", "', range_to_null)
    for candidate in (snippet, no_trailing_comma, range_to_null, missing_comma):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            continue
    return None


# ---- Context-classification batching ----
# The per-entity context LLM call is the throughput bottleneck under Claude-only. We batch it with a
# two-pass memoize: pass 1 collects every (pottery_name, typology, sentence, context) the row-builder
# needs (deterministic — computed before the LLM call); we classify them in batches; pass 2 rebuilds
# the rows reading the cache. Same proven pattern as Layer 5 (indexed + schema + per-item fallback).
# Batching off -> the dispatcher just calls the single-item path (original behaviour).
_CTX_COLLECT = None    # when a list, pass-1 collect mode (record keys, skip the LLM)
_CTX_CACHE: Dict = {}  # context key -> (status, ds, de, find_reasoning, date_reasoning, role)


def _ctx_key(pottery_name, typology, sentence, context):
    return (pottery_name, typology or "", sentence[:400], context[:600])


def _llm_pottery_context(pottery_name, typology, sentence, context):
    """Dispatcher (same return contract as before): collect keys (pass 1), serve from the batch
    cache (pass 2), or fall back to the single-item call (batching off / cache miss)."""
    key = _ctx_key(pottery_name, typology, sentence, context)
    if _CTX_COLLECT is not None:
        _CTX_COLLECT.append(key)
        return "uncertain", None, None, "", "", "specific"   # placeholder; pass-1 rows are discarded
    if key in _CTX_CACHE:
        return _CTX_CACHE[key]
    return _llm_pottery_context_single(pottery_name, typology, sentence, context)


def _pottery_batch_size():
    """Entities per context call. config.LLM_BATCH_SIZE overrides (1 = per-item); else auto by
    backend — smaller than Layer 5 because each item's output is richer (status+dates+role)."""
    from config import LLM_BATCH_SIZE, LLM_PROVIDER
    if LLM_BATCH_SIZE:
        return max(1, LLM_BATCH_SIZE)
    if LLM_PROVIDER == "anthropic":
        return 20
    if LLM_PROVIDER == "ollama":
        return 6
    from config import LLM_API_MODEL
    if any(t in (LLM_API_MODEL or "").lower() for t in ("1b", "3b", "8b")):
        return 8
    return 12


# Reuse the single-item rubric verbatim (everything before its "Return ONLY" line), then ask for a
# results array. The rubric portion has no brace placeholders, so it is .format()-safe.
_LLM_POTTERY_CONTEXT_BATCH_PROMPT = (
    _LLM_POTTERY_CONTEXT_PROMPT.split("Return ONLY")[0]
    + 'Classify EVERY numbered item below in the same way. Respond with JSON ONLY (no text outside '
      "it): an object with a \"results\" array holding ONE object per item, echoing each item's index:\n"
      '{{"results": [{{"index": <int>, "find_status": "present|absent|comparison|citation|uncertain", '
      '"date_start": <int or null>, "date_end": <int or null>, "mention_role": "specific|general", '
      '"find_reasoning": "<one sentence>", "date_reasoning": "<one sentence>"}}]}}\n\nItems:\n{items}\n'
)
_POTTERY_CONTEXT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "index": {"type": "integer"},
        "find_status": {"type": "string",
                        "enum": ["present", "absent", "comparison", "citation", "uncertain"]},
        "date_start": {"type": ["integer", "null"]},
        "date_end": {"type": ["integer", "null"]},
        "mention_role": {"type": "string", "enum": ["specific", "general"]},
        "find_reasoning": {"type": "string"},
        "date_reasoning": {"type": "string"},
    },
    "required": ["index", "find_status", "date_start", "date_end", "mention_role",
                 "find_reasoning", "date_reasoning"],
    "additionalProperties": False,
}
_POTTERY_CONTEXT_BATCH_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": _POTTERY_CONTEXT_ITEM_SCHEMA}},
    "required": ["results"],
    "additionalProperties": False,
}


def _parse_results_array(raw):
    """Pull the results array from a batched reply ({"results":[...]} or a bare [...])."""
    obj = _extract_json_object(raw)
    if isinstance(obj, dict) and isinstance(obj.get("results"), list):
        return obj["results"]
    try:
        s = raw.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
        a = json.loads(s[s.index("["): s.rindex("]") + 1])
        return a if isinstance(a, list) else []
    except (ValueError, json.JSONDecodeError):
        return []


def _coerce_context_obj(o):
    """One batch result dict -> the 6-tuple, with the same validation as the single-item path."""
    status = str(o.get("find_status", "uncertain")).lower()
    if status not in {"present", "absent", "comparison", "citation", "uncertain"}:
        status = "uncertain"
    ds, de = _parse_year(o.get("date_start")), _parse_year(o.get("date_end"))
    if ds is None or de is None:
        ds = de = None
    role = str(o.get("mention_role", "specific")).lower()
    if role not in {"specific", "general"}:
        role = "specific"
    return (status, ds, de,
            str(o.get("find_reasoning", o.get("reasoning", ""))),
            str(o.get("date_reasoning", "")), role)


def _batch_classify_contexts(keys):
    """Fill _CTX_CACHE for all keys via batched calls (one per _pottery_batch_size() entities), with
    per-item fallback to the single path for any missing/invalid index. Logs in-progress."""
    keys = list(dict.fromkeys(keys))            # dedupe, keep order
    if not keys:
        return
    from config import LLM_PROVIDER
    B = _pottery_batch_size()
    schema = _POTTERY_CONTEXT_BATCH_SCHEMA if LLM_PROVIDER == "anthropic" else None
    n = (len(keys) + B - 1) // B
    print(f"[Pottery summary] LLM context: {len(keys)} entities, batch size {B} -> {n} call(s)", flush=True)
    from src.llm_client import call_llm
    for bi, k0 in enumerate(range(0, len(keys), B), start=1):
        chunk = keys[k0:k0 + B]
        items = "\n".join(
            f'[{j}] Pottery type: "{kk[0]}" | Typology code: "{kk[1] or "—"}" | '
            f'Sentence: "{kk[2]}" | Wider context: "{kk[3]}"'
            for j, kk in enumerate(chunk))
        got = {}
        try:
            raw = call_llm(_LLM_POTTERY_CONTEXT_BATCH_PROMPT.format(items=items),
                           max_tokens=max(4096, len(chunk) * 160), output_schema=schema)
            for o in _parse_results_array(raw):
                try:
                    got[int(o.get("index"))] = _coerce_context_obj(o)
                except (TypeError, ValueError):
                    continue
        except Exception:
            pass
        for j, kk in enumerate(chunk):
            _CTX_CACHE[kk] = got.get(j) or _llm_pottery_context_single(*kk)
        print(f"[Pottery summary] context batch {bi}/{n} done ({min(k0 + B, len(keys))}/{len(keys)})", flush=True)


def _llm_pottery_context_single(
    pottery_name: str,
    typology: str,
    sentence: str,
    context: str,
) -> Tuple[str, Optional[int], Optional[int], str, str, str]:
    """Call LLM to classify find_status, extract context-aware date, and judge whether
    the mention is a SPECIFIC find or a GENERAL recap/summary.

    Returns (find_status, date_start, date_end, find_reasoning, date_reasoning, mention_role).
    find_status is one of: present / absent / comparison / citation / uncertain.
    mention_role is "specific" or "general".
    """
    from src.llm_client import call_llm

    prompt = _LLM_POTTERY_CONTEXT_PROMPT.format(
        pottery_name=pottery_name,
        typology=typology or "—",
        sentence=sentence[:400],
        context=context[:600],
    )
    raw = call_llm(prompt)
    parsed = _extract_json_object(raw)
    if parsed is None:
        print(f"[LLM pottery context] JSON parse failed for '{pottery_name}'")
        print(f"[LLM pottery context] Raw response: {raw!r}")
        return "uncertain", None, None, "", "", "specific"

    status        = str(parsed.get("find_status", "uncertain")).lower()
    d_start       = _parse_year(parsed.get("date_start"))
    d_end         = _parse_year(parsed.get("date_end"))
    find_reasoning = str(parsed.get("find_reasoning", parsed.get("reasoning", "")))
    date_reasoning = str(parsed.get("date_reasoning", ""))
    # Default to "specific" on anything unexpected — never suppress a find on a bad parse.
    role = str(parsed.get("mention_role", "specific")).lower()
    if role not in {"specific", "general"}:
        role = "specific"
    if status not in {"present", "absent", "comparison", "citation", "uncertain"}:
        status = "uncertain"
    if d_start is not None and d_end is not None:
        return status, d_start, d_end, find_reasoning, date_reasoning, role
    return status, None, None, find_reasoning, date_reasoning, role


def _llm_pottery_dates(pottery_name: str) -> Tuple[Optional[int], Optional[int]]:
    from src.llm_client import call_llm

    raw = call_llm(_LLM_POTTERY_DATE_PROMPT.format(pottery_name=pottery_name))
    parsed = _extract_json_object(raw)
    if parsed is not None:
        s = _parse_year(parsed.get("start"))
        e = _parse_year(parsed.get("end"))
        if s is not None and e is not None:
            return s, e
    return None, None


# Return type for _best_dates: (start, end, method)
_DateResult = Tuple[Optional[int], Optional[int], str]


def _parse_year(value) -> Optional[int]:
    """Parse a year value that may be an int, a plain string int, or contain BCE/AD."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return None
    is_bce = bool(re.search(r'\bBCE?\b', s, re.IGNORECASE))
    m = re.search(r'-?\d+', s)
    if m:
        year = int(m.group())
        if is_bce and year > 0:
            year = -year
        return year
    return None


def _section_dominant_date(section_text: str, chron_vocab: Optional[Dict]) -> Optional[Tuple[int, int]]:
    """The single coherent SPECIFIC date a section states, for phase propagation (#1).

    Returns (start, end) when the section's specific date signals form one cluster
    spanning <=300 years; returns None when there are none, or when they conflict
    (e.g. a Roman AND a medieval signal span >300 years) — so an ambiguous, multi-period
    section never propagates. Generic whole-period labels (Roman -12..450) are excluded
    by the width filter, so only a genuinely specific section date propagates.
    """
    if not section_text:
        return None
    from src.date_parser import extract_date_signals
    text = normalize_archaic(section_text)
    spec = [(s["start"], s["end"]) for s in extract_date_signals(text)
            if s["precision"] in ("high", "medium") and 0 <= (s["end"] - s["start"]) <= 300]
    if chron_vocab:
        vr = _match_chron_vocab(text, chron_vocab)
        if vr is not None and (vr[1] - vr[0]) <= 300:
            spec.append(vr)
    spec = sorted(set(spec))
    if not spec:
        return None
    lo, hi = min(s for s, _ in spec), max(e for _, e in spec)
    if hi - lo > 300:          # signals span >300 yr → conflicting periods → ambiguous
        return None
    return lo, hi


def _best_dates(
    record: Dict,
    chron_vocab: Optional[Dict] = None,
    use_llm: bool = False,
    pottery_name: str = "",
    llm_context_dates: Optional[Tuple[int, int]] = None,
    section_dates: Optional[Dict] = None,
) -> "_DateResult":
    """
    Return (start, end, method) for a pottery record.

    Priority (TYPOLOGY FIRST):
      1. Typology date — Layer 6 assignment or pattern/vocabulary date — always
         wins when present, even over a narrower context period. A specific type
         (e.g. amphora "Camulodunum 184" 43–250) must not be overridden by an
         unrelated period mention nearby ("Augustan" → −12–25).  → "typology"
      Records WITHOUT a typology date then fall through to:
      2. Explicit year/range in the own sentence (AD/BC + year) → "text_explicit"
      3. Century expression OR period term — narrowest wins → "text_century" / "chron_vocab"
      4. LLM context-aware date (pre-computed) → "llm_context"
      5. LLM typological knowledge (use_llm only) → "llm"
    """
    from src.date_parser import extract_date_signals

    # --- 0. Generic / indeterminate finds-table forms stay UNDATED ----------
    # "pot", "beker", "onbekend", "indet" have no typological date and the source
    # gives none; any date here would be a context-bleed artefact, so force empty.
    if _is_generic_form(record):
        return None, None, ""

    # --- 1. Typology date wins when present ---------------------------------
    # Only the real pattern/vocabulary date carried on the record counts as a
    # "typology date" here. Layer 6's chrono_date_label is NOT used at this stage:
    # for generic finds it is context-derived (not a true type date) and must not
    # pre-empt the text/context dating below — it stays a low-priority fallback.
    ds, de = _parse_year(record.get("date_start")), _parse_year(record.get("date_end"))
    if ds is not None and de is not None:
        return ds, de, "typology"

    # --- No typology date: date from text/context ---------------------------
    # Modernize archaic spelling/idioms first (old reports) so parser+vocab match:
    # "Romeinschen tijd" → "Romeinse tijd", "onzer jaartelling" → "n.Chr.".
    def _explicit(context: str) -> Optional["_DateResult"]:
        """High-precision explicit year/range (e.g. 'AD 70', '19-16 BC')."""
        if not context:
            return None
        signals = extract_date_signals(normalize_archaic(context))
        explicit = [s for s in signals if s["precision"] == "high"]
        if explicit:
            explicit.sort(key=lambda s: s["end"] - s["start"])
            return explicit[0]["start"], explicit[0]["end"], "text_explicit"
        return None

    def _period(context: str) -> Optional["_DateResult"]:
        """Century expression OR chron_vocab period term — narrowest wins."""
        if not context:
            return None
        context = normalize_archaic(context)
        signals = extract_date_signals(context)
        p2: List[Tuple[int, int, int, str]] = []  # (width, start, end, method)
        medium = [s for s in signals if s["precision"] == "medium"]
        if medium:
            medium.sort(key=lambda s: s["end"] - s["start"])
            best = medium[0]
            p2.append((best["end"] - best["start"], best["start"], best["end"], "text_century"))
        if chron_vocab:
            vocab_result = _match_chron_vocab(context, chron_vocab)
            if vocab_result is not None:
                vs, ve = vocab_result
                p2.append((ve - vs, vs, ve, "chron_vocab"))
        if p2:
            p2.sort()
            return p2[0][1], p2[0][2], p2[0][3]
        return None

    # Prefer the term's OWN sentence; only fall back to the wider ±2-sentence
    # date_context if the sentence yields no date. This stops a date from an
    # adjacent, unrelated record (e.g. a neighbouring "Middeleeuwen:" entry) from
    # bleeding in when the term's own sentence already states its period.
    # Tried in order of precision: the find's own sentence, the ±2-sentence window, the
    # char window, then the wider FORWARD window (llm_date_context). The forward window is
    # last so a date in the find's own sentence always wins; it only adds a date when the
    # nearer contexts have none — e.g. a bulletin item that states the period a few
    # sentences after the finds ("…uit de tweede eeuw na Christus…").
    # clause_date_context (find → next clause boundary) is tried FIRST so a find's own
    # date in an enumeration wins over a neighbour's; it's empty/dateless for the common
    # single-find case, where the engine falls through to the contexts below unchanged.
    contexts = (record.get("line_date_context", ""),
                record.get("clause_date_context", ""),
                record.get("context_sentence", ""),
                record.get("date_context", ""),
                record.get("context_window", ""),
                record.get("llm_date_context", ""))

    # 2. Explicit year/range — most reliable text date, beats everything below.
    for context in contexts:
        result = _explicit(context)
        if result is not None:
            return result

    # 2.5 (C2). Passage-grounded LLM date. When enabled it overrides the regex
    # century/period dates below — for narrative finds the LLM attributes the right
    # clause's date (e.g. a Late-Roman comparison) where narrowest-wins picks the
    # wrong adjacent period. It only fires when the LLM actually grounded a date
    # (llm_context_dates is None when the passage states no period), so it never
    # invents one. Still below typology + explicit dates.
    from config import POTTERY_LLM_DATE_OVERRIDE
    if POTTERY_LLM_DATE_OVERRIDE and llm_context_dates is not None:
        return llm_context_dates[0], llm_context_dates[1], "llm_context"

    # 3. Century / period regex + chron_vocab (the find's OWN context).
    own = None
    for context in contexts:
        result = _period(context)
        if result is not None:
            own = result
            break

    # 3.5 (#1) Section-phase propagation. An untyped find that its own context leaves
    # entirely UNDATED inherits a SPECIFIC date stated for its section (e.g. "dates to the
    # 2nd century AD" several sentences away). It never OVERRIDES an existing date — not even
    # the generic Roman default — because that default is often the correct answer (gold's
    # whole-assemblage finds) and a section may carry a misleading narrow signal. Typed finds
    # never reach here (they returned at step 1). Section date is None for ambiguous
    # multi-period sections, so nothing propagates across a Roman↔medieval boundary.
    if section_dates and own is None:
        sd = section_dates.get(record.get("section_id", "")) or None
        if sd is not None:
            return sd[0], sd[1], "section_phase"
    if own is not None:
        return own

    # 4. LLM context date (fallback when override is off).
    if llm_context_dates is not None:
        return llm_context_dates[0], llm_context_dates[1], "llm_context"

    # Layer 6 chronology assignment (fallback only — context above takes priority)
    chrono_label = record.get("chrono_date_label", "")
    if chrono_label and record.get("chrono_status") == "assigned":
        parts = re.split(r'[–—]', chrono_label)
        if len(parts) >= 2:
            cs, ce = _parse_year(parts[0].strip()), _parse_year(parts[1].strip())
            if cs is not None:
                return cs, ce, "typology"

    # LLM typological knowledge (last resort, no context)
    if use_llm and pottery_name:
        s, e = _llm_pottery_dates(pottery_name)
        if s is not None:
            return s, e, "llm"

    return None, None, ""


# Canonical English names for bare Dutch ware terms that have no typology code (so they
# never get an English name from the CSV typology lookup). The gold standards record these
# wares in English ("Smooth-walled pottery", "Lid", …); without this map the pipeline would
# emit the raw Dutch trigger word. Keyed on the lower-cased extracted name.
_NL_WARE_CANON_EN = {
    "gladwandig": "Smooth-walled pottery",
    "gladwandig aardewerk": "Smooth-walled pottery",
    "ruwwandig": "Rough-walled pottery",
    "ruwwandig aardewerk": "Rough-walled pottery",
    "gevernist aardewerk": "Varnished pottery",
    "wrijfschaal": "Grinding bowl",
    "wrijfschalen": "Grinding bowl",
    "deksel": "Lid",
    "deksels": "Lid",
    # Dutch diminutive vessel forms (19th-c. antiquarian prose: "schaaltjes, kommetjes,
    # bekertjes, kruikjes, urntjes"). Mapped to the gold's English (plural for the -s form).
    "schaaltje": "Dish",       "schaaltjes": "Dishes",
    "kommetje": "Bowl",        "kommetjes": "Bowls",
    "bekertje": "Beaker",      "bekertjes": "Beakers",
    "kruikje": "Jug",          "kruikjes": "Jugs",
    "urntje": "Urn",           "urntjes": "Urns",
    "potje": "Pot",            "potjes": "Pots",
    "kannetje": "Jug",         "kannetjes": "Jugs",
    "schoteltje": "Saucer",    "schoteltjes": "Saucers",
    "bordje": "Plate",         "bordjes": "Plates",
    "drinkbeker": "Drinking cup", "drinkbekers": "Drinking cups",
    "ruwwandige": "Rough-walled pottery", "gladwandige": "Smooth-walled pottery",
    "rode ruwwandige": "Red rough-walled pottery", "rood ruwwandig": "Red rough-walled pottery",
    "wit gladwandig": "White smooth-walled pottery", "witte gladwandige": "White smooth-walled pottery",
    "geverfde beker": "Painted beaker", "geverfd beker": "Painted beaker",
    "painted cups": "Painted cups", "painted cup": "Painted cup",
    "inheems aardewerk": "Indigenous pottery",
    "handgevormd aardewerk": "Indigenous pottery",
    "handgevormd inheems aardewerk": "Indigenous pottery",
    # Remaining bare Dutch ware names → the gold's English (win #1).
    "aardewerk": "Pottery",
    "belgisch aardewerk": "Belgian pottery", "belgische waar": "Belgian pottery",
    "kogelpotaardewerk": "Globular pottery", "kogelpot": "Globular pottery",
    "scherf met het stempel": "Sherd with stamp",
    "kookpotten": "Cooking pots", "kookpot": "Cooking pot",
    "kruikwaar": "Flagon ware",
    "geverfde bekers": "Painted beakers",
    "beker": "Beaker", "bekers": "Beakers",
    # Bare (non-diminutive) Dutch vessel words — real reports use these constantly.
    "kruik": "Jug", "kruiken": "Jugs", "kan": "Jug", "kannen": "Jugs",
    "bord": "Plate", "borden": "Plates",
    "schaal": "Bowl", "schalen": "Bowls", "kom": "Bowl", "kommen": "Bowls",
    "urn": "Urn", "urnen": "Urns",
    "honingpot": "Honey pot", "honingpotje": "Honey pot", "honingpotjes": "Honey pots",
    "honingpotten": "Honey pots",
    "kurkurn": "Cork urn", "kurkurnen": "Cork urns",
    "lamp": "Lamp", "lampen": "Lamps", "olielamp": "Oil lamp", "olielampje": "Oil lamp",
    "olielampjes": "Oil lamps", "firmalamp": "Firmalamp", "firmalampje": "Firmalamp",
    "firmalampjes": "Firmalamps",
    "pannetje": "Pan", "pannetjes": "Pans",
    "gordelbeker": "Girdle beaker", "gordelbekers": "Girdle beakers",
    "kruikamfoor": "Flagon-amphora", "kruikamforen": "Flagon-amphorae",
    "wrijfkom": "Grinding bowl", "wrijfkommen": "Grinding bowls",
    "wrijfschotel": "Grinding bowl", "wrijfschotels": "Grinding bowls",
    "pingsdorf": "Pingsdorf ware", "pingsdorfer": "Pingsdorf ware",
    "badorf": "Badorf ware", "badorfer": "Badorf ware",
    "siegburg": "Siegburg stoneware", "paffrath": "Paffrath ware", "andenne": "Andenne ware",
    # French vessel/ware words (French-language reports)
    "assiette": "Plate", "assiettes": "Plates", "écuelle": "Bowl", "écuelles": "Bowls",
    "ecuelle": "Bowl", "ecuelles": "Bowls", "tasse": "Cup", "tasses": "Cups",
    "cruche": "Jug", "cruches": "Jugs", "lampe": "Lamp", "lampes": "Lamps",
    "vase": "Vase", "vases": "Vases", "urne": "Urn", "urnes": "Urns",
    "amphore": "Amphora", "amphores": "Amphorae", "gobelet": "Beaker", "gobelets": "Beakers",
    "pichet": "Jug", "sigillée": "Terra sigillata", "sigillee": "Terra sigillata",
    "terre cuite": "Pottery", "terre rouge": "Pottery", "terre sigillée": "Terra sigillata",
    "poterie": "Pottery", "céramique": "Pottery", "ceramique": "Pottery",
}

# Canonical casing for English ware names that the chron-vocab path emits lowercase
# (win #2). Singular and plural are kept DISTINCT on purpose: unifying them lets the
# re-mention suppressor treat "Amphora" and "Amphorae" (different finds/dates) as the
# same entity and drop one. Generic form words (bowl, jar, plate) are absent so they
# stay lowercase, as the gold records them.
_WARE_CANON_EN = {
    "terra sigillata": "Terra sigillata",
    "terra nigra": "Terra nigra",
    "terra rubra": "Terra rubra",
    "dolium": "Dolium", "dolia": "Dolia",
    "amphora": "Amphora", "amphorae": "Amphorae",
    "mortaria": "Mortaria", "mortarium": "Mortarium",
}


def _pottery_name_for(record: Dict, csv_lookup: Dict[str, str]) -> str:
    """Derive the human-readable pottery name for a record."""
    if _is_typology_record(record):
        hint = record.get("canonical_hint", "")
        return csv_lookup.get(hint, record.get("preferred_label") or record.get("term_raw", ""))
    name = record.get("preferred_label") or record.get("term_raw", "")
    key = name.strip().lower()
    if key in _NL_WARE_CANON_EN:
        return _NL_WARE_CANON_EN[key]
    return _WARE_CANON_EN.get(key, name)


_HUBENER_CODE_RE = re.compile(
    r"H[üu]bener.*?(?:groep(?:en)?|gruppen?|groups?)\s+(\d)", re.IGNORECASE
)


def _typology_code_for(record: Dict) -> str:
    """The typology code as it appears in the report (e.g. "Alzey 27").

    The matched term (``term_raw``) is the typology code itself; ``preferred_label``
    holds the descriptive ware name (e.g. "Late Roman cooking pot"), which belongs
    in the ``pottery`` column, not here.
    """
    if _is_typology_record(record):
        code = record.get("term_raw") or record.get("preferred_label", "")
        # Narrative Hübener-group citations ("Hubener 1968, groepen 3-6") carry the
        # whole span as term_raw; normalize to the clean typology label.
        m = _HUBENER_CODE_RE.search(code)
        if m:
            return f"Hübener Group {m.group(1)}"
        code = re.sub(r"\s+", " ", code).strip()
        # Expand the abbreviated family to its canonical form so the typology column
        # reads "Dragendorff 18/31" (as the gold records it), not "Drag. 18/31".
        code = re.sub(r"^Drag\.\s*", "Dragendorff ", code)
        # Collapse a stray space around the slash in a dual code so it reads "18/31"
        # (as the vocab/gold records it), not "18/ 31" when the report prints it spaced.
        code = re.sub(r"(\d)\s*/\s*(\d)", r"\1/\2", code)
        return code
    return ""


def _context_label_for(records: List[Dict], primary: Dict) -> Tuple[str, float]:
    """Return (context_label, context_confidence) from the primary record, falling
    back to the most common label across the sentence group."""
    label = primary.get("context_label", "")
    conf  = float(primary.get("context_confidence") or 0.0)
    if label:
        return label, conf
    # Fallback: majority vote across the group
    labels = [r.get("context_label", "") for r in records if r.get("context_label")]
    if labels:
        label = Counter(labels).most_common(1)[0][0]
        conf   = float(primary.get("context_confidence") or 0.0)
    return label or "", conf


def _build_pottery_rows(
    sentence_records: List[Dict],
    csv_lookup: Dict[str, str],
    chron_vocab: Optional[Dict] = None,
    use_llm: bool = False,
    section_dates: Optional[Dict] = None,
) -> List[Dict]:
    """
    Given all pottery records from one sentence, produce one or more output rows.
    Typology records are paired with the nearest descriptive-name record.
    Each output row now includes Layer 5 context_label/confidence and, when
    use_llm=True, an LLM-derived find_status and context-aware date.
    """
    typo_records = [r for r in sentence_records if _is_typology_record(r)]
    # Generic finds-table forms are emitted standalone and excluded from typology
    # pairing, so a bare "beker" row in a flattened table cannot be swallowed as the
    # descriptive name of a nearby typology code (e.g. an adjacent "Holwerda 94").
    generic_records = [r for r in sentence_records if _is_generic_form(r)]
    name_records = [r for r in sentence_records
                    if not _is_typology_record(r) and not _is_generic_form(r)]

    paired_name_ids: set = set()
    rows = []

    def _make_row(
        primary: Dict,
        pottery_name: str,
        typology_str: str,
        start: Optional[int],
        end: Optional[int],
        method: str,
        term_raw: str = "",
        start_char: int = 0,
    ) -> Dict:
        context_label, context_conf = _context_label_for(sentence_records, primary)
        sentence = primary.get("context_sentence", "").strip()
        # "<vessel> of form/type <code>" (e.g. "a plate of form Consp. 11"): the explicit
        # vessel word is the find's form. Prefer it over a GENERIC CSV name ("pottery")
        # when a typology is present, so the pot column reflects what the text actually says.
        if typology_str and pottery_name.strip().lower() in _GENERIC_POT_NAMES:
            vof = _VESSEL_OF_FORM_RE.search(sentence)
            if vof:
                pottery_name = vof.group(1).lower()
        # Catalogue entry "<number>, Drag. XX …": the find-number is the Pot_name. The
        # code can sit deep in a multi-line block, so locate it and look at the text
        # immediately before it for a trailing "<number>,".
        if typology_str and term_raw:
            code = re.sub(r"\s+", " ", term_raw).strip()
            idx = sentence.find(code)
            if idx > 0:
                bm = _CATALOGUE_NUM_TAIL_RE.search(sentence[:idx])
                # Require a "/" — real find-catalogue numbers have one (89-0-0/8128); this
                # rejects a bare preceding TYPE number ("Drag. 37, Drag. 33" must not make
                # the Drag 33 row's name "37").
                if bm and "/" in bm.group(1):
                    pottery_name = bm.group(1).strip()
        # For the LLM (C2), prefer the forward-focused context anchored at the find:
        # it captures the clause that dates THIS find while excluding off-topic dates
        # that precede it (coin statistics, an earlier vessel's date) which mislead
        # even a strong model. Falls back to the ±2 date_context, then the sentence.
        context = (primary.get("llm_date_context", "")
                   or primary.get("date_context", "")
                   or primary.get("context_window", "")
                   or sentence)

        llm_find_status   = ""
        llm_find_reasoning = ""
        llm_date_reasoning = ""
        mention_role = "specific"
        llm_ctx_dates: Optional[Tuple[int, int]] = None

        if use_llm:
            llm_status, llm_ds, llm_de, llm_find_r, llm_date_r, mention_role = _llm_pottery_context(
                pottery_name, typology_str, sentence, context
            )
            llm_find_status    = llm_status
            llm_find_reasoning = llm_find_r
            llm_date_reasoning = llm_date_r
            if llm_ds is not None and llm_de is not None:
                llm_ctx_dates = (llm_ds, llm_de)

        # Re-run date selection with LLM context dates as P2.5
        if llm_ctx_dates is not None:
            start, end, method = _best_dates(
                primary, chron_vocab, use_llm=False,
                pottery_name=pottery_name,
                llm_context_dates=llm_ctx_dates,
                section_dates=section_dates,
            )

        # Clean OCR line-breaks from the raw matched term (e.g. "Chenet\n320" → "Chenet 320")
        term_cleaned = re.sub(r'\s+', ' ', term_raw).strip()

        # Site name, in priority order:
        #   1. site from the section heading — spaced-caps ("A M B I J." → Ambij) or
        #      inline ("Houten (Utr.).") — computed in structure.split_into_sections
        #   2. inventory-table site code forward-filled onto the find (e.g. table_2)
        site_name = (primary.get("section_site", "")
                     or _site_from_spaced_heading(primary.get("section_title", ""))
                     or primary.get("site_code", ""))

        # Per-axis certainties for schema parity with the hybrid (see column docs): presence is a
        # REAL Layer-5 judgment (context_confidence); name is a heuristic (typed > generic); date
        # is derived from date_method. overall = mean.
        _pres_cert = max(0, min(10, round(context_conf * 10))) if context_conf else ""
        _name_cert = 8 if typology_str else 6
        _has_date = (start not in ("", None)) or (end not in ("", None))
        _date_cert, _date_reason = _date_certainty(method, _name_cert, _has_date)
        return {
            "report_id":          primary.get("report_id", ""),
            "site_name":          site_name,
            "page":               primary.get("page", ""),
            "pottery":            pottery_name,
            "typology":           typology_str,
            "term_found":         term_cleaned,
            "term_found_normalized_en": pottery_name,
            "quantity":           "",   # rule-based path does not extract counts; hybrid path fills this
            "start_date":         start,
            "end_date":           end,
            "date_method":        method,
            "context_label":      context_label,
            "pot_name_certainty_level":     _name_cert,
            "pot_name_llm_reasoning":       "name from typology code" if typology_str else "name from ware match",
            "pot_presence_certainty_level": _pres_cert,
            "pot_presence_llm_reasoning":   llm_find_reasoning or (f"classified {context_label}" if context_label else "rule detection"),
            "dates_certainty_level":        _date_cert,
            "date_llm_reasoning":           llm_date_reasoning or _date_reason,
            "overall_certainty_level":      _overall(_name_cert, _pres_cert, _date_cert),
            "original_text":      sentence,
            "_start_char":        start_char,    # internal; not exported to CSV
            "_mention_role":      mention_role,  # internal: "specific" | "general"
            # internal: came from a flattened finds-table CELL (its own line sits between
            # bare-number cells — the D1 table-cell signal). Each numbered table row is a
            # DISTINCT find even when it shares a generic ware name ("aardewerk"/"Pottery"),
            # so it must be exempt from the re-mention suppressor below.
            "_table_cell":        bool(primary.get("line_date_context", "")),
        }

    for typo in typo_records:
        # Find nearest unpaired descriptive name
        best_name: Optional[Dict] = None
        best_dist = _PAIR_DISTANCE_THRESHOLD + 1

        for name_rec in name_records:
            if id(name_rec) in paired_name_ids:
                continue
            dist = _char_distance(typo, name_rec)
            if dist < best_dist:
                best_dist = dist
                best_name = name_rec

        if best_name is not None:
            csv_name     = csv_lookup.get(typo.get("canonical_hint", ""), "")
            pottery_name = csv_name or _pottery_name_for(best_name, csv_lookup)
            # Decide whether to CONSUME the paired descriptive-name record.
            #  • csv_name empty → we use best_name as the pottery name, so consume it.
            #  • best_name is a bare VESSEL FORM (Bowl, Jar, Plate, strainer…) or a
            #    generic form → it IS this code's own form in a flattened finds table
            #    ("Drag 37 … Bowl"), so consume it to avoid a duplicate standalone row.
            #  • otherwise best_name is a DISTINCT WARE (gevernist aardewerk, terra nigra)
            #    that merely follows the code in a comma enumeration — do NOT consume it,
            #    or a separate find is lost. A redundant ware descriptor (e.g. standalone
            #    "terra sigillata" beside "Terra sigillata plate / Drag 18/31") is removed
            #    later by the subsume step instead.
            best_label = _pottery_name_for(best_name, csv_lookup)
            best_is_form = bool(_VESSEL_FORM_RE.match(best_label.strip())) or _is_generic_form(best_name)
            if (not csv_name) or best_is_form:
                paired_name_ids.add(id(best_name))
            start, end, method = _best_dates(typo, chron_vocab, False, pottery_name, section_dates=section_dates)
            name_start, name_end, name_method = _best_dates(best_name, chron_vocab, False, pottery_name, section_dates=section_dates)
            # Text-based dates from the name record always override the typology date.
            # chron_vocab dates from the name record only override when the typology
            # itself has no date — otherwise a broad period label like "Late Roman"
            # matched from the table caption would incorrectly replace a specific
            # typology range like Alzey 27 (300–450).
            if name_method in ("text_explicit", "text_century"):
                start, end, method = name_start, name_end, name_method
            elif start is None:
                start, end, method = name_start, name_end, name_method
            rows.append(_make_row(typo, pottery_name, _typology_code_for(typo), start, end, method,
                                  term_raw=typo.get("term_raw", ""),
                                  start_char=typo.get("start_char", 0)))
        else:
            unpaired_name = _pottery_name_for(typo, csv_lookup)
            start, end, method = _best_dates(typo, chron_vocab, False, unpaired_name, section_dates=section_dates)
            rows.append(_make_row(typo, unpaired_name, _typology_code_for(typo), start, end, method,
                                  term_raw=typo.get("term_raw", ""),
                                  start_char=typo.get("start_char", 0)))

    # Remaining unpaired descriptive name records
    for name_rec in name_records:
        if id(name_rec) in paired_name_ids:
            continue
        name_label = _pottery_name_for(name_rec, csv_lookup)
        start, end, method = _best_dates(name_rec, chron_vocab, False, name_label, section_dates=section_dates)
        rows.append(_make_row(name_rec, name_label, "", start, end, method,
                              term_raw=name_rec.get("term_raw", ""),
                              start_char=name_rec.get("start_char", 0)))

    # Generic finds-table forms — standalone, always undated.
    for gen_rec in generic_records:
        gen_label = _pottery_name_for(gen_rec, csv_lookup)
        rows.append(_make_row(gen_rec, gen_label, "", None, None, "",
                              term_raw=gen_rec.get("term_raw", ""),
                              start_char=gen_rec.get("start_char", 0)))

    return rows


def export_pottery_summary(
    records: List[Dict],
    csv_lookup: Dict[str, str],
    output_path: Path,
    chron_vocab: Optional[Dict] = None,
    use_llm: bool = False,
    ref_dedup_llm: bool = False,
    section_texts: Optional[Dict[str, str]] = None,
    consolidate_llm: bool = False,
) -> None:
    # Include all pottery records — context_label is now a visible output column
    # so the user can filter in the spreadsheet rather than having the pipeline hide records.
    pottery_records = [r for r in records if _is_pottery_record(r)]

    # #1: per-section dominant date, for phase propagation onto undated/generic finds.
    section_dates = {sid: _section_dominant_date(txt, chron_vocab)
                     for sid, txt in (section_texts or {}).items()}

    # Group by chunk so that vessel-form name records (line-level sentence "bowl")
    # and typology code records (whole-chunk sentence) end up in the same group and
    # can be paired by character distance.  In prose text, all records from one chunk
    # land here too; the 120-char pairing threshold still separates unrelated entities.
    groups: Dict[Tuple, List[Dict]] = defaultdict(list)
    for r in pottery_records:
        key = (r.get("report_id", ""), r.get("chunk_id", ""), r.get("section_id", ""))
        groups[key].append(r)

    # When the per-entity context LLM is on AND batching is enabled, do a two-pass: pass 1 collects
    # every context-classification input the row-builder needs (deterministic), batch-classify them,
    # then pass 2 builds the rows reading the cache. Otherwise build directly (single calls).
    global _CTX_COLLECT, _CTX_CACHE
    _CTX_CACHE = {}
    if use_llm and _pottery_batch_size() > 1:
        _CTX_COLLECT = []
        for group_records in groups.values():        # pass 1: collect keys only (rows discarded)
            _build_pottery_rows(group_records, csv_lookup, chron_vocab, use_llm,
                                section_dates)
        collected, _CTX_COLLECT = _CTX_COLLECT, None
        _batch_classify_contexts(collected)

    all_rows = []
    for group_records in groups.values():
        all_rows.extend(_build_pottery_rows(group_records, csv_lookup, chron_vocab, use_llm,
                                            section_dates))

    # Deduplicate by detection position. The trigger-level dedup in pottery_extractor
    # (abs_trigger_start) already ensures the same physical position in the text never
    # produces two candidates. Using start_char here therefore only collapses genuine
    # duplicates while preserving all distinct occurrences (e.g., same typology code
    # appearing in multiple fabric sub-groups of a table).
    seen = set()
    deduped = []
    for row in all_rows:
        key = (row["pottery"].lower(), row["typology"].lower(), row.get("_start_char", 0))
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    # Win #4 (narrow): a catalogue number is a unique find ID, so the same number with the
    # same typology can only be ONE object — collapse repeats (the recap mentions detected
    # at different positions). Restricted to pure catalogue-number names ("--/27-3-17/5260")
    # so distinct same-named finds (e.g. table_1's seven separate "jar" rows) are untouched.
    # Drop UNTYPED ware mentions found in a bibliography citation or an early-modern
    # ("Nieuwe tijd") section — both are out-of-scope false positives (B1). Typed finds
    # are kept (a Drag code next to a citation is still a real find).
    deduped = [r for r in deduped
               if r["typology"] or not _OUT_OF_SCOPE_RE.search(r.get("original_text", ""))]

    cat_seen = set()
    collapsed = []
    for row in deduped:
        name = row["pottery"].strip()
        if "/" in name and _CATALOGUE_NAME_RE.fullmatch(name):
            ck = (name.lower(), row["typology"].lower(), row.get("site_name", ""),
                  row["start_date"], row["end_date"])
            if ck in cat_seen:
                continue
            cat_seen.add(ck)
        collapsed.append(row)
    deduped = collapsed

    # Remove name-only rows subsumed by a paired row on the same sentence (prose text).
    # A standalone "terra sigillata" is redundant when "terra sigillata / Chenet 320"
    # already covers the same mention.  original_text is used as the sentence proxy;
    # vessel-form rows from tables have very short original_text ("Bowl") and will not
    # match the long chunk-level original_text of typology rows, so they are unaffected.
    paired = {(r["pottery"].lower(), r["original_text"][:80]) for r in deduped if r["typology"]}
    deduped = [
        row for row in deduped
        if row["typology"]
        or not any(
            row["pottery"].lower() in paired_pot and row["original_text"][:80] == paired_orig
            for paired_pot, paired_orig in paired
        )
    ]

    # Drop GENERAL recap/summary/interpretation re-mentions (LLM-judged mention_role)
    # of a pottery that is ALSO reported as a SPECIFIC find of the same canonical name.
    # The "specific row of the same name must exist" guard means a type whose only mention
    # is general is never lost — so genuine repeats (two specific dolia) both survive while
    # the "voorraadvaten (amfoor en dolium)" recap is removed.
    try:
        from config import POTTERY_SUPPRESS_SUMMARY_MENTIONS
    except ImportError:
        POTTERY_SUPPRESS_SUMMARY_MENTIONS = False
    if POTTERY_SUPPRESS_SUMMARY_MENTIONS:
        # Key on (pottery name, SITE) so a "general" row is dropped only when a SPECIFIC
        # find of the same pot exists AT THE SAME SITE. In a prose report all finds share
        # one site, so genuine re-mentions collapse; in an inventory report each find sits
        # under its own site-code, so distinct per-site finds (e.g. table_2's "aardewerk"
        # at codes 508067, 500383, …) are never mistaken for re-mentions of one another.
        # Only UNTYPED ware mentions participate: a typed find is distinct by its code, so
        # it is never suppressed and never counts as the "specific" twin of another. This
        # stops typed finds that share a generic pot name ("Pottery" for Oberaden 83 /
        # Stuart 147 …) from collapsing one another.
        specific_keys = {(r["pottery"].lower(), r.get("site_name", "")) for r in deduped
                         if not r.get("typology") and r.get("_mention_role") != "general"}
        before = len(deduped)
        deduped = [r for r in deduped
                   if r.get("typology")
                   or r.get("_table_cell")            # each numbered finds-table row is distinct
                   or r.get("_mention_role") != "general"
                   or (r["pottery"].lower(), r.get("site_name", "")) not in specific_keys]
        if before - len(deduped):
            print(f"[Pottery summary] suppressed {before - len(deduped)} general/recap re-mention(s)")

    # Collapse prose rows that merely reference a same-page table entry of the
    # same pot (e.g. a figure caption echoing a finds-table type). Genuine repeat
    # table rows and cross-page mentions are preserved.
    if ref_dedup_llm:
        print(f"[Pottery summary] table-reference dedup over {len(deduped)} rows ...", flush=True)
    deduped, n_ref = _dedup_table_references(deduped, use_llm=ref_dedup_llm)
    if n_ref:
        print(f"[Pottery summary] suppressed {n_ref} table-reference echo(es)")

    # Layer 7.4 — find consolidation (coreference). Collapses mentions that refer to the
    # SAME physical find (conclusions/Archis recaps, prose repeats, cross-references)
    # which the per-mention classifier cannot detect in isolation. Off unless enabled.
    if consolidate_llm:
        from src.consolidation import consolidate_finds
        print(f"[Pottery summary] consolidation (coreference) over {len(deduped)} rows ...", flush=True)
        deduped, n_consol = consolidate_finds(deduped, use_llm=True)
        if n_consol:
            print(f"[Pottery summary] consolidated {n_consol} recap mention(s) into existing finds")

    # Context date completion: one-sided Roman-period clamp (same as the hybrid) for finds left
    # with exactly one date endpoint.
    for r in deduped:
        ns, ne, clamped = _roman_period_clamp(r.get("start_date", ""), r.get("end_date", ""))
        if clamped:
            r["start_date"], r["end_date"] = ns, ne
            r["date_method"] = "context_clamp"
            dc, dr = _date_certainty("context_clamp", r.get("pot_name_certainty_level", 6), True)
            r["dates_certainty_level"], r["date_llm_reasoning"] = dc, dr
            r["overall_certainty_level"] = _overall(
                r.get("pot_name_certainty_level"), r.get("pot_presence_certainty_level"), dc)

    # Roman-period scope filter (same rule as the hybrid): keep undated + Roman-overlapping finds;
    # drop only fully-undated finds whose label clearly names a sole non-Roman period.
    try:
        from config import POTTERY_ROMAN_ONLY
        from src.periods import roman_in_scope
    except ImportError:
        POTTERY_ROMAN_ONLY = False
    if POTTERY_ROMAN_ONLY:
        def _scope_text(r):
            return " ".join(str(r.get(k, "")) for k in
                            ("pottery", "term_found_normalized_en", "term_found", "original_text"))
        before = len(deduped)
        deduped = [r for r in deduped
                   if roman_in_scope(r.get("start_date", ""), r.get("end_date", ""), _scope_text(r))]
        if before - len(deduped):
            print(f"[Pottery summary] dropped {before - len(deduped)} off-scope (non-Roman) find(s)")

    # Canonicalize site names (collapse spelling/format variants of the same place).
    from src.site_norm import apply_site_canonicalization
    n_site = apply_site_canonicalization(deduped, "site_name", use_llm=use_llm)
    if n_site:
        print(f"[Pottery summary] merged {n_site} site-name variant(s)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "report_id", "site_name", "page", "pottery", "typology", "term_found", "term_found_normalized_en",
            "quantity",
            "start_date", "end_date", "date_method", "context_label",
            "pot_name_certainty_level", "pot_name_llm_reasoning",
            "pot_presence_certainty_level", "pot_presence_llm_reasoning",
            "dates_certainty_level", "date_llm_reasoning",
            "overall_certainty_level",
            "original_text",
        ], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(deduped)

    print(f"[Pottery summary] {len(deduped)} pottery entities → {output_path}")

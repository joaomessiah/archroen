"""Layer 5 — context interpretation.

Classifies each candidate by how the report refers to it — present, absent,
comparison, uncertain, or irrelevant — using deterministic cue rules first and an
LLM fallback for low-confidence cases. The label gates chronology assignment.
"""
import re
import json
from typing import Dict, List, Tuple

# Canonical terms that are post-Roman and therefore irrelevant for Roman archaeology
POST_ROMAN_CANONICALS = {
    "CENTURY_15_AD", "CENTURY_16_AD", "CENTURY_17_AD",
    "CENTURY_18_AD", "CENTURY_19_AD", "CENTURY_20_AD", "CENTURY_21_AD",
    "CENTURY_RANGE_15_16_AD", "CENTURY_RANGE_16_17_AD", "CENTURY_RANGE_17_18_AD",
    "CENTURY_RANGE_18_19_AD", "CENTURY_RANGE_19_20_AD", "CENTURY_RANGE_20_21_AD",
}

# Canonical terms that are pre-Roman (3rd century BC and earlier) and therefore
# irrelevant for the Dutch Roman period (starts ~12 BCE). The 1st–2nd century BC
# are excluded because they overlap with the early Roman horizon.
PRE_ROMAN_CANONICALS = {
    "CENTURY_3_BC", "CENTURY_4_BC", "CENTURY_5_BC",
    "CENTURY_6_BC", "CENTURY_7_BC", "CENTURY_8_BC", "CENTURY_9_BC", "CENTURY_10_BC",
    "CENTURY_RANGE_2_3_BC", "CENTURY_RANGE_3_4_BC", "CENTURY_RANGE_4_5_BC",
    "CENTURY_RANGE_5_6_BC", "CENTURY_RANGE_6_7_BC",
}

# Phrases that indicate the sentence is historiographic, not an archaeological find
_HISTORIOGRAPHIC_RE = re.compile(
    r"\bsince the\b|\bhistory of\b|\bresearch history\b"
    r"|\bonderzoeksgeschiedenis\b|\bonderzoeksoverzicht\b"
    r"|\bhistorisch kader\b|\bstand van het onderzoek\b"
    r"|\bliteratuuroverzicht\b|\bhistoriografisch\b"
    r"|\bhistoriographic\b|\bstate of research\b|\bscholarly history\b",
    re.IGNORECASE,
)

# Bibliographic citation patterns: "(ed) (2023) Title..." or "Author (2023)"
_BIBLIOGRAPHIC_RE = re.compile(
    r"\([Ee]ds?\)(?:\s*\(\d{4}[a-z]?\)|\s+[A-Z])"  # (ed)/(eds) followed by (year) or Title-word
    r"|\(\d{4}[a-z]?\)\s+[A-Z]"                     # (year[a-z]) followed by an uppercase Title-word
    r"|\(\d{4}[a-z]?\),\s"                           # (year[a-z]), — in-text citation with comma
    r"|\b[Ee]t al\.\s*\(\d{4}[a-z]?\)"             # et al. (year[a-z])
    r"|\b[Pp]p?\.\s*\d+"                            # p. 12 / pp. 12–15  (page reference)
    r"|\b[Vv]ol\.\s*\d+"                            # vol. 3
    r"|\b\d{4}[a-z]\b"                              # year+letter suffix (2011a, 2005b) — unambiguous cite
    r"|(?<!\()[A-Z][a-z]+\s+\d{4}\)",               # Surname Year) not inside own parens — multi-author cite
)

# Finds vocabulary: used to guard the bibliographic filter — sentences that mention
# actual finds should not be suppressed even if they also contain a citation.
_FINDS_VOCAB_RE = re.compile(
    r"\b(gevonden|aangetroffen|found|recovered|discovered|dates|dateert"
    r"|aanwezig|identified|recorded|established|emerged|founded|constructed"
    r"|built|inhabited|occupied|settled|evidenced|attested|demonstrated"
    r"|recognised|recognized|shows?|displays?|bewoning|nederzetting"
    r"|vondsten|sporen|urnenveld|schatvondst)\b",
    re.IGNORECASE,
)

# Ordered rule groups: first match wins.
# Each entry: (compiled_regex, context_label, confidence)
# Order matters: absent/comparison before present to avoid "not found" → present.
_RULES: List[Tuple[re.Pattern, str, float]] = [
    (
        re.compile(
            r"\b(could not be assigned|not found|not present|absent"
            r"|not recorded|not attested|nowhere found|never found"
            # Dutch negation + find verb (multi-word phrases before single-word variants)
            r"|nergens aangetroffen|nergens gevonden"
            r"|nooit aangetroffen|nooit gevonden"
            r"|nog niet aangetroffen|nog niet gevonden"
            r"|niet meer aangetroffen|niet meer gevonden"
            r"|niet aangetroffen|niet gevonden|ontbreekt|ontbreken"
            # Additional Dutch absent phrases
            r"|geen sporen van|geen aanwijzingen voor|geen vondsten"
            r"|afwezig|niet bewaard|niet gedocumenteerd|niet herkend"
            r"|buiten het plangebied|buiten beschouwing)\b",
            re.IGNORECASE,
        ),
        "absent",
        0.90,
    ),
    (
        re.compile(
            r"\b(vergelijkbaar|similar to|comparable to|resembles|cf\.|compare)\b",
            re.IGNORECASE,
        ),
        "comparison",
        0.90,
    ),
    (
        re.compile(
            r"\b(may indicate|possibly|perhaps|could be|might|mogelijk"
            r"|waarschijnlijk|probably|could not be dated)\b",
            re.IGNORECASE,
        ),
        "uncertain",
        0.70,
    ),
    (
        re.compile(
            r"\b(gevonden|aangetroffen|found|recovered|discovered|dates|dateert"
            r"|aanwezig|identified|recorded"
            # construction / emergence
            r"|established|emerged|founded|constructed|built|inhabited|occupied|settled"
            # description of what a find consists of / contains
            r"|consists?\s+of|comprised\s+of|evidenced|attested|demonstrated|recognised|recognized"
            # display / showing (artifact descriptions)
            r"|shows?|displays?|depicted|marked\s+with|inscribed"
            # Dutch finds / habitation
            r"|bewoning|nederzetting|vondsten|sporen|urnenveld|schatvondst"
            r"|uit\s+de\s+(?:Romeinse|IJzer|Midden|Late|Vroege)"
            r")\b",
            re.IGNORECASE,
        ),
        "present",
        0.85,
    ),
]

_VALID_LABELS = {"present", "absent", "comparison", "uncertain", "irrelevant"}

_LLM_PROMPT_TEMPLATE = """\
You are an archaeological text analyst. A term was detected in a Roman-period excavation report from the Netherlands (ca. 12 BCE – 450 CE). Pottery types, construction phases, coin finds, and site features from this period are archaeologically relevant.
Your task: classify whether this mention represents actual archaeological evidence at the site.

Term: {term}
Sentence: {sentence}

The value of "context_label" MUST be exactly one of these five strings:
  present | absent | comparison | uncertain | irrelevant

Definitions:
- present:    the term refers to an actual find or evidence at the site
- absent:     the term is explicitly stated as not found or not applicable
- comparison: the term is used as a comparison, not a direct find
- uncertain:  the sentence is ambiguous or cannot be determined
- irrelevant: the mention has no chronological or archaeological value for this site

Respond with JSON only — no explanation, no extra text:
{{"context_label": "<present|absent|comparison|uncertain|irrelevant>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}
"""

_LLM_RETRY_PROMPT_TEMPLATE = """\
"{bad_label}" is not a valid label. Reply with ONE word only — no JSON, no punctuation:

present   (actual find or evidence at the site)
absent    (explicitly not found)
comparison (used as comparison, not a direct find)
uncertain (ambiguous)
irrelevant (no archaeological value for this site)

Term: {term}
Sentence: {sentence}
"""

# Batched version of the single-item prompt: classify MANY items in one call. Same rubric; the
# model echoes each item's index so results map back unambiguously (alignment is the key safety
# property — validated by count, with per-item fallback for any missing/invalid index).
_LLM_BATCH_PROMPT_TEMPLATE = """\
You are an archaeological text analyst. Terms were detected in a Roman-period excavation report from the Netherlands (ca. 12 BCE – 450 CE). Pottery types, construction phases, coin finds, and site features from this period are archaeologically relevant.
Your task: classify, for EACH numbered item below, whether its mention represents actual archaeological evidence at the site.

Each "context_label" MUST be exactly one of: present | absent | comparison | uncertain | irrelevant
Definitions:
- present:    the term refers to an actual find or evidence at the site
- absent:     the term is explicitly stated as not found or not applicable
- comparison: the term is used as a comparison, not a direct find
- uncertain:  the sentence is ambiguous or cannot be determined
- irrelevant: the mention has no chronological or archaeological value for this site

Items:
{items}

Respond with JSON ONLY (no markdown, no extra text): an object with a "results" array holding ONE object per item, echoing each item's index:
{{"results": [{{"index": <int>, "context_label": "<present|absent|comparison|uncertain|irrelevant>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}]}}
"""

# Structured-outputs schema for the Claude path: guarantees a valid results array with a valid
# label enum per item, so neither the index nor the JSON can be dropped/mangled (removes the main
# batching risk). Ignored by the cloud/ollama backends (they rely on prompt + best-effort parse).
_BATCH_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "index": {"type": "integer"},
        "context_label": {"type": "string",
                          "enum": ["present", "absent", "comparison", "uncertain", "irrelevant"]},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["index", "context_label", "confidence", "reasoning"],
    "additionalProperties": False,
}
_BATCH_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": _BATCH_ITEM_SCHEMA}},
    "required": ["results"],
    "additionalProperties": False,
}


def _classify_rule(record: Dict) -> Tuple[str, float]:
    """Deterministic context classifier — returns (label, confidence). Decision order matters:
    typology-code matches are `present` by definition; out-of-period centuries, historiographic
    and (finds-free) bibliographic sentences are `irrelevant`; then the ordered cue groups run
    absent → comparison → uncertain → present. An unmatched record returns `uncertain`/0.30, which
    is below the LLM threshold and so hands the record to the LLM fallback."""
    canonical = record.get("term_canonical", "")
    context = " ".join(record.get("context_sentence", "").split())

    # Typology code matches from the pottery vocabulary (csv_pottery_* patterns) are
    # definitionally present — appearing in a finds report is itself the evidence.
    # The prose-text rule chain is designed for running sentences, not table cells.
    if record.get("pattern_id", "").startswith("csv_pottery_"):
        return "present", 0.95

    if canonical in POST_ROMAN_CANONICALS:
        return "irrelevant", 0.95

    if canonical in PRE_ROMAN_CANONICALS:
        return "irrelevant", 0.92

    if _HISTORIOGRAPHIC_RE.search(context):
        return "irrelevant", 0.85

    # Only suppress as bibliographic if the sentence contains NO finds vocabulary.
    # Sentences like "Terra sigillata gevonden (Willems 2007a)" describe real finds
    # and must not be filtered out just because they include an in-text citation.
    if _BIBLIOGRAPHIC_RE.search(context) and not _FINDS_VOCAB_RE.search(context):
        return "irrelevant", 0.90

    for pattern, label, confidence in _RULES:
        if pattern.search(context):
            return label, confidence

    return "uncertain", 0.30


_LABEL_IN_JSON_RE = re.compile(
    r'"context_label"\s*:\s*"(present|absent|comparison|uncertain|irrelevant)"',
    re.IGNORECASE,
)

def _parse_llm_response(raw: str) -> Tuple[str, float, str]:
    """Parse a single-item LLM reply into (label, confidence, reasoning). Tolerant by design:
    if the JSON braces are missing or malformed, it tries to rescue the label with a regex before
    giving up, so a slightly-off reply still yields a usable classification."""
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
    except ValueError:
        # No closing brace — try to rescue label from partial output
        m = _LABEL_IN_JSON_RE.search(raw)
        if m:
            return m.group(1).lower(), 0.5, "rescued from partial JSON"
        raise
    try:
        parsed = json.loads(raw[start:end])
    except json.JSONDecodeError:
        # Malformed JSON — try to rescue label via regex
        m = _LABEL_IN_JSON_RE.search(raw)
        if m:
            return m.group(1).lower(), 0.5, "rescued from malformed JSON"
        raise
    label = parsed.get("context_label", "uncertain")
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    reasoning = parsed.get("reasoning", "")  # absent in retry responses
    return label, round(confidence, 2), reasoning


def _classify_llm(record: Dict) -> Tuple[str, float, str]:
    """Classify one record with the LLM (the per-record fallback / batch backstop). If the reply
    is not one of the five valid labels, it retries with a stricter one-word prompt and then maps
    common near-miss words (e.g. "presence"→present); only then does it give up to `uncertain`."""
    from src.llm_client import call_llm

    term = record.get("term_raw", "")
    sentence = " ".join(record.get("context_sentence", "").split())

    prompt = _LLM_PROMPT_TEMPLATE.format(term=term, sentence=sentence)
    raw = call_llm(prompt)

    try:
        label, confidence, reasoning = _parse_llm_response(raw)
    except (ValueError, KeyError, json.JSONDecodeError):
        return "uncertain", 0.30, f"LLM parse error: {raw[:120]}"

    if label not in _VALID_LABELS:
        bad_label = label
        retry_prompt = _LLM_RETRY_PROMPT_TEMPLATE.format(
            bad_label=bad_label, term=term, sentence=sentence
        )
        raw2 = call_llm(retry_prompt).strip().lower()
        match = re.search(r"\b(present|absent|comparison|uncertain|irrelevant)\b", raw2)
        if match:
            label = match.group(1)
        else:
            # Map common near-miss words before giving up
            _NEAR_MISS = {
                "relevant": "present", "presence": "present", "occurrence": "present",
                "found": "present", "exists": "present",
                "absent": "absent", "missing": "absent", "not found": "absent",
                "comparative": "comparison", "compared": "comparison",
                "unclear": "uncertain", "ambiguous": "uncertain",
                "not relevant": "irrelevant", "unrelated": "irrelevant",
            }
            mapped = next((v for k, v in _NEAR_MISS.items() if k in raw2), None)
            if mapped:
                label = mapped
            else:
                return "uncertain", 0.30, f"LLM retry gave no valid label: {raw2[:80]}"

    return label, confidence, reasoning


def _llm_batch_size() -> int:
    """Records classified per LLM call. config.LLM_BATCH_SIZE overrides (1 = one per record); else
    auto by backend — stronger/schema-guaranteed models batch bigger, weak ones stay small."""
    from config import LLM_BATCH_SIZE, LLM_PROVIDER
    if LLM_BATCH_SIZE:
        return max(1, LLM_BATCH_SIZE)
    if LLM_PROVIDER == "anthropic":
        return 30                      # Claude + JSON schema -> guaranteed-valid arrays
    if LLM_PROVIDER == "ollama":
        return 8                       # local, usually small/weak + num_ctx-bound
    from config import LLM_API_MODEL
    if any(t in (LLM_API_MODEL or "").lower() for t in ("1b", "3b", "8b")):
        return 10                      # small cloud models
    return 20                          # 70B / default cloud


def _parse_batch_results(raw: str) -> List[Dict]:
    """Pull the results array from a batched reply — accepts {"results": [...]} (schema/object form)
    or a bare [...] array; tolerates markdown fences. Returns [] on failure (caller falls back)."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
    try:                                            # object form: {"results": [...]}
        d = json.loads(s[s.index("{"): s.rindex("}") + 1])
        if isinstance(d, dict) and isinstance(d.get("results"), list):
            return d["results"]
    except (ValueError, json.JSONDecodeError):
        pass
    try:                                            # bare array form: [...]
        a = json.loads(s[s.index("["): s.rindex("]") + 1])
        return a if isinstance(a, list) else []
    except (ValueError, json.JSONDecodeError):
        return []


def _classify_llm_batch(subset: List[Dict]) -> List[Tuple[str, float, str]]:
    """Classify a batch of records in ONE call. Returns a list aligned to `subset`, each
    (label, confidence, reasoning). Results are mapped back by the echoed index; any item that is
    missing or has an invalid label falls back to the single-item _classify_llm (never worse than
    the per-record path — a failed batch just costs extra calls, not wrong data)."""
    from config import LLM_PROVIDER
    items = "\n".join(
        f'[{j}] Term: "{r.get("term_raw", "")}" | Sentence: "{" ".join(r.get("context_sentence", "").split())}"'
        for j, r in enumerate(subset))
    prompt = _LLM_BATCH_PROMPT_TEMPLATE.format(items=items)
    schema = _BATCH_SCHEMA if LLM_PROVIDER == "anthropic" else None
    by_index: Dict[int, Tuple[str, float, str]] = {}
    try:
        from src.llm_client import call_llm
        raw = call_llm(prompt, max_tokens=max(4096, len(subset) * 80), output_schema=schema)
        for o in _parse_batch_results(raw):
            try:
                idx = int(o.get("index"))
            except (TypeError, ValueError):
                continue
            label = str(o.get("context_label", "")).lower()
            if label in _VALID_LABELS:
                try:
                    conf = round(float(o.get("confidence", 0.5)), 2)
                except (TypeError, ValueError):
                    conf = 0.5
                by_index[idx] = (label, conf, str(o.get("reasoning", "")))
    except Exception:
        pass
    return [by_index.get(j) or _classify_llm(r) for j, r in enumerate(subset)]


def interpret_candidates(records: List[Dict], use_llm: bool = True) -> List[Dict]:
    """Layer 5 entry point: classify every record's context label. Runs the deterministic rule
    pass over all records, then sends only the low-confidence ones (< LLM_CONFIDENCE_THRESHOLD) to
    the LLM in batches. With `use_llm=False` it is purely rule-based. Writes `context_label`,
    `context_confidence`, `interpretation_method`, and `interpretation_reasoning`."""
    from config import LLM_CONFIDENCE_THRESHOLD

    total = len(records)
    # 1. Deterministic rule pass for ALL records; collect the low-confidence ones for the LLM.
    decided = []   # per record: [label, confidence, method, reasoning]
    todo = []      # indices needing the LLM fallback
    for record in records:
        label, confidence = _classify_rule(record)
        decided.append([label, round(confidence, 2), "rule", ""])
        if use_llm and confidence < LLM_CONFIDENCE_THRESHOLD:
            todo.append(len(decided) - 1)

    # 2. LLM fallback for the low-confidence records, in batches (one call per B records).
    B = _llm_batch_size()
    n_batches = (len(todo) + B - 1) // B if todo else 0
    print(f"[Layer 5] Interpreting {total} records (LLM={'on' if use_llm else 'off'}); "
          f"{len(todo)} need LLM, batch size {B} -> {n_batches} call(s)")
    for bi, k in enumerate(range(0, len(todo), B), start=1):
        idx_chunk = todo[k:k + B]
        results = _classify_llm_batch([records[x] for x in idx_chunk])
        for pos, i in enumerate(idx_chunk):
            label, confidence, reasoning = results[pos]
            decided[i] = [label, round(confidence, 2), "llm", reasoning]
        print(f"[Layer 5] batch {bi}/{n_batches}: {len(idx_chunk)} records "
              f"({min(k + B, len(todo))}/{len(todo)} done)")

    # 3. Assemble output records.
    result = []
    for record, (label, confidence, method, reasoning) in zip(records, decided):
        out = dict(record)
        out["context_label"] = label
        out["context_confidence"] = confidence
        out["interpretation_method"] = method
        out["interpretation_reasoning"] = reasoning
        result.append(out)
    print(f"[Layer 5] Done. {len(todo)} records used LLM fallback in {n_batches} batch call(s).")
    return result

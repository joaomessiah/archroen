"""Layer 3 (detection) — regex candidate detection.

Scans each chunk with the generated pattern files (pottery types, chronology periods,
century references) and emits a candidate per match with its surrounding context
window. Also merges dual typologies (e.g. "Lamboglia 2/Dressel 6A") and builds the
typology-code -> date lookup used downstream.
"""
import re
from typing import List, Dict

# Matches a real sentence boundary: period followed by whitespace and an uppercase
# letter (or opening paren). Guards against false breaks on:
#   - Single-letter initials: "J. Smith"  (J is uppercase → lookbehind [A-Z] blocks it)
#   - Numbered list items:   "3. Titel"   (3 is digit   → lookbehind \d blocks it)
# Note: "n.Chr." and "v.Chr." are already safe because their internal periods have no
# whitespace between the period and the next character ("Chr."), so the [ \t\r\n]+
# requirement is never satisfied there.
_SENT_BOUNDARY_RE = re.compile(r'(?<![A-Z\d])\.[ \t\r\n]+(?=[A-Z(])')


def _find_sentence_start(text: str, pos: int) -> int:
    """Return the char index where the sentence containing pos begins."""
    boundaries = [m.end() for m in _SENT_BOUNDARY_RE.finditer(text, 0, pos)]
    return boundaries[-1] if boundaries else 0


def _find_sentence_end(text: str, pos: int) -> int:
    """Return the char index just after the period that ends the sentence."""
    m = _SENT_BOUNDARY_RE.search(text, pos)
    return (m.start() + 1) if m else len(text)


def _compile_patterns(pattern_specs: List[Dict]) -> List[Dict]:
    """Pre-compile each JSON pattern spec's regex (case-insensitive) once, carrying its
    metadata (canonical hint, date range, labels) alongside, so the per-chunk scan below
    doesn't recompile on every chunk."""
    compiled = []
    for spec in pattern_specs:
        compiled.append({
            "pattern_id": spec["pattern_id"],
            "canonical_hint": spec.get("canonical_hint"),
            "description": spec.get("description", ""),
            "chronology_id": spec.get("chronology_id"),
            "phase_code": spec.get("phase_code"),
            "preferred_label": spec.get("preferred_label"),
            "date_start": spec.get("date_start"),
            "date_end": spec.get("date_end"),
            "regex": re.compile(spec["regex"], re.IGNORECASE),
        })
    return compiled


def _extract_context(text: str, start: int, end: int, window_chars: int) -> Dict[str, str]:
    """Return two views of the text around a match: a fixed ±`window_chars` character window
    (for the LLM / date extraction) and the single enclosing sentence (for the rule layer)."""
    left = max(0, start - window_chars)
    right = min(len(text), end + window_chars)
    context_window = text[left:right].strip()

    sentence_start = _find_sentence_start(text, start)
    sentence_end = _find_sentence_end(text, end)
    context_sentence = text[sentence_start:sentence_end].strip()

    return {
        "context_window": context_window,
        "context_sentence": context_sentence,
    }


def _find_page(page_breaks: list, char_offset: int) -> int:
    page = page_breaks[0][0]
    for page_no, offset in page_breaks:
        if offset <= char_offset:
            page = page_no
        else:
            break
    return page


_TYPOLOGY_PREFIX = "csv_pottery_"


def _canon_code(code: str) -> str:
    """Normalize a typology code to the UPPER_UNDERSCORE form used by canonical_hint."""
    return re.sub(r'[^A-Za-z0-9]+', '_', code).strip('_').upper()


def build_code_date_lookup(csv_path) -> Dict[str, tuple]:
    """Build {CANON_CODE: (date_start, date_end, pot_name_en, typology_code)} from a vocab CSV.

    Indexed under the canon of the typology_code AND of every '|'-separated abbreviation, so an
    abbreviated reference ("Consp. 11") resolves to the canonical entry ("Conspectus 11"). The
    value carries the full typology_code so callers can display/normalise to it.

    Resolve dual components against the master (authoritative per-code dates) — the
    derived Normalized/pattern files can be stale (e.g. "Dressel 2" carrying the
    "Dressel 2-4" date).
    """
    import csv as _csv
    out: Dict[str, tuple] = {}
    parsed = []
    with open(csv_path, encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            code = (r.get("typology_code") or "").strip()
            if not code:
                continue
            try:
                ds, de = int(r["date_start"]), int(r["date_end"])
            except (TypeError, ValueError, KeyError):
                continue
            # value carries the FULL typology_code so callers can display/normalise to it
            val = (ds, de, (r.get("pot_name_en") or "").strip(), code)
            out[_canon_code(code)] = val
            parsed.append((val, r.get("abbreviations") or ""))
    # Also index every '|'-separated abbreviation ("Consp. 11", "Alz. 1", …) so an abbreviated
    # reference resolves to the canonical entry. setdefault => real typology codes are never shadowed.
    for val, abbr in parsed:
        for ab in abbr.split("|"):
            ab = ab.strip()
            if ab:
                out.setdefault(_canon_code(ab), val)
    return out


def merge_dual_typologies(candidates: List[Dict], chunks: List[Dict],
                          code_dates: Dict[str, tuple]) -> List[Dict]:
    """Merge dual typology references — "A/B" or "A-N" — into one candidate.

    A report writing "Lamboglia 2/Dressel 6A" or "Dressel 7-11" means "the pot is
    either A or B" — a single entity, not two. We keep the FULL string as term_raw
    (so it becomes the typology value), date it from the first component that has a
    date (else the second, …), and keep the first resolved component's descriptive
    name. The "/" second-component candidate is dropped.

    Only the "-" forms that join two type *numbers* (e.g. "Dressel 7-11") are
    treated as duals; a trailing letter variant ("Dressel 1B") or an existing
    grouped master entry is left untouched.

    ``code_dates`` is {CANON_CODE: (date_start, date_end, pot_name_en)} — see
    build_code_date_lookup; build it from the master so component dates are correct.
    """
    def resolve(component_codes):
        for code in component_codes:
            hit = code_dates.get(_canon_code(code))
            if hit is not None:
                ds, de, label = hit[:3]
                return ds, de, _canon_code(code), label
        return None

    cmap = {c["chunk_id"]: c["text"] for c in chunks}
    is_typo = lambda c: str(c.get("pattern_id", "")).startswith(_TYPOLOGY_PREFIX)

    by_chunk: Dict[str, List[Dict]] = {}
    other = []
    for c in candidates:
        if is_typo(c):
            by_chunk.setdefault(c["chunk_id"], []).append(c)
        else:
            other.append(c)

    merged = []
    for chunk_id, group in by_chunk.items():
        text = cmap.get(chunk_id, "")
        group.sort(key=lambda c: c.get("start_char") or 0)
        suppressed = set()
        # Suppress a typology code whose span is contained within a longer code at an
        # overlapping position — e.g. bare "Dragendorff 18" (csv_pottery_0333) sitting
        # inside "Dragendorff 18/31" (csv_pottery_0334). The longer, more specific match
        # is the real one; the prefix sub-match is a spurious duplicate.
        for a in group:
            sa, ea = a["start_char"], a["end_char"]
            for b in group:
                if a is b:
                    continue
                sb, eb = b["start_char"], b["end_char"]
                if sb <= sa and eb >= ea and (eb - sb) > (ea - sa):
                    suppressed.add(id(a))
                    break
        for idx, c in enumerate(group):
            if id(c) in suppressed:
                continue
            s, e = c["start_char"], c["end_char"]
            term = (c.get("term_raw") or "").strip()
            components = None
            new_end = e

            nxt = group[idx + 1] if idx + 1 < len(group) else None
            if nxt is not None and re.fullmatch(r"\s*\(\s*", text[e:nxt["start_char"]] or ""):
                # "X (Y…)" — Y is a parenthetical SYNONYM of X (same find under another
                # classification, e.g. "Consp. 11 (Haltern 1b/Service Ia)"). Keep the
                # narrowest-dated of the two (most precise) and drop the other, so one
                # find yields one row instead of two.
                def _width(cd):
                    ds, de = cd.get("date_start"), cd.get("date_end")
                    return (de - ds) if (ds is not None and de is not None) else 10 ** 9
                keep, drop = (c, nxt) if _width(c) <= _width(nxt) else (nxt, c)
                suppressed.add(id(drop))
                if id(c) == id(keep):
                    merged.append(c)   # else `keep` is nxt and is appended when reached
                continue
            if nxt is not None and re.fullmatch(r"\s*/\s*", text[e:nxt["start_char"]] or ""):
                # "A / B" — two adjacent codes joined by a slash
                new_end = nxt["end_char"]
                components = [term, (nxt.get("term_raw") or "").strip()]
                suppressed.add(id(nxt))
            else:
                # "A-N" — code followed by dash + a bare number (not a letter variant)
                m = re.match(r"-\s*(\d+)", text[e:e + 8])
                if m:
                    new_end = e + m.end()
                    family = term.rsplit(" ", 1)[0] if " " in term else term
                    components = [term, f"{family} {m.group(1)}"]

            if components is None:
                merged.append(c)
                continue

            c = dict(c)
            c["term_raw"] = text[s:new_end]
            c["end_char"] = new_end
            res = resolve(components)
            if res is not None:
                c["date_start"], c["date_end"], c["canonical_hint"], c["preferred_label"] = res
            merged.append(c)

    # Expand continuation type numbers in a typology enumeration:
    # "Dragendorff 18/31, 33, 37" or "Drag 29 en 37" list several types but only the
    # first carries the family name. For each typology code, walk forward over
    # ", <n>" / "en <n>" / "and <n>" items and emit a sibling "<family> <n>" — but only
    # while each resolves to a known master type, so a trailing non-type token stops it.
    _CONT_RE = re.compile(r"(?:\s*,\s*|\s+(?:en|and)\s+)(\d+(?:\s*/\s*\d+)?[A-Za-z]?)")
    # Abbreviated family names → the full family used as the master code key, so a
    # continuation off an abbreviation ("Drag 29 en 37") still resolves "Dragendorff 37".
    _FAMILY_ABBREV = {"drag": "Dragendorff"}
    extra = []
    for c in list(merged):
        if not is_typo(c):
            continue
        term = (c.get("term_raw") or "").strip()
        fam_m = re.match(r"^(.*?)[\s.]*\d", term)
        if not fam_m or not fam_m.group(1).strip():
            continue
        family = fam_m.group(1).strip()
        fam_full = _FAMILY_ABBREV.get(family.lower().rstrip("."), family)
        text = cmap.get(c["chunk_id"], "")
        pos = c["end_char"]
        while True:
            m = _CONT_RE.match(text, pos)
            if not m:
                break
            num = re.sub(r"\s+", "", m.group(1))
            res = resolve([f"{fam_full} {num}"])
            if res is None:
                break
            nc = dict(c)
            nc["term_raw"] = f"{fam_full} {num}"
            nc["start_char"], nc["end_char"] = m.start(1), m.end()
            nc["date_start"], nc["date_end"], nc["canonical_hint"], nc["preferred_label"] = res
            extra.append(nc)
            pos = m.end()
    merged.extend(extra)

    return other + merged


def detect_candidates(chunks: List[Dict], pattern_specs: List[Dict], window_chars: int, report_id: str = "") -> List[Dict]:
    """Scan every chunk with every compiled pattern and emit one candidate per match, carrying
    its context window, page, and char span. Finally deduplicate by *section-absolute* span so a
    match that falls in the overlap of two adjacent chunks (CHUNK_OVERLAP) is counted only once."""
    compiled_patterns = _compile_patterns(pattern_specs)
    candidates = []

    for chunk in chunks:
        text = chunk["text"]

        for spec in compiled_patterns:
            for match in spec["regex"].finditer(text):
                ctx = _extract_context(text, match.start(), match.end(), window_chars)
                candidates.append({
                    "report_id": report_id,
                    "chunk_id": chunk["chunk_id"],
                    "section_id": chunk["section_id"],
                    "section_title": chunk["section_title"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "page": _find_page(chunk["page_breaks"], match.start()),
                    "term_raw": match.group(0),
                    "match_type": "regex",
                    "pattern_id": spec["pattern_id"],
                    "canonical_hint": spec["canonical_hint"],
                    "chronology_id": spec["chronology_id"],
                    "phase_code": spec["phase_code"],
                    "preferred_label": spec["preferred_label"],
                    "date_start": spec["date_start"],
                    "date_end": spec["date_end"],
                    "start_char": match.start(),
                    "end_char": match.end(),
                    "text_offset_start": chunk.get("text_offset_start", 0),
                    **ctx,
                })

    deduped = []
    seen = set()
    for c in candidates:
        # Use section-absolute position so the same span detected in two overlapping
        # chunks (due to CHUNK_OVERLAP) is counted only once.
        abs_start = c.get("text_offset_start", 0) + c["start_char"]
        abs_end   = c.get("text_offset_start", 0) + c["end_char"]
        key = (c["section_id"], abs_start, abs_end, c["term_raw"].lower(), c["canonical_hint"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped

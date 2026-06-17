"""Layer 3 (structure) — sectioning and chunking.

Splits cleaned page text into logical sections by heading detection, then breaks
sections into overlapping character chunks (CHUNK_SIZE / CHUNK_OVERLAP) that bound
the context window used by detection and the LLM layers.
"""
import re
from typing import List, Dict, Tuple

SECTION_HEADING_RE = re.compile(
    r"^(?:"
    # English headings
    r"abstract|introduction|summary|methods?|results?|conclusion|discussion"
    r"|findings?|dating|context|section|stratigraphy|pottery|features|finds"
    r"|references?|appendix|bibliography"
    r"|"
    # Dutch headings (common in Dutch grey-literature excavation reports)
    r"samenvatting|inleiding|methode[n]?|resultaten|conclusie[s]?|discussie"
    r"|datering[en]?|sporen|vondsten|aardewerk|keramiek|aanbevelingen"
    r"|bijlage[n]?|literatuur|vindplaats|grondsporen|stratigrafie"
    r"|opgravingsgeschiedenis|onderzoeksgebied|geologie|bodem"
    r"|bewoning|fasering|interpretatie|context|periode|chronologie"
    r"|"
    # Numbered headings: "1.", "2.1.", "1.2.3." etc. (very common in Dutch reports).
    # Negative lookahead (?!\d) prevents matching decimal numbers like "2.0" or "0.7"
    # (which would be split as "2." + "0" by the greedy \d+ engine).
    r"\d+(?:\.\d+)*\.(?!\d)"
    r")\b",
    re.IGNORECASE,
)

# Spaced-capital headings used in old bulletin-style reports, where each find is
# introduced by a place name in letter-spaced capitals on its own line
# ("A M B I J.", "E I J G E L S H O V E N.", "V R A A G ."). Treating these as
# section boundaries keeps each entry's date context from bleeding into the next
# unrelated entry. Anchored to the whole line, so a line that merely starts with
# spaced caps but continues in prose is not matched. Requires ≥3 single letters,
# which avoids initials ("A. J.") and other incidental capitals.
SPACED_CAPS_HEADING_RE = re.compile(
    r"^(?:[A-ZÀ-ÖØ-Þ]\s+){2,}[A-ZÀ-ÖØ-Þ]\s*\.?\s*$"
)

# Inline site headings in old bulletin reports: a place name followed by a Dutch
# province abbreviation in parentheses, then the entry text on the SAME line
# ("Houten (Utr.). Bij het graven …", "Kerkrade (L.). Van 3 April …"). The place
# name is the site; the remainder of the line is body text.
_NL_PROVINCES = {
    "L", "UTR", "OV", "GLD", "NH", "ZH", "NB", "GR", "FR", "DR", "ZL", "FL", "U",
}
INLINE_SITE_HEADING_RE = re.compile(
    r"^([A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)*)"  # place name
    r"\s*\(([A-Za-z.]{1,5})\)\.\s*"                                   # (Prov.).
    r"(.*)$"                                                          # rest of line
)

# Place-name section headings in chronicle BULLETINS ("De Maasgouw", "Archeologisch
# Nieuws", "Opgravings-Nieuws"): one PDF reports many sites, each introduced by a
# place name — usually ALL CAPS ("GULPEN.", "UBACH OVER WORMS.") or just the place on
# its own line ("Nieuwenhagen."). A gazetteer keeps this precise (a place mid-prose
# like "…te Maastricht. De volgende…" is not split unless it is ALL CAPS / stands alone).
_PLACE_GAZETTEER = sorted({
    "heerlen", "maastricht", "gulpen", "hoensbroek", "eygelshoven", "eysden",
    "nieuwenhagen", "roermond", "venlo", "lottum", "limbricht", "schinveld",
    "sint geertruid", "ubach over worms", "cadier en keer", "illikhoven", "roosteren",
    "illikhoven-roosteren", "bemelen", "schinnen", "merkelbeek", "voerendaal", "kerkrade",
    "simpelveld", "rijswijk", "houten", "vechten", "rimburg", "nijmegen", "esch",
    "beek en donk", "baarlo", "heel", "cuyk", "geysteren", "stein", "margraten",
    "kampen", "leiden", "jutphaas", "elsloo", "hapert", "gemonde", "ubachsberg",
    "wanssum", "grevenbicht", "steensel", "zaltbommel", "westervoort", "gramsbergen",
    "brunssum", "meerssen", "valkenburg", "thorn", "weert", "sittard", "geleen",
    "beek", "thulle", "groenstraat", "coriovallum", "lutjewierum", "noordoostpolder",
}, key=len, reverse=True)
_PLACE_HEADING_RE = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _PLACE_GAZETTEER) + r")"
    r"\s*(?:\(([A-Za-z.]{1,6})\))?\s*[.:]\s*(.*)$",
    re.IGNORECASE,
)


def _place_heading(stripped: str):
    """Return (site_name, rest_of_line) if the line is a bulletin place heading, else None.
    Accept only when the place is ALL CAPS, carries a province, or stands alone — so a
    place name occurring mid-sentence does not wrongly start a new section."""
    m = _PLACE_HEADING_RE.match(stripped)
    if not m:
        return None
    place, prov, rest = m.group(1), m.group(2), m.group(3)
    if place.isupper() or prov or not rest.strip():
        return place.title(), rest.strip()
    return None


def _valid_province(token: str) -> bool:
    return token.replace(".", "").replace(" ", "").upper() in _NL_PROVINCES


# Letter-spaced headings that are bulletin SECTION labels, not place names — they must
# not be taken as a site (e.g. "B E R I C H T E N." = "News", not a findspot).
_NON_PLACE_HEADINGS = {
    "berichten", "mededelingen", "inhoud", "vondstmeldingen", "kroniek",
    "literatuur", "boekbespreking", "varia", "register", "colofon", "redactie",
}


def _collapse_spaced_caps(title: str) -> str:
    """"A M B I J." → "Ambij"; "E I J G E L S H O V E N." → "Eijgelshoven"."""
    t = title.strip().rstrip(".").strip()
    tokens = t.split()
    if len(tokens) >= 3 and all(len(tok) == 1 and tok.isalpha() for tok in tokens):
        collapsed = "".join(tokens).capitalize()
        if collapsed.lower() in _NON_PLACE_HEADINGS:
            return ""
        return collapsed
    return ""


def _is_keyword_heading(stripped: str) -> bool:
    """A keyword/numbered section heading — but NOT a content line that merely starts
    with a heading word (e.g. "AARDEWERK: terra sigillata, Belgisch aardewerk, …").
    A real heading is short and carries no list/sentence after the keyword.
    """
    m = SECTION_HEADING_RE.match(stripped)
    if not m:
        return False
    rest = stripped[m.end():].strip(" .:-—")
    if "," in rest or len(rest) > 30:
        return False
    return True


# A flattened inventory/finds table renders each row's cells on their own lines, so a
# material+period cell ("aardewerk Romeinse tijd") sits between the bare find-number
# line above it and the bare count line below it. Such a cell can collide with a
# section-heading keyword (aardewerk/vondsten/datering …) and be wrongly consumed as a
# heading, deleting the find. Bare-integer neighbours on BOTH sides mark it as a table
# cell, not a heading — a generic, language-agnostic signal (prose headings are flanked
# by text/blank lines, never by two bare numbers).
_BARE_INT_RE = re.compile(r"\d{1,4}")


def _is_numeric_cell(line: str) -> bool:
    """A line of one or two bare integers — a flattened table's number cells. Two
    integers occur when a row's count merges with the next row's find-number
    ("1 21" = count 1, next find 21), which is common in these extractions."""
    toks = line.split()
    return 1 <= len(toks) <= 2 and all(_BARE_INT_RE.fullmatch(t) for t in toks)


def _is_finds_table_cell(prev_line: str, next_line: str) -> bool:
    return _is_numeric_cell(prev_line.strip()) and _is_numeric_cell(next_line.strip())


def _compute_page_breaks(parts: List[str], page_part_indices: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Convert (page_no, part_index) pairs to (page_no, char_offset) pairs after joining parts with newlines."""
    offset = 0
    part_offsets = []
    for part in parts:
        part_offsets.append(offset)
        offset += len(part) + 1  # +1 for the joining \n

    return [(page_no, part_offsets[idx]) for page_no, idx in page_part_indices]


def _chunk_page_breaks(
    section_breaks: List[Tuple[int, int]], chunk_start: int, chunk_size: int
) -> List[Tuple[int, int]]:
    """Return page_breaks relative to a chunk's start offset within the section text."""
    active_page = section_breaks[0][0]
    for page_no, offset in section_breaks:
        if offset <= chunk_start:
            active_page = page_no

    result = [(active_page, 0)]
    for page_no, offset in section_breaks:
        rel = offset - chunk_start
        if 0 < rel < chunk_size:
            result.append((page_no, rel))

    return result


def split_into_sections(pages: List[Dict]) -> List[Dict]:
    """Split the flattened page lines into sections at heading boundaries, tracking page breaks.

    Heading recognisers are tried in priority order per line: inline site heading
    ("Houten (Utr.). …") → bulletin place-name heading ("GULPEN. …") → spaced-caps / keyword
    heading. Place/site headings also set the section's `site_name`. A keyword heading wedged
    between two bare-integer lines is treated as a finds-table cell, not a heading, so a find row
    is never deleted."""
    sections = []
    counter = 1
    current = {
        "section_id": "section_1",
        "section_title": "Unlabeled Section",
        "site_name": "",
        "page_start": None,
        "page_end": None,
        "_parts": [],
        "_page_part_indices": [],
        "_current_page": None,
    }

    def _start_section(title: str, site_name: str, page_no: int, first_part: str = "") -> Dict:
        """Open a fresh section dict (incrementing the id counter), optionally seeded with the
        heading line's trailing body text as its first content part."""
        nonlocal counter
        counter += 1
        sec = {
            "section_id": f"section_{counter}",
            "section_title": title,
            "site_name": site_name,
            "page_start": page_no,
            "page_end": page_no,
            "_parts": [first_part] if first_part else [],
            "_page_part_indices": [(page_no, 0)],
            "_current_page": page_no,
        }
        return sec

    # Flatten to non-empty lines carrying their page number, so heading detection can
    # inspect neighbouring lines (a finds-table cell sits between bare-integer lines).
    flat = [(page["page_number"], s)
            for page in pages
            for s in (ln.strip() for ln in page["text"].split("\n")) if s]

    for idx, (page_no, stripped) in enumerate(flat):
            prev_line = flat[idx - 1][1] if idx > 0 else ""
            next_line = flat[idx + 1][1] if idx + 1 < len(flat) else ""

            # Inline site heading ("Houten (Utr.). Bij het graven …"): the place name
            # is the site; the rest of the line stays as body text.
            inline = INLINE_SITE_HEADING_RE.match(stripped)
            if inline and _valid_province(inline.group(2)):
                if current["_parts"]:
                    sections.append(_finalize_section(current))
                current = _start_section(inline.group(1).strip(), inline.group(1).strip(),
                                         page_no, inline.group(3).strip())
                continue

            # Bulletin place-name heading ("GULPEN. In een terrein …", "Nieuwenhagen.")
            place_h = _place_heading(stripped)
            if place_h:
                site, body = place_h
                if current["_parts"]:
                    sections.append(_finalize_section(current))
                current = _start_section(site, site, page_no, body)
                continue

            is_spaced = SPACED_CAPS_HEADING_RE.match(stripped)
            # A keyword heading wedged between two bare-integer lines is a finds-table
            # cell (find-number / cell / count), not a section heading — keep it as body.
            is_keyword = (_is_keyword_heading(stripped)
                          and not _is_finds_table_cell(prev_line, next_line))
            if is_spaced or is_keyword:
                if current["_parts"]:
                    sections.append(_finalize_section(current))
                site = _collapse_spaced_caps(stripped) if is_spaced else ""
                current = _start_section(stripped, site, page_no)
                continue

            if current["page_start"] is None:
                current["page_start"] = page_no
                current["_page_part_indices"] = [(page_no, 0)]
                current["_current_page"] = page_no
            elif page_no != current["_current_page"]:
                current["_page_part_indices"].append((page_no, len(current["_parts"])))
                current["_current_page"] = page_no

            current["page_end"] = page_no
            current["_parts"].append(stripped)

    if current["_parts"]:
        sections.append(_finalize_section(current))

    return sections


def _finalize_section(current: Dict) -> Dict:
    parts = current["_parts"]
    page_breaks = _compute_page_breaks(parts, current["_page_part_indices"])
    return {
        "section_id": current["section_id"],
        "section_title": current["section_title"],
        "site_name": current.get("site_name", ""),
        "page_start": current["page_start"],
        "page_end": current["page_end"],
        "page_breaks": page_breaks,
        "text": "\n".join(parts).strip(),
    }


def chunk_sections(sections: List[Dict], chunk_size: int, overlap: int) -> List[Dict]:
    """Break each section into overlapping character chunks. A section that fits in `chunk_size`
    is emitted whole (`is_full_section=True`) so short bulletin entries keep one chronological
    frame; longer sections are windowed with `overlap` carried between windows. Page-break offsets
    are recomputed relative to each chunk's start."""
    chunks = []
    chunk_counter = 1

    for section in sections:
        text = section["text"]
        breaks = section["page_breaks"]

        if len(text) <= chunk_size:
            chunks.append({
                "chunk_id": f"chunk_{chunk_counter}",
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "site_name": section.get("site_name", ""),
                "page_start": section["page_start"],
                "page_end": section["page_end"],
                "page_breaks": breaks,
                "text": text,
                "text_offset_start": 0,
                # The chunk holds the whole section: a self-contained unit. For
                # short bulletin entries this lets date context span the entire
                # entry (one site = one chronological frame) instead of ±2 sentences.
                "is_full_section": True,
            })
            chunk_counter += 1
            continue

        step = max(1, chunk_size - overlap)
        for start in range(0, len(text), step):
            part = text[start:start + chunk_size].strip()
            if not part:
                continue
            chunks.append({
                "chunk_id": f"chunk_{chunk_counter}",
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "site_name": section.get("site_name", ""),
                "page_start": section["page_start"],
                "page_end": section["page_end"],
                "page_breaks": _chunk_page_breaks(breaks, start, chunk_size),
                "text": part,
                "text_offset_start": start,
                "is_full_section": False,
            })
            chunk_counter += 1
            if start + chunk_size >= len(text):
                break

    return chunks

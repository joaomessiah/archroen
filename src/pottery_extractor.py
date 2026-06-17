"""Layer 3b — trigger-based pottery extraction.

Catches pottery mentions that are not in the known pattern list. Trigger words
(EN/NL/LA, from pottery_triggers.json) flag candidate sentences, which are then
confirmed by surrounding cues and an optional LLM fallback. Also extracts figure
plates of vessel drawings labelled only by find/catalogue numbers.
"""
import re
import json
from typing import Dict, List, Optional, Set, Tuple


# Naming-convention patterns applied in order; first match wins.
# These catch the most common structured pottery names without needing the LLM.
_NAMING_PATTERNS: List[re.Pattern] = [
    # Typology codes: "Drag. 37", "Stuart 201", "Dressel 20", "Niederbieber 89"
    # [\s\-]* handles OCR line-breaks and optional hyphens between name and number.
    re.compile(
        r'\b((?:Drag(?:endorff)?|Stuart|Niederbieber|Nb|Hofheim|Dressel'
        r'|Haltern|Loeschcke|R[ií]tterling|Ludowici|Alzei|Gose|Oelmann'
        r'|Déchelette|Walters|Bet)\.?[\s\-]*(?:type\s+)?\d+[a-zA-Z]?)\b',
        re.IGNORECASE,
    ),
    # "Samian ware", "Black-burnished ware", "Gallo-Belgic ware", "Oxford ware", etc.
    # Only "ware/wares" — "pottery/ceramics" are too generic and cause false positives.
    # Allows:
    #   - Simple two-word names:          "Fine ware"   [A-Z][a-z]+ \s+ ware
    #   - Hyphenated compound prefix:     "Gallo-Belgic ware"  [A-Z][a-z]+-[A-Z][a-z]+ \s+ ware
    #   - Two capitalised words:          "North African ware"  [A-Z][a-z]+ \s+ [A-Z][a-z]+ \s+ ware
    #   - Lowercase qualifier + ware:     "Pompeian red ware"  captured by the optional
    #                                      (?:\s+[a-z]+)? group before "ware"
    re.compile(
        r'\b('
        r'[A-Z][a-z]+(?:-[A-Z][a-z]+)*'           # "Gallo-Belgic" or "Fine" or "Pompeian"
        r'(?:\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)*)*'   # optional extra capitalised words
        r'(?:\s+[a-z]+)*'                           # optional lowercase qualifier(s) ("red", "burnished")
        r'\s+(?:ware|wares)'
        r')\b',
    ),
    # Dutch surface treatment + aardewerk: "gladwandig aardewerk", "ruwwandig aardewerk"
    re.compile(r'\b((?:glad|ruw|grijs|rood|wit)wandig\s+aardewerk)\b', re.IGNORECASE),
    # Surface-treatment ware named WITHOUT "aardewerk", optionally with a colour and an
    # adjective inflection: "rode ruwwandige (fragmenten)", "wit gladwandig (fragment)".
    re.compile(r'\b((?:(?:rode|rood|witte|wit|grijze|grijs|bruine|bruin)\s+)?'
               r'(?:glad|ruw|grijs|rood|wit)wandige?)\b', re.IGNORECASE),
    # Painted/decorated vessel: "geverfde beker", "painted cups" (specific finds; the bare
    # vessel word stays out of prose). NL (geverfd/beschilderd) + EN (painted/decorated).
    re.compile(r'\b((?:geverfd|beschilderd|painted|decorated)\w*\s+'
               r'(?:beker\w*|cups?|beakers?|bowls?|jugs?|jars?|plates?|dishes?))\b', re.IGNORECASE),
    # Dutch origin / surface-treatment wares + aardewerk: "Belgisch aardewerk" (Belgic),
    # "gevernist aardewerk" (varnished). Period adjectives (Romeins, Middeleeuws) are
    # deliberately excluded — those mark date, not a ware, so they stay bare "aardewerk".
    re.compile(r'\b((?:Belgisch|gevernist|geverfd|gesmookt|gepolijst)\s+aardewerk)\b', re.IGNORECASE),
    # Handmade / native pottery: "handgevormd inheems aardewerk", "inheems aardewerk"
    re.compile(r'\b(handgevormd\s+(?:inheems\s+)?aardewerk)\b', re.IGNORECASE),
    re.compile(r'\b(inheems\s+aardewerk)\b', re.IGNORECASE),
    # Standalone vessel-type names that are unambiguous on their own
    re.compile(r'\b(doli(?:um|a)|mortari(?:um|a)|amphorae?|arretin[ae])\b', re.IGNORECASE),
    # Maker-stamped sherd: "scherf met het stempel" — a specific, datable find.
    # Bare "scherf"/"scherven" stay rejected (generic) to avoid prose over-extraction.
    re.compile(r'\b(scherf|scherven)\s+met\s+(?:het\s+|een\s+)?stempel\b', re.IGNORECASE),
    # English handmade / native pottery (Dutch equivalents "handgevormd aardewerk" /
    # "inheems aardewerk" are handled by the patterns above; these cover English reports)
    re.compile(r'\b((?:hand-?made|native)\s+(?:\w+\s+)?pottery)\b', re.IGNORECASE),
    # "Form 37", "Type IIa", "Vorm 5" — before terra sigillata so specific codes win
    re.compile(r'\b((?:Form|Type|Vorm)\s+[A-Z]{0,2}\d+[a-zA-Z]?)\b', re.IGNORECASE),
    # "terra sigillata/nigra/rubra" optionally followed by an ORIGIN adjective, which in
    # these reports is always Capitalised ("Zuid-Gallisch", "Argonne", "Italische") — the
    # (?-i:[A-Z]) keeps case-sensitivity for that first letter even though the rest of the
    # pattern is case-insensitive. This stops the trailing slot from swallowing lowercase
    # Dutch words that merely follow the ware in prose ("terra nigra blijft/gaat/vormen",
    # "terra rubra vroeg") and turning a discussion mention into a garbage name.
    re.compile(
        r'\b(terra\s+(?:sigillata|nigra|rubra)'
        r'(?:\s+(?-i:[A-Z])[A-Za-z-]+(?:isch|ais|aine|ese|ensis)?)?)\b',
        re.IGNORECASE,
    ),
    # Dutch compound wares: "Mayen-aardewerk", "Eifel-keramiek"
    re.compile(r'\b([A-Z][a-z]+-(?:aardewerk|keramiek))\b'),
]

_LLM_PROMPT = """\
You are an archaeological text analyst. Read the sentence and extract any specific pottery type names mentioned.
A pottery type name is a proper noun or technical term that identifies a specific ware, form, or fabric.
Generic words like "pottery", "sherds", "aardewerk", "scherven", "keramiek" are NOT type names.

Return ONLY a JSON array of strings. If no specific pottery type name is present, return [].

Sentence: {sentence}
"""


# Dutch nominal compounds glue a generic tail onto a ware/vessel word with no space
# ("wrijfschaalfragmenten", "dekselfragmenten", "terra sigillatascherven"). \b then
# fails right after the trigger, so the find is never inspected. This optional tail
# lets the trigger still fire on the compound; _strip_compound_tail then normalises
# the extracted name back to the bare term.
_COMPOUND_TAIL = r'(?:fragment(?:en)?|scherf|scherven|stuk(?:ken)?|rest(?:en)?|materiaal)'
_COMPOUND_TAIL_RE = re.compile(_COMPOUND_TAIL + r'$', re.IGNORECASE)


def _strip_compound_tail(name: str) -> str:
    return _COMPOUND_TAIL_RE.sub('', name).strip()


def _build_trigger_regex(triggers: List[Dict]) -> re.Pattern:
    sorted_triggers = sorted(triggers, key=lambda t: len(t["trigger"]), reverse=True)
    # Spaces in multi-word triggers ("terra sigillata") become \s+ so an OCR line-break
    # between the words ("terra\nrubra") still matches.
    parts = [re.escape(t["trigger"]).replace(r"\ ", " ").replace(" ", r"\s+")
             for t in sorted_triggers]
    return re.compile(r'\b(?:' + '|'.join(parts) + r')' + _COMPOUND_TAIL + r'?\b', re.IGNORECASE)


# Sentences longer than this are considered pathological (e.g. no sentence boundaries
# in table content). Beyond this threshold, fall back to the line containing the trigger.
_MAX_POTTERY_SENTENCE = 300


def _extract_sentence(text: str, match_start: int, match_end: int) -> Tuple[str, int, int]:
    from src.detection import _find_sentence_start, _find_sentence_end
    sent_start = _find_sentence_start(text, match_start)
    sent_end = _find_sentence_end(text, match_end)
    if sent_end - sent_start > _MAX_POTTERY_SENTENCE:
        # No usable sentence boundaries found (e.g. table rows, caption blocks).
        # Fall back to just the line containing the trigger so that each table row
        # is treated as its own unit and _extract_by_regex gets focused input.
        line_start = text.rfind("\n", 0, match_start)
        line_start = (line_start + 1) if line_start != -1 else 0
        line_end = text.find("\n", match_end)
        line_end = line_end if line_end != -1 else len(text)
        return text[line_start:line_end].strip(), line_start, line_end
    return text[sent_start:sent_end].strip(), sent_start, sent_end


def _extract_date_context(text: str, sent_start: int, sent_end: int, n: int = 2) -> str:
    """Extend sentence span by ±n real sentences to capture nearby date expressions.

    Uses the same sentence-boundary regex as the rest of the pipeline so that decimal
    numbers in table cells ("16.6", "2.0") are not mistaken for sentence boundaries.
    """
    from src.detection import _SENT_BOUNDARY_RE

    boundaries = [(m.start(), m.end()) for m in _SENT_BOUNDARY_RE.finditer(text)]
    # boundary = (period_char_pos, first_char_of_next_sentence)

    # Walk back n sentence boundaries from sent_start to find ctx_start
    prev_starts = [b[1] for b in boundaries if b[1] <= sent_start]
    ctx_start = prev_starts[-n] if len(prev_starts) >= n else 0

    # Walk forward n sentence boundaries from sent_end to find ctx_end
    next_ends = [b[0] + 1 for b in boundaries if b[0] >= sent_end]
    ctx_end = next_ends[n - 1] if len(next_ends) >= n else len(text)

    return text[ctx_start:ctx_end].strip()


def _clause_forward_context(sentence: str, pos: int) -> str:
    """The find's own clause: from the find position forward to the next clause boundary
    (comma/semicolon/colon/period). Isolates a find's own date in an enumeration like
    "X … 2nd century, Y … 1st century" so a neighbour's date can't bleed in."""
    rest = sentence[pos:]
    m = re.search(r"[,;:.]", rest)
    return (rest[:m.start()] if m else rest).strip()


def _line_context(text: str, pos: int) -> str:
    """The find's OWN line (newline-bounded), but ONLY when it is a finds-table CELL — a
    short line with a short (numeric/single-token) neighbouring line, as in a flattened
    inventory table ("…\\n7\\naardewerk Romeinse tijd t/m Volle Middeleeuwen\\n1\\n…").
    Returns "" for ordinary prose, where line-scoping would wrongly truncate a clause-
    bounded date (e.g. a wrapped "2nd–3rd century"); there the wider contexts apply."""
    ls = text.rfind("\n", 0, pos) + 1
    le = text.find("\n", pos)
    if le == -1:
        le = len(text)
    line = text[ls:le].strip()
    if len(line) > 60:                       # a long line is prose, not a table cell
        return ""
    prev, nxt = _adjacent_lines(text, pos)   # table cells sit beside short number/token lines
    if len(prev) <= 12 or len(nxt) <= 12:
        return line
    return ""


def _forward_date_context(text: str, pos: int, n: int = 2, min_chars: int = 0) -> str:
    """Context for the date-LLM: from the FIND's position forward through n sentence
    ends — i.e. the rest of its clause plus the next n sentences. Deliberately
    excludes text BEFORE the find so adjacent off-topic dates (coin statistics, a
    different vessel's date earlier in the sentence) cannot mislead the model.
    In these reports the find's own date typically follows it ("X, dateerbaar …").

    ``min_chars`` guarantees a minimum forward reach: abbreviation periods ("Ed.",
    "Bern.") create false sentence boundaries that can cut the window short before a
    date stated a few sentences later, so the char floor keeps it in view."""
    from src.detection import _SENT_BOUNDARY_RE

    boundaries = [(m.start(), m.end()) for m in _SENT_BOUNDARY_RE.finditer(text)]
    next_ends = [b[0] + 1 for b in boundaries if b[0] >= pos]
    end = next_ends[n - 1] if len(next_ends) >= n else len(text)
    if min_chars:
        end = max(end, min(pos + min_chars, len(text)))
    return text[pos:end].strip()


# Standalone site-inventory codes (e.g. Belgian CAI: a line that is exactly 6
# digits). In inventory-style tables each code heads a block of finds, so the
# nearest code above a find is that find's site.
_SITE_CODE_RE = re.compile(r"^[ \t]*(\d{6})[ \t]*$", re.MULTILINE)


def _site_code_before(text: str, pos: int) -> str:
    """Forward-fill: return the last standalone site code at/above char `pos`."""
    last = ""
    for m in _SITE_CODE_RE.finditer(text):
        if m.start() <= pos:
            last = m.group(1)
        else:
            break
    return last


# In-entry find-category labels in old bulletin reports: an all-caps material word
# (optionally multi-word) at line start ending in ":" or ".", e.g. "AARDEWERK:",
# "GLASWERK.", "MUNTEN:". They delimit category blocks within one site entry.
_CATEGORY_LABEL_RE = re.compile(r"(?m)^[ \t]*[A-ZÀ-Þ]{4,}(?:[ \t]+[A-ZÀ-Þ]{2,})*\s*[:.]")


def _category_scoped_context(text: str, pos: int) -> str:
    """For a find at char `pos` in a multi-category bulletin entry, return the entry
    intro plus the find's OWN category block, excluding sibling blocks — so a date in
    another category (e.g. a coin reign under "MUNTEN:") cannot date this find. If the
    entry has no category labels, returns the whole text unchanged.
    """
    labels = [m.start() for m in _CATEGORY_LABEL_RE.finditer(text)]
    if not labels:
        return text
    block_start = 0
    for ls in labels:
        if ls <= pos:
            block_start = ls
        else:
            break
    block_end = next((ls for ls in labels if ls > block_start), len(text))
    if block_start == 0:  # find sits in the intro, before any category label
        return text[:block_end]
    return text[:labels[0]] + "\n" + text[block_start:block_end]


def _trigger_is_covered(trigger_start: int, trigger_end: int, covered: Set[Tuple[int, int]]) -> bool:
    """Return True only if the trigger word itself falls inside an existing candidate span."""
    for cs, ce in covered:
        if trigger_start >= cs and trigger_end <= ce:
            return True
    return False


def _extract_by_regex(sentence: str) -> Optional[str]:
    for pattern in _NAMING_PATTERNS:
        m = pattern.search(sentence)
        if m:
            name = m.group(0).strip()
            if _is_valid_pottery_name(name):
                return name
    # Fallback for table rows: when the entire line is just a bare vessel-form word
    # (bowl, jar, plate, …) with no accompanying typology code, preserve it as-is.
    # The full-line anchor on _VESSEL_FORM_RE prevents prose sentences from matching.
    stripped = sentence.strip()
    if _VESSEL_FORM_RE.match(stripped):
        return stripped.capitalize()
    return None


def _extract_at_trigger(
    sentence: str, t_start: int, t_end: int, trigger_text: str
) -> Optional[str]:
    """Extract the pottery name at a specific trigger position within the sentence.

    Unlike _extract_by_regex (which returns the first naming-pattern match anywhere
    in the sentence), this anchors on the trigger word so that a sentence listing
    several terms — e.g. "aardewerk (terra sigillata, dolia, kookpotten, kruikwaar)"
    — yields the correct term for each trigger rather than only the first.

    Priority: (1) a naming pattern whose match spans the trigger (captures compounds
    like "ruwwandig aardewerk"); (2) the whole line as a bare vessel form (table
    cells); (3) the trigger word itself.
    """
    for pattern in _NAMING_PATTERNS:
        for m in pattern.finditer(sentence):
            if m.start() <= t_start and m.end() >= t_end:
                name = m.group(0).strip()
                if _is_valid_pottery_name(name):
                    return name
    stripped = sentence.strip()
    if _VESSEL_FORM_RE.match(stripped):
        return stripped.capitalize()
    # Bare generic / indeterminate form alone on its line — a finds-table row
    # ("pot", "beker", "onbekend", "indet"). The whole-line equality keeps prose out:
    # in running text the trigger's line is the full clause, not the lone token.
    token = stripped.rstrip('?').strip()
    if token.lower() in GENERIC_FORM_TOKENS:
        return token
    # Strip a glued Dutch compound tail so "wrijfschaalfragmenten" → "wrijfschaal",
    # "terra sigillatascherven" → "terra sigillata".
    name = _strip_compound_tail(trigger_text.strip())
    if _is_valid_pottery_name(name):
        return name
    # Bare vessel form inside a finds ENUMERATION ("dolia, mortaria and jugs"): accept it
    # when it directly follows a list connector AND the sentence lists other pottery. This
    # keeps lone prose "cups"/"jugs" out while catching genuine enumerated finds.
    tok = trigger_text.strip()
    if (re.search(r'(?:,|\band\b|\ben\b|&)\s*$', sentence[:t_start])
            and _VESSEL_FORM_RE.match(tok)
            and _POTTERY_NAME_INDICATOR.search(sentence)):
        return tok
    return None


# Bare vessel-form names used as fallback when a table line contains nothing more
# than the form word itself (no typology code, no additional context).
# Matched as full-line anchored so prose sentences never trigger this.
_VESSEL_FORM_RE = re.compile(
    r'^(?:[a-z]+\s+)?'  # optional descriptive qualifier ("cheese" strainer, "storage" jar)
    r'(bowls?|jugs?|jars?|plates?|cups?|dishes?|flasks?|flagons?|beakers?|urns?'
    r'|bottles?|bowl/jars?|tankards?|lids?|strainer[s]?)$',
    re.IGNORECASE,
)

_NON_POTTERY_MATERIALS = re.compile(
    r'\b(bronze[n]?|metalen?|iron|ijzer|koper|lood|glass|glas|steen|stone|hout|wood|been|bone)\b',
    re.IGNORECASE,
)

# A valid pottery name must contain at least one pottery-specific NON-NUMERIC term.
# \d+ intentionally excluded: bare years (1985) and page numbers pass the digit check
# but are not pottery. Typology codes like "Drag. 37" still pass because "drag" matches.
_POTTERY_NAME_INDICATOR = re.compile(
    r'\b(ware|wares|aardewerk|keramiek|sigillata|nigra|rubra|amphorae?'
    r'|arretin[ae]'                   # arretina / arretine
    r'|mortari(?:um|a)|doli(?:um|a)'  # full inflected forms so \b lands at the right place
    r'|kookpot(?:ten)?|kruikwa(?:ar|ren)|kruik'  # generic Dutch forms: cooking pot(s), jug-ware, jug
    r'|kogelpot\w*'                   # kogelpot / kogelpotten / kogelpotaardewerk (compound)
    r'|wrijfscha(?:al|len)'           # wrijfschaal/wrijfschalen (Dutch mortarium / grinding bowl)
    r'|deksel\w*'                     # deksel / deksels (lid)
    r'|(?:schaaltje|kommetje|bekertje|kruikje|urntje|potje|kannetje|schoteltje|bordje)s?'  # NL diminutive vessel forms
    r'|drinkbeker\w*'                 # drinkbeker (drinking cup compound)
    r'|stempel'                       # maker-stamped sherd ("scherf met stempel")
    r'|gladwandig\w*|ruwwandig\w*|grijsbakkend|roodbakkend|witbakkend'
    r'|geverfd\w*|painted|decorated'  # geverfde beker / painted cups (painted/decorated vessel)
    r'|steengoed|terra|drag|stuart|dressel|niederbieber|hofheim|alzei|gose'
    r'|haltern|chenet|brunsting|loeschcke|gauloise|conspectus|oelmann|pirling'
    r'|pannenbakkerij|inheems|handgevormd|handmade|native'
    # Bare (non-diminutive) Dutch vessel-form + ware words common in real grey-literature.
    # "kan"/"kom" (Dutch modal verbs) are deliberately excluded; "kommen" (plural) is kept.
    r'|bord(?:en)?|urn(?:en)?|schaal|schalen|schotel(?:s)?|amfo(?:or|ren)|amphoor'
    r'|fles(?:sen)?|beker(?:s)?|kommen|honingpot\w*|kurkurn\w*|gordelbeker\w*'
    r'|kruikamfo\w*|wrijfkom\w*|wrijfschotel\w*|pannetje\w*'
    r'|lamp(?:en)?|olielamp\w*|firmalamp\w*'
    r'|pingsdorf\w*|badorf\w*|siegburg|paffrath|andenne|badorfer'
    # French vessel/ware words (some reports are in French)
    r'|assiette\w*|[ée]cuelle\w*|tasse\w*|cruche\w*|lampe\w*|vase\w*|urne\w*'
    r'|amphore\w*|gobelet\w*|pichet\w*|sigill[ée]e?|terre\s+(?:cuite|rouge|sigill)'
    r'|poterie|c[ée]ramique)\b',
    re.IGNORECASE,
)

# Bare years and page/inventory numbers are not pottery names.
_BARE_NUMBER = re.compile(r'^\d+$')

# NOTE: "aardewerk" (Dutch for "pottery") is intentionally NOT here — in the
# Dutch site-inventory reports it is recorded as a finding in its own right.
_GENERIC_TERMS = {
    "pottery", "sherds", "sherd", "scherven", "scherf",
    "keramiek", "ceramics", "ceramic", "vessel", "vessels",
    "soorten", "soort", "types", "type", "vormen", "vorm",
    # bare "ware"/"wares" is a fabric indicator, not a find on its own
    # ("Samian ware" etc. are compounds and remain valid)
    "ware", "wares",
}

# Bare generic / indeterminate FORM tokens (NL + EN). On their OWN line — i.e. as a
# finds-table row — these are recorded as a (typically undated) finding, because a
# finds table lists them as form types. They are deliberately accepted ONLY when the
# trigger's whole line is just the token: in prose the line is the full clause, so a
# common word like "pot" never matches here. Distinct from _GENERIC_TERMS (fabric /
# material words that are never findings on their own).
GENERIC_FORM_TOKENS = {
    "pot", "potten", "beker", "bekers", "beaker", "beakers",
    "onbekend", "onbekende", "indet", "indeterminate", "unknown",
}

# Function/category COLUMN headers in finds cross-tabs. A bare vessel-form token
# sandwiched between these (e.g. "…Large Container / Flagons / Kitchenware…") is a
# header cell, not a find, and must not be extracted as pottery.
_FUNCTION_HEADER_TERMS = {
    "function", "category", "categorie", "fragments", "fragmenten",
    "tableware", "kitchenware", "storage", "container",
    "small container", "large container", "drinking vessel",
}


def _adjacent_lines(text: str, pos: int) -> Tuple[str, str]:
    """Return (previous non-empty line, next non-empty line) around the line at pos."""
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)

    prev = ""
    j = line_start - 1
    while j > 0:
        ps = text.rfind("\n", 0, j) + 1
        cand = text[ps:j].strip()
        if cand:
            prev = cand
            break
        j = ps - 1

    nxt = ""
    k = line_end + 1
    while k < len(text):
        ke = text.find("\n", k)
        if ke == -1:
            ke = len(text)
        cand = text[k:ke].strip()
        if cand:
            nxt = cand
            break
        k = ke + 1
    return prev, nxt


# Truly INDETERMINATE form tokens (a subset of GENERIC_FORM_TOKENS): unlike "pot"/"beker"
# these name no vessel at all. When the SAME token repeats consecutively ("Onbekend
# Onbekend Onbekend …") it is a flattened metadata/legend column fill, not N separate
# finds, so it must be dropped. A lone "onbekend"/"indet" in a real finds row is kept.
_INDETERMINATE_FORMS = {"onbekend", "onbekende", "indet", "indeterminate", "unknown"}


def _is_indeterminate_noise(name: str, text: str, pos: int) -> bool:
    """True when a bare indeterminate token (Onbekend/indet/unknown) appears as part of a
    consecutive repetition of itself — a column-fill cell, not a recorded pottery find."""
    tok = name.strip().lower().rstrip("?").strip()
    if tok not in _INDETERMINATE_FORMS:
        return False
    seg = text[max(0, pos - 40):pos + 40].lower()
    esc = re.escape(tok)
    return bool(re.search(esc + r"\W+" + esc, seg))


def _is_function_header_form(name: str, text: str, line_pos: int) -> bool:
    """True when a bare vessel-form/generic token is actually a Function-column header
    in a cross-tab — i.e. its adjacent line is a function/category header term."""
    nl = name.strip().lower()
    if not (_VESSEL_FORM_RE.match(nl) or nl in GENERIC_FORM_TOKENS):
        return False
    prev, nxt = _adjacent_lines(text, line_pos)
    return prev.lower() in _FUNCTION_HEADER_TERMS or nxt.lower() in _FUNCTION_HEADER_TERMS

# PERIOD-qualified generic ware-GROUP headers (e.g. "Late Roman coarse ware")
# are overview/section captions describing a whole class of finds, not a specific
# pottery mention — so they are false positives. The leading period term is what
# makes them a header: a *bare* generic ware ("coarse ware", "fine ware") is kept,
# because in site-inventory reports it is itself a recorded find. Specific named
# wares ("Samian ware", "Gallo-Belgic ware") never match here either.
_WARE_GROUP_LABEL = re.compile(
    r'^(?:(?:early|middle|late|sub-?)\s+)*'                                  # optional period adjective(s)
    r'(?:roman|medieval|prehistoric|merovingian|carolingian|iron[\s-]?age)'  # REQUIRED period noun
    r'\s+'
    r'(?:coarse|fine|rough|common|reduced|oxidi[sz]ed|grey|gray|kitchen|table|cooking|household|domestic)'
    r'\s+wares?$',
    re.IGNORECASE,
)


def _is_valid_pottery_name(name: str) -> bool:
    name = name.strip()
    # Reject bare numbers and years (e.g. "1985", "42")
    if _BARE_NUMBER.match(name):
        return False
    # Reject bracket-enclosed labels — these are section headings, not pottery types
    if name.startswith('[') or name.endswith(']'):
        return False
    if name.lower() in _GENERIC_TERMS:
        return False
    # Reject generic ware-group headers ("Late Roman coarse ware", "fine ware")
    if _WARE_GROUP_LABEL.match(name):
        return False
    if _NON_POTTERY_MATERIALS.search(name):
        return False
    if not _POTTERY_NAME_INDICATOR.search(name):
        return False
    return True


def _extract_by_llm(sentence: str) -> List[str]:
    """LLM fallback for pottery-name extraction: ask the model for the pottery/ware names in a
    trigger sentence the rules could not name. Returns a list of names (possibly empty); used only
    when `POTTERY_EXTRACT_LLM_USE` is on."""
    from src.llm_client import call_llm

    raw = call_llm(_LLM_PROMPT.format(sentence=sentence.strip()))
    try:
        start = raw.index('[')
        end = raw.rindex(']') + 1
        names = json.loads(raw[start:end])
        if isinstance(names, list):
            cleaned = [n.strip().strip('"\'') for n in names if isinstance(n, str)]
            return [n for n in cleaned if n and _is_valid_pottery_name(n)]
    except (ValueError, json.JSONDecodeError):
        pass
    return []


def _find_page(page_breaks: list, char_offset: int) -> int:
    page = page_breaks[0][0]
    for page_no, offset in page_breaks:
        if offset <= char_offset:
            page = page_no
        else:
            break
    return page


# Vessel-of-ware constructions in prose ("een kom van terra sigillata", "kom van
# handgemaakt aardewerk"): the find IS the vessel (a bowl made of that ware), so we
# emit the vessel form and suppress the inner ware mention. Gated to vessel + "van" +
# ware so bare vessel words in running text are never extracted.
_VESSEL_EN = {
    "kom": "Bowl", "kommen": "Bowl", "schaal": "Bowl", "schalen": "Bowl",
    "bord": "Plate", "borden": "Plate", "beker": "Beaker", "bekers": "Beaker",
    "kruik": "Jug", "kruiken": "Jug", "kan": "Jug",
}
_VESSEL_OF_WARE_RE = re.compile(
    r"(kom(?:men)?|scha(?:al|len)|bord(?:en)?|beker(?:s)?|krui(?:k|ken)|kan)\s+van\s+"
    r"(?:[\w-]+\s+){0,4}"
    r"(?:terra\s+sigillata|terra\s+nigra|terra\s+rubra|sigillata|aardewerk|keramiek)\b",
    re.IGNORECASE,
)


def extract_pottery_mentions(
    chunks: List[Dict],
    existing_candidates: List[Dict],
    triggers: List[Dict],
    use_llm: bool = True,
    report_id: str = "",
    section_texts: Optional[Dict[str, str]] = None,
) -> List[Dict]:
    """Layer 3b entry point: find pottery mentions not already covered by the regex patterns.

    Trigger words (EN/NL/LA) flag candidate sentences; each is confirmed and named by surrounding
    cues and validity checks, with an optional LLM fallback (`use_llm`). `existing_candidates` mark
    positions already covered by Layer 3 so the same find is not emitted twice. A widened
    ±2-sentence `date_context` is attached for Layer 6. Returns the new candidate dicts."""
    trigger_re = _build_trigger_regex(triggers)
    section_texts = section_texts or {}

    covered_per_chunk: Dict[str, Set[Tuple[int, int]]] = {}
    for cand in existing_candidates:
        cid = cand["chunk_id"]
        covered_per_chunk.setdefault(cid, set()).add(
            (cand["start_char"], cand["end_char"])
        )

    new_candidates: List[Dict] = []
    seen_sentences: Set[Tuple[str, int]] = set()
    total_trigger_hits = regex_hits = llm_calls = llm_hits = 0

    # First pass: collect all trigger sentences that need processing
    pending = []
    for chunk in chunks:
        text = chunk["text"]
        chunk_id = chunk["chunk_id"]
        covered = covered_per_chunk.setdefault(chunk_id, set())
        for m in trigger_re.finditer(text):
            # Skip only if the trigger word itself is already inside an existing candidate.
            # Using word-level (not sentence-level) overlap allows detecting multiple
            # pottery entities in the same sentence (e.g. "kommen van inheems aardewerk
            # en van terra sigillata (Chenet 320)").
            if _trigger_is_covered(m.start(), m.end(), covered):
                continue
            # Vessel-of-ware: "kom van … terra sigillata" → emit the vessel (Bowl) and
            # claim the span so the inner ware trigger is suppressed (one find, not two).
            # override = (vessel_name, clause_text, clause_start, clause_end): the clause
            # is this find's own context, so two bowls in one sentence stay distinct.
            override = None
            tok = m.group().lower()
            if tok in _VESSEL_EN:
                vow = _VESSEL_OF_WARE_RE.match(text, m.start())
                if vow:
                    covered.add((m.start(), vow.end()))
                    override = (_VESSEL_EN[tok], text[m.start():vow.end()].strip(),
                                m.start(), vow.end())
            sentence, sent_start, sent_end = _extract_sentence(text, m.start(), m.end())
            # Deduplicate on the trigger-word's absolute position, not the sentence start.
            # Using sentence start was too aggressive for table content: all triggers in a
            # chunk with no sentence boundaries share sent_start=0 and only the first
            # would fire. Using the trigger position means each trigger occurrence fires
            # exactly once (same trigger in two overlapping chunks → same abs position →
            # deduplicated; different triggers in the same sentence → each processed once).
            # Actual result-level duplicates (same pottery name, same original text) are
            # collapsed later by the dedup step in export_pottery_summary().
            abs_trigger_start = chunk.get("text_offset_start", 0) + m.start()
            sent_key = (chunk["section_id"], abs_trigger_start)
            if sent_key in seen_sentences:
                continue
            seen_sentences.add(sent_key)
            # Trigger position relative to the extracted sentence, so extraction can
            # anchor on this trigger rather than the first match in the sentence.
            pending.append((chunk, sentence, sent_start, sent_end,
                            m.start() - sent_start, m.end() - sent_start, m.group(),
                            override))

    total_trigger_hits = len(pending)
    llm_total = sum(
        1 for (_c, s, _ss, _se, ts, te, tt, ov) in pending
        if ov is None and _extract_at_trigger(s, ts, te, tt) is None and use_llm
    )
    print(f"[Layer 3b] {total_trigger_hits} trigger sentences to inspect | {llm_total} will need LLM ...")

    for chunk, sentence, sent_start, sent_end, t_start, t_end, trigger_text, override in pending:
        # ctx_text/cand_start/cand_end define the find's own context + position; for a
        # vessel-of-ware find these are its clause (so two bowls in one sentence are
        # distinct rows), otherwise the trigger's sentence.
        ctx_text, cand_start, cand_end = sentence, sent_start, sent_end
        if override is not None:
            name, ctx_text, cand_start, cand_end = override
            method = "vessel_of_ware"
            regex_hits += 1
        else:
            name = _extract_at_trigger(sentence, t_start, t_end, trigger_text)
            method = "trigger_regex"
            if name is not None:
                regex_hits += 1
            elif use_llm:
                llm_calls += 1
                print(f"[Layer 3b] LLM call {llm_calls}/{llm_total} ...")
                names = _extract_by_llm(sentence)
                if names:
                    name = names[0]
                    method = "trigger_llm"
                    llm_hits += 1

        if name is None:
            continue
        # Collapse OCR line-breaks inside the extracted name ("terra\nrubra" → "terra rubra").
        name = re.sub(r"\s+", " ", name).strip()

        # Drop Function-column headers in cross-tabs (e.g. "Flagons" between
        # "Large Container" and "Kitchenware") — header cells, not finds.
        if _is_function_header_form(name, chunk["text"], sent_start):
            continue
        # Drop a bare indeterminate token (Onbekend/indet/unknown) with no pottery word
        # nearby — a metadata/legend cell, not a find (E).
        if _is_indeterminate_noise(name, chunk["text"], sent_start):
            continue

        new_candidates.append({
                "report_id": report_id,
                "chunk_id": chunk["chunk_id"],
                "section_id": chunk["section_id"],
                "section_title": chunk["section_title"],
                "section_site": chunk.get("site_name", ""),
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "page": _find_page(chunk["page_breaks"], sent_start),
                "term_raw": name,
                "match_type": method,
                "pattern_id": "pottery_trigger",
                "canonical_hint": None,
                "chronology_id": None,
                "phase_code": None,
                "preferred_label": name,
                "date_start": None,
                "date_end": None,
                "start_char": cand_start,
                "end_char": cand_end,
                # Inventory-table site code governing this find (forward-filled from
                # the nearest standalone 6-digit line above it); "" when none.
                # Resolved over the whole SECTION at the TRIGGER word's absolute offset
                # (sent_start + t_start): using the sentence start would, in dense
                # table text, reach above the find's own code and grab an earlier one.
                "site_code": _site_code_before(
                    section_texts.get(chunk["section_id"], chunk["text"]),
                    chunk.get("text_offset_start", 0) + sent_start + t_start,
                ),
                "context_window": ctx_text,
                "context_sentence": ctx_text,
                # Use this chunk's own text: `text` from the first-pass loop is stale
                # here (it points at the last chunk), which would pull date context
                # from an unrelated section. sent_start/sent_end are offsets into
                # chunk["text"], so they align with it.
                # Clause-bounded forward context: from the find to the next clause
                # boundary (,;:.) — for enumerations where each find carries its OWN date
                # ("terra sigillata … 2nd century, painted cups … 2nd-3rd, amphorae … 1st
                # century") this isolates the find's own date instead of letting
                # narrowest-wins grab a neighbour's. Tried FIRST in _best_dates; when it
                # holds no date the wider contexts still apply, so other cases are unchanged.
                "clause_date_context": _clause_forward_context(sentence, t_start),
                # The find's own line — isolates a finds-table row's period from interleaved
                # neighbouring rows (D1). Tried before the wider windows in _best_dates.
                "line_date_context": _line_context(chunk["text"], sent_start + t_start),
                # For a self-contained short entry (whole section in one chunk), scope
                # the date context to the entire entry so a governing period stated a
                # few sentences away still applies to every find in it — but within a
                # multi-category entry, restrict to the find's own category block so a
                # coin/glass date can't bleed onto pottery; otherwise ±2 sentences.
                "date_context": (
                    _category_scoped_context(chunk["text"], sent_start + t_start)
                    if chunk.get("is_full_section")
                    else _extract_date_context(chunk["text"], sent_start, sent_end, n=2)
                ),
                # Forward-focused context for the date-LLM (C2): from the find forward,
                # so off-topic dates BEFORE it (coin stats, an earlier vessel's date)
                # can't mislead the model.
                # n=4: in narrative/bulletin prose the find's date can sit a few
                # sentences after it ("…kwamen schaaltjes… voor den dag. … De voorwerpen,
                # welke uit de tweede eeuw na Christus…"). Forward-only keeps earlier
                # off-topic dates out; the regex/chron_vocab path reads this too.
                "llm_date_context": _forward_date_context(
                    chunk["text"], sent_start + t_start, n=4, min_chars=650
                ),
            })

    print(
        f"[Pottery] trigger sentences: {total_trigger_hits}"
        f" | regex: {regex_hits}"
        f" | LLM calls: {llm_calls}"
        f" | LLM hits: {llm_hits}"
        f" | new candidates: {len(new_candidates)}"
    )
    return new_candidates


# A find/catalogue number used to label a vessel drawing on a plate, e.g.
# "513-2/20-1-67", "22-3-6/4056". The slash + multiple dashes distinguish it from
# measurements (decimals/×/units) and date ranges (no slash); \d{1,3} on the first group
# keeps 4-digit references like "2009-V.962" out.
_CATALOGUE_NUM_RE = re.compile(r"\b\d{1,3}-\d+(?:-\d+)?/\d+(?:-\d+)*\b")
# Figure/plate caption markers (NOT "Table/Tabel" — those are DATA tables, not vessel
# plates, and would risk the finds-table reports).
_FIG_MARKER_RE = re.compile(
    r"\b(?:fig|figure|afb|pl|plate|tafel|taf|abb|abbildung|planche)\b\.?", re.IGNORECASE)
# Vessel/pottery words that mark a caption as a pottery plate. The list can be broad and
# multilingual because firing also requires a figure marker (the conjunction keeps
# precision): ordinary prose mentioning "aardewerk" won't trigger unless it is a caption.
_VESSEL_CAPTION_RE = re.compile(
    r"\b(?:vessels?|vaatwerk|aardewerk|pottery|ceramics?|keramiek|potten|scherven"
    r"|gef[aä][sß]e|funde|vases?|c[eé]ramique)\b", re.IGNORECASE)
# A find-number paired with a typology/form code on one line marks a find CATALOGUE.
_CATALOGUE_ENTRY_RE = re.compile(
    r"(?:-{1,2}/)?\d[\d./+\- ]*\d\s*,\s*(?:Drag|dish|cup|Lud)", re.IGNORECASE)


def extract_figure_catalogue_finds(chunks: List[Dict], report_id: str = "") -> List[Dict]:
    """Plates of vessel drawings label each vessel only with a find/catalogue number
    (no ware word). Such a number is a find ONLY inside a vessel-plate caption, so it is
    extracted gated on BOTH a figure/plate marker AND a vessel/pottery word in the same
    chunk. Each number is dated from the caption (e.g. "Late Roman vessels" → 275–450)."""
    out: List[Dict] = []
    for chunk in chunks:
        text = chunk["text"]
        if not (_FIG_MARKER_RE.search(text) and _VESSEL_CAPTION_RE.search(text)):
            continue
        # A chunk that pairs numbers with typology codes ("…/8128, Drag. 29") is a FIND
        # CATALOGUE, not a plate of vessel drawings labelled by bare numbers — those
        # entries are handled by the typology + catalogue-prefix pairing, so skip here.
        if _CATALOGUE_ENTRY_RE.search(text):
            continue
        caption = next((ln.strip() for ln in text.split("\n")
                        if _VESSEL_CAPTION_RE.search(ln)), text.strip())
        seen: Set[str] = set()
        for m in _CATALOGUE_NUM_RE.finditer(text):
            num = m.group(0)
            if num in seen:
                continue
            # A number immediately followed by ", Drag./dish/cup" is a catalogue ENTRY
            # (find-number + typology on one line), handled by the typology pairing — not
            # a bare figure label. Skip it here so it isn't double-counted.
            if re.match(r"\s*,\s*(?:Drag|dish|cup|Lud)", text[m.end():m.end() + 14], re.IGNORECASE):
                continue
            seen.add(num)
            out.append({
                "report_id": report_id,
                "chunk_id": chunk["chunk_id"],
                "section_id": chunk["section_id"],
                "section_title": chunk["section_title"],
                "section_site": chunk.get("site_name", ""),
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "page": _find_page(chunk["page_breaks"], m.start()),
                "term_raw": num,
                "match_type": "figure_catalogue",
                "pattern_id": "pottery_figure_catalogue",
                "canonical_hint": None,
                "chronology_id": None,
                "phase_code": None,
                "preferred_label": num,
                "date_start": None,
                "date_end": None,
                "start_char": m.start(),
                "end_char": m.end(),
                "site_code": "",
                "context_window": caption,
                "context_sentence": caption,
                "date_context": caption,
                "llm_date_context": caption,
            })
    return out

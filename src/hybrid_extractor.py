"""
Claude-hybrid full-report extraction (see docs/design/design_notes.md).

A frontier LLM reads the WHOLE report and returns the pottery find list directly, instead
of the rule-based detect→interpret→date→summarise chain. Two guardrails make it usable for
a thesis:

  1. Anti-hallucination: every find must carry a VERBATIM quote that actually appears in the
     report; finds whose quote cannot be located are dropped.
  2. Deterministic date grounding: when the model returns a typology code (Drag. 37, Gose
     230 …) its date is taken from the canonical typology table, not the model's number, so
     dates stay consistent with the rule pipeline.

Model-agnostic: uses Claude when ANTHROPIC_API_KEY is set, otherwise falls back to the
configured cloud LLM (LLM_API_*), so the architecture runs without a Claude key. Gated by
config.POTTERY_HYBRID_LLM_USE; output schema matches export_pottery_summary().
"""
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_OUT_FIELDS = [
    "report_id", "site_name", "page", "pottery", "typology", "term_found", "term_found_normalized_en",
    "quantity",
    "start_date", "end_date", "date_method", "context_label",
    "pot_name_certainty_level", "pot_name_llm_reasoning",
    "pot_presence_certainty_level", "pot_presence_llm_reasoning",
    "dates_certainty_level", "date_llm_reasoning",
    "overall_certainty_level",
    "original_text",
]

_PROMPT = """\
You are an expert archaeologist extracting POTTERY finds from an excavation report. The
report may be in Dutch, English, French or German (incl. archaic spelling). Read the WHOLE
report below and list EVERY pottery vessel or ware that was actually FOUND at a site.

For each find return JSON keys:
- "pottery": the vessel/ware name in English (e.g. "Terra sigillata", "Jug", "Cooking pot",
  "Beaker", "Mortarium", "Amphora", "Cork urn", "Pingsdorf ware"). KEEP the ware qualifiers the
  text gives — fabric/tradition/colour/technique words like native/inheems, handmade/handgevormd,
  coarse/fine, reduced/oxidized, colour: e.g. "inheems-Romeins aardewerk" -> "Native Roman ware",
  "rood ruwwandig aardewerk" -> "Red coarse ware". Use bare "Pottery" ONLY for a truly generic,
  unqualified sherd.
  DIMINUTIVES: render the BASE vessel form, NEVER "Small …"/"Little …". A diminutive is a grammatical
  form, not a size. Dutch -je/-tje/-pje/-kje (+plural -s): schaaltje(s) -> "Dish", kommetje(s) ->
  "Bowl", bekertje(s) -> "Beaker", kruikje(s) -> "Jug", urntje(s) -> "Urn", potje(s) -> "Pot",
  kannetje(s) -> "Flagon"; German -chen/-lein (Schälchen -> "Dish"); French -et/-ette. The verbatim
  diminutive is still preserved in "term".
- "typology": the typology code exactly as written if given ("Drag. 37", "Gose 230",
  "Niederbieber 79", "Stuart 201B", "Alzey 28"), else "".
- "term": the ware/vessel term EXACTLY as written in the report, in the SOURCE language (not
  translated), e.g. "inheems-Romeins aardewerk", "gladwandig aardewerk", "speelschijfje", "Drag. 37".
- "site": the SETTLEMENT-LEVEL site name. Strip COMMA-separated findspot qualifiers — streets,
  trenches/sleuven, fields, excavation/project/feature names, area sub-divisions — keeping only the
  town: "Uilegats, Heerlen" -> "Heerlen"; "Nijmegen, second fortress" -> "Nijmegen"; "Heerlen,
  Promenade" -> "Heerlen". BUT KEEP an established HYPHENATED site name (Municipality-Toponym) intact
  — that hyphenated form IS the site's name: "Voerendaal-Ten Hove", "Kerkrade-Holzkuil",
  "Geleen-Janskamperveld" stay as-is (do NOT shorten to just the municipality). Also keep genuinely
  compound town names ("Den Haag", "'s-Hertogenbosch"). Use the name AS THE REPORT GIVES IT — do not
  translate a Roman name to its modern town or vice versa. In a multi-site bulletin, attribute each
  find to its own site (the place heading the find sits under). If none is identifiable, "".
- "quantity": integer count of vessels for THIS row, ONLY when the text gives one — a numeral
  ("drie"/"3" -> 3, "27" -> 27, "een dertigtal" -> 30 approx), or a single specifically-described
  vessel -> 1. Use null when the count is not numerically given: an unquantified plural ("fragmenten
  van kommen"), a vague word ("talrijke"/"enkele"/"veel"), the bare article "een" meaning just "a"
  (not "one"), or no count at all. NEVER invent a count. A count NEVER creates extra rows (see F).
- "start_date" / "end_date": integer years for THIS find's production/use (negative = BCE),
  or null if the report states no date for it.
- "original_text": a VERBATIM quote copied exactly from the report that evidences this find.
- "page": the page number (from the [[pN]] markers) where the find is described, else null.
- "pot_name_certainty_level": integer 0-10 = how confident you are the WARE/TYPE is correctly
  identified. Clear explicit name/type = 9-10; normal = 7-8; a HEDGED identification
  ("possibly/probably a X", "mogelijk/vermoedelijk", "cf."/"vgl."/"?", "too worn to be sure") = 2-4.
- "pot_name_llm_reasoning": ONE short sentence on why (e.g. "name stated in the text",
  "identified from typology code", "tentative, cf. NB 104").
- "pot_presence_certainty_level": integer 0-10 = how confident you are this pot was actually
  RECOVERED here (a real find, not merely compared/cited). Clearly found = 9-10; found but hedged = 5-7.
- "pot_presence_llm_reasoning": ONE short sentence on why (e.g. "explicitly found in pit S12").
- "specific_object": true if this row is a DISCRETE pottery object/vessel actually recovered (a
  cataloged find, even if fragmentary, indeterminate, or hedged); false if it is only a GENERAL
  statement that pottery occurs / keeps being found at the place, with NO identifiable individual
  object — e.g. "op het Tempsplein komen voortdurend Romeinsche voorwerpen voor", "er worden sedert
  jaren gedurig Romeinsche potten en aardewerk gevonden". When in doubt, true. (A false row is kept,
  but its pot_name_certainty_level will be set to 0 — there is no specific ware to identify.)

RULES
- Include ONLY pottery actually recovered at a site. EXCLUDE: items merely compared, cited,
  or referenced; items explicitly NOT found; and all non-pottery (coins/munten, roof
  tiles/tegulae/dakpannen, glass, bronze, querns/maalstenen, flint/vuursteen). Ignore
  unrelated medieval/modern history asides.
- TENTATIVE IDENTIFICATION still counts. If an object WAS recovered but its type is hedged
  ("possibly a dolium", "mogelijk/vermoedelijk", "too worn to be sure"), INCLUDE it as a find of
  the stated type with a LOW pot_name_certainty_level (2-4) but a normal pot_presence_certainty_level.
  This is NOT the same as "explicitly NOT found" (which you exclude) — here the object exists, only
  its identification is uncertain.
- REWORKED SHERDS COUNT. A vessel sherd reused/reworked into another object (a pendant,
  spindle-whorl, gaming counter, etc.) means that vessel WAS found, so it IS a find of the
  ORIGINAL vessel — e.g. "pendant made of a rim fragment of a plate of form Haltern 1b" ->
  pottery "Plate", typology "Haltern 1b".
- DO NOT invent anything. Every find MUST have a verbatim original_text quote that appears
  in the report. If you cannot quote it, do not list it.
- BE EXHAUSTIVE. List every DISTINCT find. Catalogue lists and figure/plate captions often
  enumerate many vessels by number — emit ONE row PER numbered vessel. A single report can
  have 40+ finds; never summarise or sample. Terse prose may list several wares in one clause
  (e.g. "aardewerk (terra sigillata, dolia, kookpotten, kruikwaar)") — emit one row for EVERY
  ware named, including one-word "-waar"/"-goed" compounds (kruikwaar = flagon ware, ruwwandige
  waar = coarse ware); do not drop the last item in such a list.
- SPLIT COMPOUND ENTRIES. If ONE entry names more than one type/form, emit a SEPARATE row for
  EACH form — e.g. "fragmenten Drag. 29 en 37" -> two rows (Drag. 29 and Drag. 37);
  "Holwerda 25 en 27" -> two rows; "vormen Stuart 1 en 2" -> two rows.
- COUNT TABLE/CATALOGUE ROWS INDIVIDUALLY. In a finds table or per-vessel catalogue where each
  line is a separate vessel, emit one row per line — INCLUDING lines whose form is indeterminate
  ("indet", "onbekend", "vorm onbekend", a bare "pot"/"beker" count). Do NOT collapse several
  indeterminate line-items of the SAME ware into one row; if the table lists 5 indeterminate
  "Belgische waar" vessels, that is 5 rows. NOR merge a type that appears in MORE THAN ONE row/cell
  of a table (e.g. once per Content or Region column, or across two sub-tables) — emit a SEPARATE
  row for EACH such occurrence; never combine them into one summed row. (The "quantity is not
  multiplicity" rule applies to the count WITHIN a single cell, not across distinct cells.
  Collapsing applies ONLY to a later summary/recap of finds already listed — see DEDUP.)
- USE THE "STRUCTURED TABLES" SECTION (if present, after the prose) as the authoritative count of
  finds: emit ONE find per DATA row (read its ware/form/type from the columns), and SKIP rows that
  are group headers or subtotals (a group name with only totals and no specific Form/Type, e.g.
  "Coarse oxidized | Eifel region | - | - | 47 | 45"). A count column (N / aantal / MAI / MNI) gives
  the quantity — record that number in "quantity" and emit the row ONCE (never multiply rows by the
  count). Carry the typology code from the Type/Form column.
  SPANNED CELLS: when a ware/category cell is filled on one row and BLANK on the rows beneath it,
  those blank-cell rows belong to the SAME ware (carry it down) — emit a find for EACH such row,
  including rows whose type is "indet"/"onbekend"/"pot". Skip only the header and the grand-total
  row ("Eindtotaal"/"totaal"). E.g. a "Belgische waar" block with rows Holwerda 25/27/66/81, pot,
  onbekend, indet -> one Belgian-ware find PER row.
- FIELD CONVENTION: if a vessel is catalogued only by a find/registration number and no ware
  name is given, use that NUMBER as "pottery" and leave "typology" "". Never put a registration
  number in "typology" (typology is reserved for type codes like Drag./Gose/Stuart/Alzey/NB).
  When a figure/plate caption (e.g. "Fig. X. Examples of Late Roman vessels") is surrounded by a
  COLUMN of such numbers (often several lines ABOVE and BELOW the caption), EVERY number in that
  column is a separate vessel — emit ONE row for EACH of them, not just the one next to the caption.
- Dates — use ONLY chronological information written in the text about THAT find. Convert:
  "Xe eeuw"/"Xth century" = (X-1)*100+1..X*100 (no year 0: 1e eeuw = 1..100, 2e eeuw = 101..200, 4e eeuw = 301..400);
  "vroege/begin Xe" = (X-1)*100+1..(X-1)*100+50; "midden Xe" = +25..-25; "late/laat Xe" = +50..X*100;
  __PERIODS__;
  "v. Chr." / "BC" = negative years. If a typology code is given you MAY use its known
  production date.
- DATE INHERITANCE: if a find has no date of its OWN, inherit a context date ONLY when the report's
  DESCRIPTIVE PROSE explicitly gives one: an explicit period word for the finds/assemblage/occupation
  ("Romeinse vondsten"/"Roman finds"/"Romeinse tijd"/"Late Roman", "1e eeuw") OR a dated
  layer/feature/phase ("19-16 BC" dendro/coin, "4e eeuw"). Such an explicit context date applies to
  ALL finds in it that lack their own (e.g. text saying "Romeinse vondsten" -> -12..450). When that
  single explicit period governs a whole finds table/assemblage, apply the IDENTICAL range to EVERY
  typeless, otherwise-undated row in it — do not re-derive or narrow it row by row; if no single
  explicit period is stated, keep null (do not invent one). A period stated for the SITE/CONTEXT/
  PHASE itself governs the whole assemblage: if the report assigns the context to a SPECIFIC named
  period or dated horizon (e.g. "the youngest Augustan fortress", a "Flavian" phase, a layer dated
  "20-10 BC") — NOT merely "Roman"/"villa"/"nederzetting" — that period dates ALL its otherwise-
  undated finds, INCLUDING ones mentioned in a SEPARATE discussion paragraph (tableware, beakers,
  cooking pots). A GENERAL
  Roman/"Romeinse" signal with NO specific century or phase named is the FULL Roman range -12..450 —
  do NOT narrow it from the ware types present (terra sigillata/Belgic ware do not shrink "Romeinse
  vondsten" to the 1st c.). You MUST
  NOT INFER a date — keep null instead — from any of: (a) the site merely being a "villa"/
  "nederzetting"/"Roman site" WITHOUT a stated period word; (b) a find being a vessel TYPE that is
  typically Roman (dolium, mortarium, terra sigillata, amphora, etc. are NOT self-dating — a typology
  CODE dates, a bare ware name does NOT); (c) ANY "Roman"/"villa"/period word that appears only in a
  BIBLIOGRAPHY, "Bron:"/reference line, in-text citation, or publication TITLE (e.g. "in: J. de Bruin
  (ed.) 2025, Roman villas" does NOT date anything). A date the text ties to ANOTHER specific find
  (e.g. "het bekerfragment is in de 2e eeuw te dateren", "datable from AD 160") is THAT find's OWN
  date — do NOT pass it to other finds. A find with no typology and no explicit period/context date
  of its own in the descriptive prose keeps null. When in doubt, prefer null over a guessed date.
- QUANTITY IS NOT MULTIPLICITY — emit one row per DISTINCT find, NEVER one row per vessel. A plain
  count of an UNDIFFERENTIATED ware is ONE row with the number in "quantity": "drie kruiken" -> 1 Jug
  row, quantity 3; "27 potten" -> 1 Pot row, quantity 27; "vijf scherven gladwandig aardewerk" -> 1
  row, quantity 5 (sherds are pieces, not vessels). But KEEP SEPARATE every find that is individually
  DISTINGUISHED — by its own typology, STAMP, decoration, dimensions, date, findspot, or a separate
  catalogue entry/number — even of the SAME ware: two t.s. bowls with stamps OF MIM and SECVND.M ->
  2 rows; a "rechter pot" and a "linker pot" described separately -> 2 rows (quantity 1 each). When a
  count includes a singled-out item, split it off: "drie potten ... een hiervan is een klok-beker"
  -> Klok-beker (quantity 1) + Pot (quantity 2).
- PARTITIONED WARE — when the text explicitly splits a SINGLE ware into distinct SUBSETS by a
  distinctness criterion, emit ONE row PER subset (each with its own date/quantity), not one merged
  row. By DATE: "twee zijn vroeg-4e-eeuws, de rest dateert vanaf het midden van de 4e eeuw" ("two are
  early-4th-c., the rest from the mid-4th c.") -> an early-4th-c. row + a mid-4th-c. row. By
  DECORATION/MORPHOLOGY: "gevernist aardewerk MET EN ZONDER barbotine" -> a with-barbotine row + a
  without-barbotine row; "wrijfschalen met en zonder giettuit" ("mortaria with and without a pouring
  spout") -> with-spout + without-spout. Only split when the with/without (or subset) is a PHYSICAL
  feature or a different DATE that makes the vessels genuinely distinct. A ware merely GIVEN a single
  date RANGE, or one description, is still ONE row — split only on an explicit "two/some are X, the
  rest/others are Y" or "with and without <physical feature>".
- DEDUP: one row per DISTINCT find. If the SAME find is mentioned again (summary, registration
  recap, cross-reference, "the two bowls date the context"), list it ONCE. Two individually
  DISTINGUISHED vessels of one ware are two rows; an undifferentiated count of one ware is ONE row
  (quantity), not many.
- PREVIEW/LIST vs ITEMS — never emit BOTH for the same vessels. When one sentence names vessels as a
  GROUP — a count ("drie potten werden geplaatst…") or a list of several forms ("fragmenten van
  borden, kommen, urnen, deksels…") — and the text ALSO gives the individual members (by splitting
  that list into per-form rows, or by describing each vessel separately afterwards), emit ONLY the
  individual rows; do NOT additionally emit a row for the group/list sentence — it is the SAME finds.
  E.g. "drie naast elkaar geplaatste potten van ruwwandig aardewerk … De rechter pot … De middelste
  kruik … De linker pot" -> rechter pot + middelste kruik + linker pot (3 rows), NOT a 4th "drie
  potten" row; "fragmenten van borden, kommen, urnen" -> Plate + Bowl + Urn (3 rows), NOT also a
  combined "borden, kommen, urnen" row. (If only SOME members are singled out, keep the count rule's
  split instead: the named one(s) + a remainder count.)

WORKED EXAMPLES (these show the CONVENTIONS; do NOT copy their content — extract from the
REPORT below):
# A. Figure plate enumerated by number -> one row per vessel:
#   text: "Fig. 5. Aardewerk uit kuil 12: 1. ruwwandige kookpot; 2. gladwandige kruik; 3. wrijfschaal Stuart 149."
#   -> [{"pottery":"Cooking pot","typology":"","original_text":"1. ruwwandige kookpot","page":5},
#       {"pottery":"Jug","typology":"","original_text":"2. gladwandige kruik","page":5},
#       {"pottery":"Mortarium","typology":"Stuart 149","original_text":"3. wrijfschaal Stuart 149","page":5}]
# B. Registration-only numbers -> the NUMBER is the pottery name, typology empty:
#   text: "Fig. XVI.2. Examples of Late Roman vessels: 22-3-6/4056, 711-1/13-1-27."
#   -> [{"pottery":"22-3-6/4056","typology":"","start_date":275,"end_date":450,"original_text":"Examples of Late Roman vessels: 22-3-6/4056","page":1},
#       {"pottery":"711-1/13-1-27","typology":"","start_date":275,"end_date":450,"original_text":"22-3-6/4056, 711-1/13-1-27","page":1}]
# C. Merge a recap, keep distinct finds:
#   text: "Two terra sigillata bowls were found: find 3 (Drag. 37) and find 7 (Drag. 18). ... The two sigillata bowls date the layer."
#   -> [{"pottery":"Terra sigillata","typology":"Drag. 37","original_text":"find 3 (Drag. 37)"},
#       {"pottery":"Terra sigillata","typology":"Drag. 18","original_text":"find 7 (Drag. 18)"}]
#   (the later "two sigillata bowls" is the SAME two finds -> NOT extra rows)
# D. A PLATE where vessels are a COLUMN of bare find/registration numbers split by the caption
#    line -> emit EVERY number as its own find (NOT only the one beside the caption):
#    text (one per line): "22-3-6/4056
#                          513-2/20-1-67
#                          Fig. XVI.2. Examples of Late Roman vessels.
#                          711-1/13-1-27
#                          791-1/95-2-22"
#    -> one row PER number, all of them: 22-3-6/4056, 513-2/20-1-67, 711-1/13-1-27, 791-1/95-2-22
#       (pottery = the number, typology = "", and the caption "Late Roman vessels" dates them 275..450)
# E. A colour / fabric QUALIFIER makes a DISTINCT find -> split by qualifier:
#    text: "rood ruwwandig en wit gladwandig aardewerk" / "red rough-walled and white smooth-walled pottery"
#    -> [{"pottery":"Red rough-walled pottery","typology":"","original_text":"rood ruwwandig ... aardewerk"},
#        {"pottery":"White smooth-walled pottery","typology":"","original_text":"wit gladwandig aardewerk"}]
# F. A COUNT never multiplies rows -> ONE row per form/type, count goes in "quantity":
#    text: "Er werden drie kruiken en twee kommen gevonden." / "Two bowls were found."
#    -> [{"pottery":"Jug","quantity":3,"original_text":"drie kruiken"},
#        {"pottery":"Bowl","quantity":2,"original_text":"twee kommen"}]   (2 rows, one per FORM, NOT 5)
#    "27 potten" -> 1 Pot row, quantity 27. "vijf scherven gladwandig aardewerk" -> 1 row, quantity 5
#    (sherds are pieces). BUT individually-DISTINGUISHED vessels of one ware STAY separate (different
#    stamp/decoration/typology/date/findspot):
#    text: "t.s.-kommetje met stempel OF MIM" + "t.s.-kommetje met stempel SECVND.M (Drag. 27)"
#    -> [{"pottery":"Terra sigillata bowl","typology":"","quantity":1,"original_text":"...OF MIM..."},
#        {"pottery":"Terra sigillata bowl","typology":"Drag. 27","quantity":1,"original_text":"...SECVND.M..."}]
#    And a singled-out item splits off: "drie potten ... een hiervan is een klok-beker"
#    -> Bell-beaker (quantity 1) + Pot (quantity 2).

SELF-CHECK before you return — scan your finds and DELETE any redundant group/preview row:
- if you listed a GROUP/COUNT row ("drie potten", "27 potten") AND also listed those same vessels
  individually, KEEP only the individual rows and DELETE the group row;
- if you listed a multi-form LIST row ("borden, kommen, urnen, deksels") AND also listed those forms
  as their own rows, KEEP only the individual form rows and DELETE the list row.
The group/list row and its members are the SAME finds — never return both.
Also confirm every "site": strip COMMA findspot/street/feature qualifiers down to the town ("Heerlen,
Promenade" -> "Heerlen"), but KEEP hyphenated site names intact ("Voerendaal-Ten Hove" stays).

Return ONLY a JSON array for the REPORT below (no prose, no markdown fences).

REPORT:
__REPORT__
"""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


# Q3 date backfill: deterministic period gazetteer, derived from the single source of truth
# (src/periods.py) so the broad named periods the rule date-parser's regex misses stay in sync
# with the prompt + chron_vocab. Used ONLY on a find's OWN quote, so it can't bleed a neighbour.
from src.periods import gazetteer as _gazetteer        # noqa: E402
_PERIOD_GAZETTEER = _gazetteer()                       # [(compiled_regex, start, end)], specific first


def _period_date_from_quote(quote: str):
    """Find-faithful date from the find's OWN quote only (no cross-item context bleed): try the
    deterministic date-signal parser (centuries/years/qualified-Roman), else the broad-period
    gazetteer. Returns (start, end) or None."""
    from src.date_parser import extract_date_signals
    sigs = extract_date_signals(quote or "")
    if sigs:
        s = min(sigs, key=lambda d: (d["end"] - d["start"]))   # prefer the most specific span
        return s["start"], s["end"]
    for rx, a, b in _PERIOD_GAZETTEER:
        if rx.search(quote or ""):
            return a, b
    return None


def _ground_typology(typology: str, lookup: Dict[str, Tuple[int, int, str]]
                     ) -> Optional[Tuple[int, int, str, str]]:
    """Canonical (date_start, date_end, pot_name_en, full_typology_code) for a typology code,
    expanding common abbreviations first. Returns None if the code is unknown.

    Grouped codes ("Stuart 103/Oberaden 43", "Lamboglia 2/Dressel 6A") join two type-codes for ONE
    vessel: the date + name come from the FIRST component that grounds (left-to-right), while the
    output code keeps the WHOLE group (each component canonicalised, joined by "/"). Only "/" splits
    a group; "-" (e.g. "Dressel 7-11") is a within-series range and is never split."""
    from src.detection import _canon_code
    if not typology:
        return None
    t = typology.strip()
    t = re.sub(r"(?i)\bdrag\.?\b", "Dragendorff", t)
    t = re.sub(r"(?i)\bstu\.?\b", "Stuart", t)
    t = re.sub(r"(?i)\bnieder\.?\b|\bnb\b", "Niederbieber", t)
    t = re.sub(r"(?i)\balz\.?\b|\balzei\b", "Alzey", t)
    t = re.sub(r"(?i)\btype\b|\btyp\.?\b", " ", t)
    # Option A: a tentative attribution ("NB 104 cf.", "vgl. Drag. 37", "Alzey 28?") still grounds
    # to the BASE type — strip the hedge so it matches Master. The uncertainty is carried by a low
    # pot_name_certainty (the caller caps it via _is_tentative), NOT by failing the date lookup.
    t_base = _TENTATIVE_RE.sub(" ", t).strip()

    def _ground_one(code: str):
        cb = _TENTATIVE_RE.sub(" ", code).strip()
        return lookup.get(_canon_code(code)) or lookup.get(_canon_code(cb))

    for cand in (t, t_base, typology):
        hit = lookup.get(_canon_code(cand))
        if hit:
            return hit
    # Grouped code: ground the first component that resolves; keep the full group as the code.
    if "/" in t:
        comps = [c.strip() for c in t.split("/") if c.strip()]
        if len(comps) >= 2:
            primary, canon_codes = None, []
            for c in comps:
                hit = _ground_one(c)
                if hit and primary is None:
                    primary = hit
                canon_codes.append(hit[3] if hit else c)   # canonical code when known, else as-is
            if primary:
                ds, de, name, _ = primary
                return (ds, de, name, "/".join(canon_codes))
    return None


# Structured-outputs schema: the API guarantees valid JSON matching this, so a verbatim
# quote containing a `"` (e.g. „Cnaeus Ateius") can no longer break parsing and silently
# drop a whole report's finds. All keys required; optional values use nullable types.
_FIND_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "pottery": {"type": "string"},
        "typology": {"type": "string"},
        "term": {"type": "string"},
        "site": {"type": "string"},
        "quantity": {"type": ["integer", "null"]},
        "start_date": {"type": ["integer", "null"]},
        "end_date": {"type": ["integer", "null"]},
        "original_text": {"type": "string"},
        "page": {"type": ["integer", "null"]},
        "pot_name_certainty_level": {"type": ["integer", "null"]},
        "pot_name_llm_reasoning": {"type": "string"},
        "pot_presence_certainty_level": {"type": ["integer", "null"]},
        "pot_presence_llm_reasoning": {"type": "string"},
        "specific_object": {"type": "boolean"},
    },
    "required": ["pottery", "typology", "term", "site", "quantity", "start_date", "end_date",
                 "original_text", "page", "pot_name_certainty_level", "pot_name_llm_reasoning",
                 "pot_presence_certainty_level", "pot_presence_llm_reasoning", "specific_object"],
    "additionalProperties": False,
}
_FIND_SCHEMA = {
    "type": "object",
    "properties": {"finds": {"type": "array", "items": _FIND_ITEM_SCHEMA}},
    "required": ["finds"],
    "additionalProperties": False,
}


def _extract_tables_md(pdf_path) -> str:
    """Recover finds TABLES as markdown grids (PyMuPDF find_tables) so the model can count rows
    that prose-flattening destroys (e.g. table_1's 'amphora|Mayen R19|N=1', table_5's indeterminate
    'Belgische waar' rows). Returns "" for image-only/OCR PDFs with no text-layer tables."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
    except Exception:
        return ""
    out = []
    for pi, pg in enumerate(doc, 1):
        try:
            tabs = pg.find_tables()
        except Exception:
            continue
        for ti, t in enumerate(tabs.tables, 1):
            try:
                md = t.to_markdown()
            except Exception:
                try:
                    rows = t.extract()
                    md = "\n".join(" | ".join((c or "").replace("\n", " ") for c in r) for r in rows)
                except Exception:
                    md = ""
            if md and md.strip():
                out.append(f"[[p{pi} table {ti}]]\n{md.strip()}")
    return "\n\n".join(out)


def _hybrid_llm(prompt: str) -> str:
    """Pick the extraction backend (see config): the Claude Code CLI on a Max/Pro
    subscription, else the Anthropic API (with structured outputs), else the configured cloud
    LLM (so it runs without any Claude access for testing the architecture)."""
    from config import WORKFLOW_MODE, HYBRID_USE_CLAUDE_CLI
    if WORKFLOW_MODE == "claude":           # pure Claude: never touches the cloud/local Llama path
        if HYBRID_USE_CLAUDE_CLI:
            from src.llm_client import call_claude_cli
            return call_claude_cli(prompt)
        from src.llm_client import call_claude
        # structured outputs -> guaranteed-valid JSON (no `"`-in-quote parse failures)
        # Generous read timeout: a finds-dense window's ~16k-token output finishes server-side before
        # any byte returns (non-streaming), so it needs more than the default 180s. Smaller windows
        # (_chunk_budget) keep output bounded; the salvage parser recovers finds if a window overflows.
        return call_claude(prompt, max_tokens=16000, output_schema=_FIND_SCHEMA, timeout=600)
    # cloud-llama / local-llama: the configured provider (LLM_PROVIDER); never calls Claude.
    from src.llm_client import call_llm
    return call_llm(prompt, max_tokens=16000)


def _hybrid_backend() -> str:
    """Short tag for the model the hybrid extractor actually uses, so date_method reflects the
    real backend instead of hardcoding 'claude'. Mirrors the provider choice in _hybrid_llm():
    WORKFLOW_MODE == 'claude' -> 'claude'; otherwise the cloud/local model family
    (e.g. 'llama', 'qwen', 'deepseek') derived from the configured model id."""
    from config import WORKFLOW_MODE
    if WORKFLOW_MODE == "claude":
        return "claude"
    from config import LLM_PROVIDER, LLM_API_MODEL, LLM_MODEL
    model = ((LLM_MODEL if LLM_PROVIDER == "ollama" else LLM_API_MODEL) or "").lower()
    for fam in ("llama", "qwen", "deepseek", "mistral", "gemma", "gpt"):
        if fam in model:
            return fam
    return "llm"


def _salvage_objects(s: str) -> List[Dict]:
    """Recover every COMPLETE {...} object from a (possibly truncated) finds array — e.g. when a
    finds-dense window's output was cut at max_tokens mid-array, so the whole-string parse fails.
    Decodes objects one at a time from the array start and stops at the first incomplete/garbled
    one, keeping all the finds before the cut. (Without this, a single truncation loses the whole
    window — the bug that made 12707 return 0 despite a valid 43k-char prefix of real finds.)"""
    m = re.search(r'"(?:finds|mentions)"\s*:\s*\[', s)
    start = (m.end() - 1) if m else s.find("[")
    if start == -1:
        return []
    dec = json.JSONDecoder()
    out: List[Dict] = []
    i, n = start + 1, len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":   # skip separators
            i += 1
        if i >= n or s[i] == "]":
            break
        if s[i] != "{":
            break
        try:
            obj, i = dec.raw_decode(s, i)      # parse one object; advance past it
        except json.JSONDecodeError:
            break                              # truncated/garbled object -> stop, keep the rest
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _coerce_list(data) -> List[Dict]:
    """Accept either a bare array of finds or the structured-outputs object {"finds":[...]}."""
    if isinstance(data, dict):
        data = data.get("finds") or data.get("mentions") or []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def _parse_json_array(raw: str) -> List[Dict]:
    if not raw:
        return []
    s = raw.strip()
    if "```" in s:                                  # strip markdown fences
        s = re.sub(r"```(?:json)?", "", s)
    s = s.strip()
    # Structured outputs returns a clean JSON object/array — try a whole-string parse first.
    try:
        return _coerce_list(json.loads(s))
    except json.JSONDecodeError:
        pass
    # Fallback for raw-text replies (CLI / cloud-LLM paths): slice the outermost [...] or {...}.
    lo = min([i for i in (s.find("["), s.find("{")) if i != -1], default=-1)
    hi = max(s.rfind("]"), s.rfind("}"))
    if lo == -1 or hi <= lo:
        return []
    chunk = s[lo:hi + 1]
    try:
        return _coerce_list(json.loads(chunk))
    except json.JSONDecodeError:
        chunk = re.sub(r",\s*([\]}])", r"\1", chunk)  # trailing commas
        try:
            return _coerce_list(json.loads(chunk))
        except json.JSONDecodeError:
            # Last resort: the array was likely TRUNCATED at max_tokens (a finds-dense window) -
            # salvage every complete object before the cut instead of losing the whole window.
            return _salvage_objects(s)


def _to_int(x):
    if x is None or x == "":
        return ""
    try:
        return int(x)
    except (TypeError, ValueError):
        m = re.match(r"-?\d+", str(x))
        return int(m.group()) if m else ""


def _expand_typ(typ: str) -> str:
    t = (typ or "").strip()
    t = re.sub(r"(?i)\bdrag\.?\b", "Dragendorff", t)
    t = re.sub(r"(?i)\bstu\.?\b", "Stuart", t)
    t = re.sub(r"(?i)\bnieder\.?\b|\bnb\b", "Niederbieber", t)
    t = re.sub(r"(?i)\balz\.?\b|\balzei\b", "Alzey", t)
    return t


# Light singular/plural folding for the 5c ware key only: collapses the SAME ware written
# singular vs plural so the surplus check doesn't re-add a duplicate (rule "Dolia" == the model's
# "Dolium"). Deliberately NARROW — Latin -a/-ae plurals + a generic English -s — so it does NOT
# merge cross-form synonyms (jug/kruik/flagon), which would risk hiding a genuine rule miss.
_LATIN_PLURAL = {"dolia": "dolium", "mortaria": "mortarium", "amphorae": "amphora",
                 "ollae": "olla", "lagoenae": "lagoena", "paterae": "patera"}


def _singularize(w: str) -> str:
    if w in _LATIN_PLURAL:
        return _LATIN_PLURAL[w]
    if len(w) > 4 and w.endswith("s"):     # beakers->beaker, bowls->bowl
        return w[:-1]
    return w


# Fabric/firing qualifiers that the hybrid (Q1) adds to a name but the rule pipeline usually omits
# ("Coarse oxidized plate" vs "Plate"). Stripped from the 5c DEDUP KEY ONLY (not the displayed
# name) so the two sides compare on form and the 5c stops re-adding finds the model already has.
# Colour (red/white/grey) and surface (rough/smooth/varnished/walled) are NOT stripped — those
# distinguish genuinely different wares (per the prompt's split-by-qualifier rule).
_DEDUP_STRIP = {"coarse", "fine", "oxidized", "oxidised", "reduced"}


# Cross-engine ware SYNONYMS, folded in the dedup key ONLY (not the displayed name): the rule
# pipeline says "Grinding bowl" where the model says "Mortarium", "Flagon" where it says "Jug".
# Folding them stops the 5c re-adding a find the model already has under a synonymous name. Phrase-
# level (so "grinding bowl" collapses to one token, not "mortarium bowl").
_WARE_SYNONYM = [
    (re.compile(r"grinding\s*bowls?|wrijfscha\w+|mortaria"), "mortarium"),
    (re.compile(r"\bjugs?\b|kruik\w*|\bkann?en?\b|pitchers?"), "flagon"),
]


def _ware_key(pot: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", (pot or "").lower())          # drop (provenance) parentheticals
    for rx, rep in _WARE_SYNONYM:
        s = rx.sub(rep, s)
    words = [_singularize(w) for w in re.findall(r"[a-z0-9]+", s) if w not in _DEDUP_STRIP]
    # fall back to the full normalised name if stripping left nothing (e.g. "Coarse ware")
    return "".join(words) or "".join(_singularize(w) for w in re.findall(r"[a-z0-9]+", (pot or "").lower()))


def _tkey(pot: str, typ: str) -> str:
    """Group key for a find: its typology code if present, else its normalised ware name.
    Lets us compare rule vs model finds at the multiset level (per-ware counts)."""
    from src.detection import _canon_code
    c = _canon_code(_expand_typ(typ)) if (typ or "").strip() else ""
    return c or _ware_key(pot)


# ---- certainty helpers (shared by hybrid + rule export; see column docs) --------------------
def _clamp10(x):
    return x if x == "" else max(0, min(10, x))


# Tentative-attribution markers ("NB 104 cf.", "vgl. Drag. 37", "Alzey 28?"). We still ground
# such codes to the BASE type (Option A) but cap the name certainty low.
_TENTATIVE_RE = re.compile(r"(?i)\b(cf|vgl|conf|confer)\.?\b|\?")


def _is_tentative(typ: str) -> bool:
    return bool(typ) and bool(_TENTATIVE_RE.search(typ))


# A diminutive is a grammatical form, not a size: Dutch -je/-tje/-pje/-kje (+plural -s),
# German -chen/-lein, French -et/-ette. Used only to RECOGNISE the source term as diminutive.
_DIMINUTIVE_RE = re.compile(r"(?:tje|pje|kje|je|chen|lein|ett?e?)s?$", re.IGNORECASE)
_SMALL_PREFIX_RE = re.compile(r"^(?:small|little)\s+", re.IGNORECASE)


def _undiminish(name: str, term: str) -> str:
    """Backstop for the prompt's diminutive rule: if the model still rendered a grammatical
    diminutive as a SIZE ("schaaltjes" -> "Small dish"), drop the "Small "/"Little " so the base
    vessel form remains ("Dish"). Gated on the SOURCE term actually being a diminutive, so a real
    "small ..." qualifier (none exist in this controlled vocab anyway) is left untouched."""
    if not (name and term and _SMALL_PREFIX_RE.match(name)):
        return name
    if not any(_DIMINUTIVE_RE.search(w) for w in re.split(r"[\s\-]+", term) if w):
        return name
    base = _SMALL_PREFIX_RE.sub("", name).strip()
    return (base[0].upper() + base[1:]) if base else name


# How confident we are that the OUTPUT date is justified by the report (NOT how precise it is) —
# keyed by date_method. Typology-grounded dates are special: only as certain as the identification.
_DATE_CERT = {
    "text_explicit":  (9, "explicit date stated in the passage"),
    "text_century":   (9, "century stated in the passage"),
    "chron_vocab":    (8, "named dated period/ware"),
    "period_term":    (8, "period word in the find's own quote"),
    "section_phase":  (6, "inherited from the section/phase date"),
    "llm_context":    (5, "inferred from surrounding context"),
    "context_clamp":  (3, "missing endpoint clamped to the Roman period"),
    "report_context": (1, "defaulted to the Roman period from excavation context"),
}


def _date_certainty(date_method, name_cert, has_date):
    """(score 0-10, one-line reason) for the output date. Typology-derived dates inherit the
    name certainty (so a tentative 'cf.' type yields a low date certainty too).

    Method labels are model-agnostic: the LLM-backend part is a runtime tag (claude / llama / …),
    so the model-dependent methods are matched by semantic SHAPE rather than a hardcoded name:
      "<backend>+typology" or "typology" -> dated from a typology code
      "<backend>_text"                   -> date read from the passage by the model
      "rules+<backend>_confirmed"        -> rule-detected date, model-confirmed presence
    """
    if not has_date:
        return 0, "no date stated"
    dm = date_method or ""
    if dm == "typology" or dm.endswith("+typology"):
        nc = name_cert if isinstance(name_cert, int) else 8
        return nc, "dated from typology code (only as certain as the identification)"
    if dm.endswith("_text"):
        return 8, "date read from the passage"
    if dm.startswith("rules+") and dm.endswith("_confirmed"):
        return 6, "date from the rule detector, presence confirmed"
    return _DATE_CERT.get(dm, (0, "no date stated"))


def _overall(*vals):
    nums = [v for v in vals if isinstance(v, int)]
    return round(sum(nums) / len(nums)) if nums else ""


def _roman_period_clamp(ds, de):
    """One-sided date fill: if EXACTLY one endpoint is set and it sits within the Roman period,
    clamp the missing endpoint to the Roman period bound ("2nd century or later" -> end 450;
    "until the 3rd century" -> start -12). Returns (ds, de, clamped?). Both-empty / both-set are
    left untouched (per decision: context-less undated finds stay undated)."""
    from config import ROMAN_PERIOD
    ps, pe = ROMAN_PERIOD
    s_empty, e_empty = (ds == ""), (de == "")
    if s_empty == e_empty:
        return ds, de, False
    if e_empty and isinstance(ds, int) and ds <= pe:        # have start, fill end
        return ds, max(pe, ds), True
    if s_empty and isinstance(de, int) and de >= ps:        # have end, fill start
        return min(ps, de), de, True
    return ds, de, False


_CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "label": {"type": "string",
                      "enum": ["present", "comparison", "absent", "duplicate", "non_pottery"]},
            "confidence": {"type": "number"},
        },
        "required": ["index", "label", "confidence"],
        "additionalProperties": False,
    }}},
    "required": ["results"],
    "additionalProperties": False,
}

_CONFIRM_PROMPT = """\
You already extracted the pottery finds from the report below. A rule-based detector flagged these
ADDITIONAL candidates you did NOT list. For EACH candidate, classify it using ONLY the report text
and the CONTEXT shown for it:
- "present": a genuine pottery vessel/ware actually RECOVERED at a site in this report, and DISTINCT
  from finds already counted.
- "comparison": named only as a parallel / comparison / typological citation / cross-reference — not
  a find recovered here.
- "absent": stated to be NOT found / not present.
- "duplicate": the SAME physical find as one already counted — even under a DIFFERENT name
  (the rule detector says "Grinding bowl" for your "Mortarium", "Flagon" for your "Jug"). COMPARE
  the candidate's CONTEXT/quote against the QUOTES of the already-listed finds below: if it evidences
  the SAME object (same or clearly-overlapping passage AND the same vessel, with an overlapping
  date), label it "duplicate". BUT two DIFFERENT vessels described in the SAME sentence are NOT
  duplicates — only the same physical object is.
- "non_pottery": not pottery (coin/munt, tile/tegula/dakpan, glass, bronze, quern/maalsteen,
  flint/vuursteen) or not a find at all.
Also give a confidence 0.0-1.0 for your label. Be strict: if the context does not clearly show the
item was recovered here as a distinct find, do NOT label it "present".

FINDS YOU ALREADY LISTED (do NOT re-add these — if a candidate is the SAME physical find as one of
these, label it "duplicate", even if the candidate uses a different name). Each is shown as
"name (typology) [date range]: quote" — compare the candidate's quote to these:
__ALREADY_LISTED__

CANDIDATES (index | pottery | typology | date | CONTEXT):
__CANDIDATES__

REPORT:
__REPORT__

Return a result for EVERY candidate index.
"""


def _context_window(quote: str, report_text: str, pad: int = 240) -> str:
    """Locate the candidate's quote in the report and return it with surrounding context, so the
    confirm step can judge present-vs-mention (the rules' main failure mode)."""
    if not quote:
        return quote
    i = report_text.find(quote)
    if i < 0 and len(quote) > 60:
        i = report_text.find(quote[:60])
    if i < 0:
        return quote
    a, b = max(0, i - pad), min(len(report_text), i + len(quote) + pad)
    return report_text[a:b].replace("\n", " ").strip()


def _confirm_llm(prompt: str) -> str:
    from config import WORKFLOW_MODE, HYBRID_USE_CLAUDE_CLI
    if WORKFLOW_MODE == "claude":           # pure Claude: never falls through to call_llm/Llama
        if HYBRID_USE_CLAUDE_CLI:
            from src.llm_client import call_claude_cli
            return call_claude_cli(prompt)
        from src.llm_client import call_claude
        return call_claude(prompt, max_tokens=2000, output_schema=_CONFIRM_SCHEMA)
    # cloud-llama / local-llama: the configured provider (LLM_PROVIDER); never calls Claude.
    from src.llm_client import call_llm
    return call_llm(prompt, max_tokens=2000)


def _drange(ds, de) -> str:
    """Compact date-range tag for the confirm step, so the model can spot date-based duplicates."""
    ds, de = _to_int(ds), _to_int(de)
    if ds == "" and de == "":
        return "no date"
    return f"{ds if ds != '' else '?'}..{de if de != '' else '?'}"


def _rule_confirm_merge(rows, rule_csv, report_text, lookup, report_id, cache_path=None):
    """Option 5c: offer the rule pipeline's per-ware SURPLUS finds (those the model didn't emit)
    back to the model; keep only the ones it confirms. Returns (extra_rows, n_confirmed, n_candidates)."""
    from collections import Counter, defaultdict
    from config import POTTERY_HYBRID_CONFIRM_THRESHOLD as THR
    if not rule_csv or not Path(rule_csv).exists():
        return [], 0, 0
    backend = _hybrid_backend()
    # #4 pre-filter: only consider rule finds the RULES themselves judged present (drop the ones
    # the rule pipeline labelled absent / comparison / citation / irrelevant — via context_label,
    # the kept categorical; llm_find_status was removed from the output).
    _drop_ctx = {"absent", "comparison", "citation", "irrelevant"}
    rule_finds = []
    with open(rule_csv, encoding="utf-8") as fh:
        for d in csv.DictReader(fh):
            pot = (d.get("pottery") or "").strip()
            if not pot:
                continue
            if d.get("context_label", "") in _drop_ctx:
                continue
            rule_finds.append({"pottery": pot, "typology": (d.get("typology") or "").strip(),
                               "start_date": d.get("start_date", ""), "end_date": d.get("end_date", ""),
                               "original_text": (d.get("original_text") or "").strip(),
                               "site": (d.get("site_name") or "").strip(), "page": d.get("page", "")})
    model_ct = Counter(_tkey(r["pottery"], r["typology"]) for r in rows)
    by_key = defaultdict(list)
    for rf in rule_finds:
        by_key[_tkey(rf["pottery"], rf["typology"])].append(rf)
    candidates = []
    for k, rfs in by_key.items():
        surplus = len(rfs) - model_ct.get(k, 0)      # finds the model is "short" on for this ware
        if surplus > 0:
            candidates += rfs[:surplus]
    if not candidates:
        return [], 0, 0
    # #3 show the model its own finds so it can flag true duplicates (compact, deduped)
    already = "\n".join(
        f'- {r["pottery"]}{" (" + r["typology"] + ")" if r["typology"] else ""}'
        f' [{_drange(r.get("start_date"), r.get("end_date"))}]: "{(r.get("original_text") or "")[:140]}"'
        for r in sorted(rows, key=lambda r: r["pottery"].lower())) or "(none)"
    # #1 full context per candidate, with its date so the model can judge date-based duplicates
    listing = "\n".join(
        f'{i} | {c["pottery"]} | typ={c["typology"] or "-"} | date={_drange(c.get("start_date"), c.get("end_date"))}'
        f' | "{_context_window(c["original_text"], report_text)}"'
        for i, c in enumerate(candidates))
    # Each candidate already carries its own _context_window (from the FULL report_text above); the
    # global __REPORT__ here is supplementary, so cap it to the chunk budget so a huge document
    # doesn't overflow the confirm call's context.
    raw = _confirm_llm(_CONFIRM_PROMPT
                       .replace("__ALREADY_LISTED__", already)
                       .replace("__CANDIDATES__", listing)
                       .replace("__REPORT__", report_text[:_chunk_budget(backend)]))
    # #2/#6 parse {results:[{index,label,confidence}]}
    labels = {}   # index -> (label, confidence)
    try:
        data = json.loads(raw.strip().strip("`"))
        for r in (data.get("results", []) if isinstance(data, dict) else []):
            labels[int(r["index"])] = (r.get("label", ""), float(r.get("confidence", 0)))
    except (ValueError, AttributeError, TypeError, KeyError):
        pass
    # cache every candidate's label+confidence so the THR knob can be swept without re-calling
    if cache_path:
        try:
            with open(cache_path, "w", newline="", encoding="utf-8") as cf:
                cw = csv.writer(cf)
                cw.writerow(["index", "pottery", "typology", "label", "confidence", "original_text"])
                for i, c in enumerate(candidates):
                    lab, conf = labels.get(i, ("", 0.0))
                    cw.writerow([i, c["pottery"], c["typology"], lab, conf, c["original_text"][:200]])
        except OSError:
            pass
    confirmed = {i for i, (lab, conf) in labels.items() if lab == "present" and conf >= THR}
    extra = []
    for i, c in enumerate(candidates):
        if i not in confirmed:
            continue
        typ, pot = c["typology"], c["pottery"]
        ds, de = _to_int(c["start_date"]), _to_int(c["end_date"])
        g = _ground_typology(typ, lookup)
        if g:
            ds, de, gn, gc = g
            if gn:
                pot = gn
            if gc:
                typ = gc + (" cf." if _is_tentative(typ) else "")
        pres_cert = max(0, min(10, round(labels[i][1] * 10)))   # confirm confidence -> presence
        name_cert = 8 if typ else 6                              # typed = more certain name
        # if the row was typology-grounded, the date is type-derived (certainty tied to name);
        # otherwise it's a plain rule date.
        date_cert, date_reason = _date_certainty("typology" if g else f"rules+{backend}_confirmed",
                                                 name_cert, ds != "" or de != "")
        extra.append({
            "report_id": report_id, "site_name": c["site"], "page": _to_int(c["page"]),
            "pottery": pot, "typology": typ, "term_found": typ or pot, "term_found_normalized_en": pot,
            "start_date": ds, "end_date": de,
            "date_method": f"rules+{backend}_confirmed", "context_label": "present",
            "pot_name_certainty_level": name_cert,
            "pot_name_llm_reasoning": "rule candidate; name from " + ("typology code" if typ else "ware match"),
            "pot_presence_certainty_level": pres_cert,
            "pot_presence_llm_reasoning": f"rule candidate confirmed present by {backend} (5c)",
            "dates_certainty_level": date_cert,
            "date_llm_reasoning": date_reason,
            "overall_certainty_level": _overall(name_cert, pres_cert, date_cert),
            "original_text": c["original_text"],
        })
    return extra, len(extra), len(candidates)


# Registration/find numbers in a catalogue entry ("--/95-1-19/10813, Drag. 37 …", "304-1/20-5-8",
# "744-9/100-1-10/...", "--/16-3-7/2427+2428"). Found ANYWHERE in the quote (the LLM leads with it,
# but the rule layer prefixes descriptive context — "…AD 50-70.\n304-1/20-5-8, Drag. 29"), at a token
# boundary. Require >=3 numeric segments joined by -/+ AND a "/" so dates ("19-16"), figure numbers
# ("2.13"), bare form codes ("Stuart 133/Oberaden 52" -> no digit after "/") and layer codes never match.
_REGNUM = re.compile(r'(?<![\w./+-])(-{0,2}/?\d[\d.]*(?:[-/+]\d[\d.]*){2,})')

# CAI (Flemish Centrale Archeologische Inventaris) inventory format: each find block is headed by a
# standalone 6-digit location code, and that code — not the toponym that appears only inside a
# "Bron:" citation — is the authoritative per-find site key. A 6-digit line alone is too weak a
# signal (a stray number could trip it), so we require >=2 such codes AND a corroborating marker:
# "NK:" (the CAI location-accuracy field), an investigation keyword, or an explicit CAI mention.
_CAI_CODE_RE = re.compile(r"^[ \t]*(\d{6})[ \t]*$", re.MULTILINE)
_CAI_CORROB_RE = re.compile(
    r"NK:\s*\d|Veldprospectie|Metaaldetectie|Opgraving|Toevalsvondst|"
    r"Historisch onderzoek|Centrale Archeologische Inventaris|\bCAI\b",
    re.IGNORECASE,
)


def _apply_cai_site_codes(rows: List[Dict], report_text: str) -> int:
    """Override each find's site_name with its CAI inventory code, but only when the report is clearly
    a CAI inventory (>=2 standalone codes AND a corroborating marker). Each code owns the text block
    from its line to the next code; a find is assigned the code of the block that UNIQUELY contains
    its verbatim original_text quote. Boilerplate quotes that recur across several coded blocks (e.g.
    identical "Romeinse tijd: ... Romeinse villa ... aardewerk" prospection entries) are ambiguous
    and left untouched rather than guessed — so the override never introduces a WRONG code.
    Deterministic and a no-op on every non-CAI report. Returns the count of rows overridden."""
    # Use only the flowing page text, not the appended table-markdown re-render: the standalone
    # 6-digit codes live in the flowing text, and including the markdown copy would make every
    # description match two blocks (flowing + table) and look ambiguous.
    text = (report_text or "").split(_TABLES_HEADER, 1)[0]
    matches = list(_CAI_CODE_RE.finditer(text))
    if len(matches) < 2 or not _CAI_CORROB_RE.search(text):
        return 0

    # Each code owns text from its line end to the next code line.
    blocks = [
        (m.group(1), text[m.end():(matches[i + 1].start() if i + 1 < len(matches) else len(text))])
        for i, m in enumerate(matches)
    ]

    def unique_owner(quote: str) -> str:
        # Prefer the full quote; fall back to a shorter prefix only if the full quote matches no
        # block (whitespace drift). Assign only when exactly one block contains the needle.
        for needle in (quote, quote[:60]):
            if not needle:
                continue
            owners = [code for code, body in blocks if needle in body]
            if len(owners) == 1:
                return owners[0]
            if owners:           # found in >1 block -> ambiguous, do not fall back to a looser match
                return ""
        return ""

    n = 0
    for r in rows:
        quote = (r.get("original_text") or "").strip()
        if not quote:
            continue
        code = unique_owner(quote)
        if code and (r.get("site_name") or "") != code:
            r["site_name"] = code
            n += 1
    return n


def _extract_regnum(text: str) -> str:
    """The catalogue registration/find number in a find's quote, or '' when there is none (the common
    case for prose/table finds, which are then left untouched). Returns the first '/'-bearing match."""
    for m in _REGNUM.finditer(text or ""):
        g = m.group(1)
        if "/" in g:
            # Strip a leading ditto/omitted-prefix marker so the SAME catalogue number written
            # "--/16-3-7/2427+2428" and "16-3-7/2427+2428" keys identically (else the two rows
            # escape the reg# union and the find is double-counted).
            return g.lstrip("-/")
    return ""


def _row_richer(a: Dict, b: Dict) -> bool:
    """True if row a is a richer representation than b (prefer a grounded typology, then a date, then
    higher overall certainty) — used to choose which duplicate of one reg# to keep."""
    def score(r):
        oc = r.get("overall_certainty_level")
        return (1 if (r.get("typology") or "").strip() else 0,
                1 if (r.get("start_date") not in ("", None) or r.get("end_date") not in ("", None)) else 0,
                oc if isinstance(oc, int) else 0)
    return score(a) > score(b)


def _row_from_rule_find(rf: Dict, lookup: Dict, report_id: str, backend: str) -> Dict:
    """Build an output row from a rule-layer catalogue find (used to recover a reg# entry the LLM
    dropped). Mirrors the 5c extra-row build: ground the typology, derive certainties."""
    typ, pot = (rf.get("typology") or "").strip(), (rf.get("pottery") or "").strip()
    ds, de = _to_int(rf.get("start_date")), _to_int(rf.get("end_date"))
    g = _ground_typology(typ, lookup)
    if g:
        ds, de, gn, gc = g
        if gn:
            pot = gn
        if gc:
            typ = gc + (" cf." if _is_tentative(typ) else "")
    name_cert = 8 if typ else 6
    pres_cert = 7
    date_cert, date_reason = _date_certainty("typology" if g else f"rules+{backend}", name_cert,
                                             ds != "" or de != "")
    return {
        "report_id": report_id, "site_name": (rf.get("site") or "").strip(), "page": _to_int(rf.get("page")),
        "pottery": pot, "typology": typ, "term_found": typ or pot, "term_found_normalized_en": pot,
        "quantity": "", "start_date": ds, "end_date": de,
        "date_method": f"rules+{backend}", "context_label": "present",
        "pot_name_certainty_level": name_cert,
        "pot_name_llm_reasoning": "catalogue entry (registration no.) recovered from the rule layer",
        "pot_presence_certainty_level": pres_cert,
        "pot_presence_llm_reasoning": "catalogued find carrying a registration number",
        "dates_certainty_level": date_cert, "date_llm_reasoning": date_reason,
        "overall_certainty_level": _overall(name_cert, pres_cert, date_cert),
        "original_text": (rf.get("original_text") or "").strip(),
    }


def _regnum_union(rows: List[Dict], rule_csv, lookup: Dict, report_id: str, backend: str):
    """Deterministic stabiliser for registration-numbered catalogues: key reg#-bearing finds by their
    reg#. Collapse LLM duplicates of one reg# (over-emission) and add reg# entries the rule layer found
    but the LLM dropped (under-emission), so the catalogue count == the distinct reg# set on EVERY run.
    Finds WITHOUT a reg# are left completely untouched, so non-catalogue reports are a no-op.
    Returns (rows, n_deduped, n_recovered)."""
    by_reg, no_reg, deduped = {}, [], 0
    for r in rows:
        rg = _extract_regnum(r.get("original_text", ""))
        if not rg:
            no_reg.append(r)
        elif rg in by_reg:
            deduped += 1
            if _row_richer(r, by_reg[rg]):
                by_reg[rg] = r
        else:
            by_reg[rg] = r
    recovered = 0
    if rule_csv and Path(rule_csv).exists():
        _drop_ctx = {"absent", "comparison", "citation", "irrelevant"}
        with open(rule_csv, encoding="utf-8") as fh:
            for d in csv.DictReader(fh):
                if d.get("context_label", "") in _drop_ctx or not (d.get("pottery") or "").strip():
                    continue
                rg = _extract_regnum(d.get("original_text", ""))
                if rg and rg not in by_reg:
                    by_reg[rg] = _row_from_rule_find(d, lookup, report_id, backend)
                    recovered += 1
    return no_reg + list(by_reg.values()), deduped, recovered


def _tables_by_page(tables_md: str) -> Dict[int, List[str]]:
    """Group recovered table blocks by their page number, so each chunk can carry the tables for its
    own pages (instead of all tables being dumped once at the end, which chunking would split off)."""
    out: Dict[int, List[str]] = {}
    if not tables_md:
        return out
    parts = re.split(r"(\[\[p(\d+) table \d+\]\])", tables_md)
    i = 1
    while i + 1 < len(parts):
        page = int(parts[i + 1])
        body = parts[i + 2] if i + 2 < len(parts) else ""
        out.setdefault(page, []).append((parts[i] + body).strip())
        i += 3
    return out


def _chunk_budget(backend: str) -> int:
    """Max chars of report text to send per model call, sized to the backend's context window (with
    headroom for the prompt template and the ~16k-token output). Documents bigger than this are
    split to fit, so the whole report reaches the model instead of being truncated."""
    # Sized so a window's OUTPUT (the finds JSON) usually fits max_tokens; finds-dense windows are
    # further protected by the 32k output budget and the truncation-salvage parser. Smaller windows
    # = fewer finds per call = less truncation, at the cost of a few more calls on big reports.
    if backend == "claude":
        return 120_000                     # ~70 finds/window: output fits 16k tokens (no truncation)
    from config import LLM_PROVIDER, LLM_API_MODEL, LLM_MODEL
    model = ((LLM_MODEL if LLM_PROVIDER == "ollama" else LLM_API_MODEL) or "").lower()
    if any(t in model for t in ("1b", "3b", "8b")):
        return 60_000                      # small models: smaller chunks -> shorter, valid JSON
    return 100_000                         # 70B / default cloud


_TABLES_HEADER = ("\n\nSTRUCTURED TABLES (recovered grids; each DATA row is normally one find "
                  "across its ware/form/type columns — SKIP group-header / subtotal rows that "
                  "give no specific Form/Type):\n")


def _chunk_report(cleaned_pages, tbl_by_page, budget: int, overlap_pages: int = 2) -> List[str]:
    """Split the page-marked report into <=budget-char windows on PAGE boundaries, with `overlap_pages`
    pages shared between consecutive windows (so a find split at a page boundary stays whole in one
    window). Each window carries the recovered tables for its own pages. Returns a single window when
    the whole document fits (== the original single-call behaviour, no regression on normal reports)."""
    page_blocks = [(p["page_number"], f"[[p{p['page_number']}]]\n{p['text']}") for p in cleaned_pages]

    def _window(block_slice):
        text = "\n\n".join(b for _, b in block_slice)
        tbls = [t for n, _ in block_slice for t in tbl_by_page.get(n, [])]
        if tbls:
            text += _TABLES_HEADER + "\n\n".join(tbls)
        return text

    n = len(page_blocks)
    chunks, i = [], 0
    while i < n:
        j, size = i, 0
        while j < n and (j == i or size + len(page_blocks[j][1]) <= budget):
            size += len(page_blocks[j][1]); j += 1
        chunks.append(_window(page_blocks[i:j]))
        if j >= n:
            break
        i = max(j - overlap_pages, i + 1)   # 2-page overlap; always advance
    return chunks


def _dedupe_chunk_finds(finds: List[Dict]) -> List[Dict]:
    """Conservative CROSS-WINDOW dedup: drop a later find that repeats an earlier one's verbatim quote
    for the same ware (identical evidence -> the same physical find, e.g. an overlapped page seen in
    two windows). Finds with distinct quotes are ALL kept — this may slightly over-count a genuine
    cross-window duplicate, which is the recall-safe, conservative choice (matches the pipeline).

    Applied ONLY across chunk windows (multi-window reports). NOT within a single response: there,
    identical (ware, quote) rows are the model's deliberate count expansion ("twee bekers" -> 2 rows
    sharing one quote), which must be preserved (see prompt rule F)."""
    seen, out = set(), []
    for f in finds:
        pot = _norm(f.get("pottery") or "")
        q = _norm(f.get("original_text") or "")[:80]
        key = (pot, q)
        if q and key in seen:
            continue
        if q:
            seen.add(key)
        out.append(f)
    return out


def _merge_preview_group_rows(rows: List[Dict], report_text: str):
    """Deterministic backstop for the prompt's PREVIEW/LIST rule (c152): drop a generic group/preview
    row when the individual finds it previews are ALSO present, so the same vessels are not represented
    twice (e.g. a "drie potten" count row alongside its rechter/middelste/linker pot rows). KEEPS the
    itemized rows; removes only the redundant group row. Returns (kept_rows, dropped_rows) and never
    touches a find that isn't covered by others.

    A row is a GROUP candidate ONLY if the model flagged it non-specific (pot_name_certainty_level==0),
    i.e. it is already a low-value group/generic mention. It is dropped only on a concrete coreference
    signal — one of:
      A. COUNT-preview: it states a count q>=2 AND >=q specific itemized finds of the SAME site follow
         it in the source text within a short window.
      B. LIST-preview: >=2 specific finds of the same site whose term is contained in the group's term
         follow it in the source.
    A pure bulk count with no itemization (no members follow) is NOT dropped — it stays as the one
    quantity row, which is intended."""
    WINDOW = 1500   # a preview can sit a paragraph of discussion before its itemization (e.g. 12732)
    norm_report = re.sub(r"\s+", " ", report_text or "").lower()

    def _offset(r):
        q = re.sub(r"\s+", " ", (r.get("original_text") or "")).lower().strip()
        return norm_report.find(q[:50]) if q else -1

    offs = [_offset(r) for r in rows]

    def _specific(r):                       # an individually-identified find (not a group/generic row)
        nc = r.get("pot_name_certainty_level")
        return isinstance(nc, int) and nc > 0

    drop, log = set(), []
    for gi, g in enumerate(rows):
        if g.get("pot_name_certainty_level") != 0 or offs[gi] < 0:   # only model-flagged group rows
            continue
        site = (g.get("site_name") or "").strip()
        gterm = (g.get("term_found") or "").lower()
        members = [m for mi, m in enumerate(rows)
                   if mi != gi and mi not in drop and _specific(m)
                   and (m.get("site_name") or "").strip() == site
                   and 0 <= offs[gi] < offs[mi] <= offs[gi] + WINDOW]
        if not members:
            continue
        q = g.get("quantity")
        is_count = isinstance(q, int) and q >= 2 and len(members) >= q
        is_list = sum(1 for m in members if (m.get("term_found") or "").lower() in gterm) >= 2
        if is_count or is_list:
            drop.add(gi)
            log.append((g.get("term_found", ""), "count" if is_count else "list", len(members)))
    kept = [r for i, r in enumerate(rows) if i not in drop]
    return kept, log


def extract_pottery_hybrid(
    cleaned_pages: List[Dict],
    output_path: Path,
    report_id: str,
    csv_lookup: Optional[Dict] = None,
    code_dates: Optional[Dict] = None,
    pdf_path: Optional[Path] = None,
    rule_csv: Optional[Path] = None,
) -> None:
    """Run the full-report LLM extraction and write the pottery summary CSV."""
    backend = _hybrid_backend()
    tables_md = _extract_tables_md(pdf_path) if pdf_path else ""
    tbl_by_page = _tables_by_page(tables_md)
    # Full report text (pages + recovered table grids). Used whole-document for quote verification
    # and as context for the 5c confirm step. It is NOT sent to the model directly — the model gets
    # context-sized chunks (below), so long catalogues are never truncated.
    report_text = "\n\n".join(f"[[p{p['page_number']}]]\n{p['text']}" for p in cleaned_pages)
    if tables_md:
        report_text += _TABLES_HEADER + tables_md
    # Verbatim-quote validation corpus: the report content PLUS the original text layer retained
    # from any OCR-re-read (corrupt-font) page. The union lets a clean OCR quote validate even
    # though the layer it replaced lacked it, and vice versa — purely additive (never drops a find).
    # The model is still given only `report_text` as content, so no find is double-counted.
    _secondary = "\n\n".join(p["text_secondary"] for p in cleaned_pages if p.get("text_secondary"))
    norm_report = _norm(report_text + ("\n\n" + _secondary if _secondary else ""))
    # Typology grounding source: the master vocab table only (single source of truth for
    # dates/names). Values are (date_start, date_end, pot_name_en, full_typology_code).
    lookup = dict(code_dates or {})

    # Chunk the document into context-sized windows (2-page overlap) so the WHOLE report reaches the
    # model — finds in the back pages of long catalogues are no longer truncated away. Small reports
    # produce one window (== the whole document), preserving the original single-call behaviour.
    from src.periods import prompt_period_block
    pblock = prompt_period_block()
    budget = _chunk_budget(backend)
    chunks = _chunk_report(cleaned_pages, tbl_by_page, budget, overlap_pages=2)

    def _extract(window: str):
        return _parse_json_array(_hybrid_llm(_PROMPT.replace("__PERIODS__", pblock)
                                                    .replace("__REPORT__", window)))
    if len(chunks) == 1:
        finds = _extract(chunks[0])
    else:
        print(f"[Hybrid] {len(report_text)} chars > {budget} budget ('{backend}'); "
              f"chunking into {len(chunks)} windows (2-page overlap)")
        finds = []
        for ci, ch in enumerate(chunks, 1):
            cf = _extract(ch)
            print(f"[Hybrid]   window {ci}/{len(chunks)} ({len(ch)} chars): {len(cf)} finds")
            finds += cf
        # Dedup ONLY across windows: identical (ware, quote) here means the overlap re-saw the same
        # page. NOT applied to single-window output, where identical rows are intentional count
        # expansion ("twee bekers" -> 2 rows sharing one quote) that must be kept (prompt rule F).
        before = len(finds)
        finds = _dedupe_chunk_finds(finds)
        print(f"[Hybrid]   merged {before} -> {len(finds)} finds (conservative cross-window dedup)")

    rows, dropped = [], 0
    for f in finds:
        pot = (f.get("pottery") or "").strip()
        pot = _undiminish(pot, (f.get("term") or "").strip())   # "Small dish" (schaaltje) -> "Dish"
        quote = (f.get("original_text") or "").strip()
        if not pot:
            continue
        # Anti-hallucination: the quote must actually occur in the report (whitespace/case
        # and punctuation-insensitive; check a leading window so minor OCR diffs are ok).
        nq = _norm(quote)
        if not nq or (nq[:40] not in norm_report and nq not in norm_report):
            dropped += 1
            continue
        typ = (f.get("typology") or "").strip()
        term = (f.get("term") or "").strip()          # verbatim source-language term
        ds, de = _to_int(f.get("start_date")), _to_int(f.get("end_date"))
        method = backend
        grounded = _ground_typology(typ, lookup)
        if grounded:
            ds, de, gname, gcode = grounded
            method = f"{backend}+typology"
            if gname:                       # canonicalise the name to the controlled vocab
                pot = gname
            if gcode:                       # canonicalise the typology to the FULL code (Consp. 11
                typ = gcode + (" cf." if _is_tentative(typ) else "")   # -> Conspectus 11; keep cf.
        elif ds != "" or de != "":
            method = f"{backend}_text"
        if ds == "" and de == "":           # Q3: deterministic period backfill from the OWN quote
            pdate = _period_date_from_quote(quote)
            if pdate:
                ds, de = pdate
                method = "period_term"
        # Certainties: name & presence are LLM-rated (clamped); a tentative/"cf." type caps the
        # name low; date certainty is derived from how the date was obtained (typology-derived
        # inherits the name certainty); overall = mean of the three.
        name_cert = _clamp10(_to_int(f.get("pot_name_certainty_level")))
        if _is_tentative(typ) and name_cert != "":
            name_cert = min(name_cert, 4)
        # Generic-mention guard: the model sets specific_object=false when the text only states that
        # pottery occurs/keeps being found at the place rather than naming a discrete recovered
        # object. Such a row has no identifiable specific ware -> name certainty 0. It is KEPT (not
        # dropped), so it stays in the record for analysis; overall = mean then reads very low.
        name_reason = (f.get("pot_name_llm_reasoning") or "").strip()
        if f.get("specific_object") is False:
            name_cert = 0
            name_reason = "general mention that pottery occurs at the site, not a discrete object"
        pres_cert = _clamp10(_to_int(f.get("pot_presence_certainty_level")))
        date_cert, date_reason = _date_certainty(method, name_cert, ds != "" or de != "")
        qty = _to_int(f.get("quantity"))          # stated count for this find; "" when not numeric
        if qty != "" and qty <= 0:                # never store 0/negatives (model slip)
            qty = ""
        rows.append({
            "report_id": report_id,
            "site_name": (f.get("site") or "").strip(),   # the model's per-find site attribution
            "page": _to_int(f.get("page")),
            "pottery": pot,
            "typology": typ,
            "term_found": term or typ or pot,          # original source term (verbatim)
            "term_found_normalized_en": pot,           # English canonical ware/vessel name
            "quantity": qty,                           # stated count (int) or "" when not numeric
            "start_date": ds, "end_date": de,
            "date_method": method,
            "context_label": "present",
            "pot_name_certainty_level": name_cert,
            "pot_name_llm_reasoning": name_reason,
            "pot_presence_certainty_level": pres_cert,
            "pot_presence_llm_reasoning": (f.get("pot_presence_llm_reasoning") or "").strip(),
            "dates_certainty_level": date_cert,
            "date_llm_reasoning": date_reason,
            "overall_certainty_level": _overall(name_cert, pres_cert, date_cert),
            "original_text": quote,
        })

    # Option 5c: rule-proposes / model-confirms merge for the finds the model missed.
    confirmed_n = 0
    try:
        from config import POTTERY_HYBRID_RULE_CONFIRM
    except ImportError:
        POTTERY_HYBRID_RULE_CONFIRM = False
    if POTTERY_HYBRID_RULE_CONFIRM and rule_csv:
        # cache_path=None: the per-candidate confirm dump (_confirm.csv) was a write-only debug
        # artifact for offline threshold sweeps; it is no longer emitted.
        extra, confirmed_n, n_cand = _rule_confirm_merge(
            rows, rule_csv, report_text, lookup, report_id, cache_path=None)
        rows += extra

    # Deterministic reg#-keyed union: pin registration-numbered catalogues to their distinct reg#
    # set (collapse LLM duplicate emissions, recover catalogue entries the LLM dropped) so the count
    # is reproducible run-to-run. No-op for finds without a reg#. See config.POTTERY_REGNUM_UNION.
    n_regdup = n_regrec = 0
    try:
        from config import POTTERY_REGNUM_UNION
    except ImportError:
        POTTERY_REGNUM_UNION = False
    if POTTERY_REGNUM_UNION:
        rows, n_regdup, n_regrec = _regnum_union(rows, rule_csv, lookup, report_id, backend)

    # Deterministic backstop for the prompt's PREVIEW/LIST rule (c152): if the model emitted a group/
    # preview row ("drie potten") AND the individual finds it previews, drop the redundant group row.
    rows, _merged = _merge_preview_group_rows(rows, report_text)
    for _term, _kind, _n in _merged:
        print(f"[Hybrid]   merged-out {_kind}-preview row '{_term[:50]}' (covered by {_n} itemized find(s))")

    # Context date completion: one-sided Roman-period clamp (deterministic, low certainty) for any
    # find left with exactly one date endpoint after extraction/grounding/own-quote backfill.
    for r in rows:
        ns, ne, clamped = _roman_period_clamp(r["start_date"], r["end_date"])
        if clamped:
            r["start_date"], r["end_date"] = ns, ne
            r["date_method"] = "context_clamp"
            dc, dr = _date_certainty("context_clamp", r["pot_name_certainty_level"], True)
            r["dates_certainty_level"], r["date_llm_reasoning"] = dc, dr
            r["overall_certainty_level"] = _overall(
                r["pot_name_certainty_level"], r["pot_presence_certainty_level"], dc)

    # Roman-period scope filter: drop finds that are dated AND don't overlap the Roman window, plus
    # fully-undated finds whose label clearly names a sole non-Roman period (undated Roman/ambiguous
    # finds are kept). See src/periods.roman_in_scope.
    n_offscope = 0
    try:
        from config import POTTERY_ROMAN_ONLY
        from src.periods import roman_in_scope
    except ImportError:
        POTTERY_ROMAN_ONLY = False
    if POTTERY_ROMAN_ONLY:
        def _scope_text(r):
            return " ".join(str(r.get(k, "")) for k in
                            ("pottery", "term_found_normalized_en", "term_found", "original_text"))
        kept = [r for r in rows if roman_in_scope(r["start_date"], r["end_date"], _scope_text(r))]
        n_offscope = len(rows) - len(kept)
        rows = kept

    # Canonicalize site names: chunked windows can spell the same place several ways; collapse them
    # so finds group by site correctly.
    from src.site_norm import apply_site_canonicalization, collapse_compound_sites, fill_singleton_site
    n_site = apply_site_canonicalization(rows, "site_name", use_llm=True)   # hybrid => LLM available
    # Deterministic backstop for the settlement-only prompt rule: if a compound site slipped through,
    # collapse it to a bare settlement that co-occurs in the report (list-free, reproducible).
    n_site += collapse_compound_sites(rows, "site_name")
    # Single-site report: blank-site rows inherit the report's only site (deterministic, no-op if >1).
    n_site += fill_singleton_site(rows, "site_name")
    # Caption backstop: if the report still has NO site anywhere (e.g. it is named only in a figure
    # caption the per-find extraction skipped), infer the single excavation site from the title +
    # captions via one focused LLM call. Strictly additive — only fills an all-blank report.
    try:
        from config import POTTERY_SITE_CAPTION_BACKSTOP
    except ImportError:
        POTTERY_SITE_CAPTION_BACKSTOP = False
    if POTTERY_SITE_CAPTION_BACKSTOP and rows and not any((r.get("site_name") or "").strip() for r in rows):
        from src.site_norm import infer_site_from_captions
        cap_site = infer_site_from_captions(report_text)
        if cap_site:
            for r in rows:
                r["site_name"] = cap_site
            n_site += len(rows)
            print(f"[Hybrid] site backstop: report had no site; inferred '{cap_site}' from title/captions")

    # CAI inventory override: in Flemish CAI extracts the authoritative site key is the standalone
    # 6-digit inventory code, not the toponym the model tends to grab from a "Bron:" citation. Runs
    # AFTER canonicalization so the numeric code is the final, un-"humanized" value. No-op elsewhere.
    try:
        from config import POTTERY_CAI_SITE_CODES
    except ImportError:
        POTTERY_CAI_SITE_CODES = True
    if POTTERY_CAI_SITE_CODES:
        n_cai = _apply_cai_site_codes(rows, report_text)
        if n_cai:
            n_site += n_cai
            print(f"[Hybrid] CAI inventory: {n_cai} site(s) set from inventory code")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_OUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tail = f"; +{confirmed_n} rule-confirmed (5c)" if confirmed_n else ""
    tail += f"; reg# union -{n_regdup} dup/+{n_regrec} recovered" if (n_regdup or n_regrec) else ""
    tail += f"; -{n_offscope} off-scope (non-Roman)" if n_offscope else ""
    tail += f"; {n_site} site variant(s) merged" if n_site else ""
    print(f"[Hybrid] {len(rows)} finds (dropped {dropped} unquoted{tail}) → {output_path}")

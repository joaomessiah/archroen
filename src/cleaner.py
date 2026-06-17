"""Layer 2 — text cleaning.

Normalises raw page text: de-hyphenates line-wrapped words, strips repeated
headers/footers and page furniture, and fixes whitespace so downstream regex
detection sees clean, continuous prose.
"""
import re
from collections import Counter
from typing import List, Dict


HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*page\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*archaeological report\s*$", re.IGNORECASE),
]

# Minimum character length for a line to be considered a repeating header/footer.
_MIN_FOOTER_LEN = 15


def _normalise_footer_line(line: str) -> str:
    """Strip a leading page number + separator so '42 / Foo' and '33 / Foo' normalise identically."""
    return re.sub(r'^\d+\s*[/\-\.]\s*', '', line.strip())


def strip_repeating_lines(pages: List[Dict]) -> List[Dict]:
    """
    Detect running headers/footers by finding lines (possibly with a leading
    page number) that appear on the majority of pages, then remove them.
    Works for any PDF without knowing the specific footer content.
    """
    if len(pages) < 2:
        return pages

    # Count how many pages each normalised line appears on.
    line_page_count: Counter = Counter()
    for page in pages:
        seen_this_page: set = set()
        for raw in page["text"].split("\n"):
            norm = _normalise_footer_line(raw)
            if len(norm) >= _MIN_FOOTER_LEN and norm not in seen_this_page:
                line_page_count[norm] += 1
                seen_this_page.add(norm)

    # A line is a header/footer if it appears on at least half the pages.
    threshold = max(2, len(pages) // 2)
    repeating = {norm for norm, count in line_page_count.items() if count >= threshold}

    if not repeating:
        return pages

    stripped_count = sum(1 for norm in repeating for _ in [None])
    print(f"[Cleaner] stripping {stripped_count} repeating header/footer line(s) found on >={threshold} pages")

    result = []
    for page in pages:
        kept = [
            line for line in page["text"].split("\n")
            if _normalise_footer_line(line) not in repeating
        ]
        rec = {"page_number": page["page_number"], "text": "\n".join(kept)}
        if page.get("text_secondary"):          # carry the retained original layer (OCR re-read pages)
            rec["text_secondary"] = page["text_secondary"]
        result.append(rec)
    return result


# --- OCR letter-fragmentation repair (old scanned bulletins) -----------------
# Some old scans extract with words shattered into one-character-per-line runs
# ("d\ni\ne" = "die", "2\n0" = "20"), space-only lines acting as word breaks. This
# is gated on a high ratio of single-LETTER lines so it fires only on genuinely
# fragmented prose pages — never on numeric tables, whose single-char lines are
# DIGITS (e.g. MNI columns), not letters.
def _looks_fragmented(text: str) -> bool:
    nonempty = [l.strip() for l in text.split("\n") if l.strip()]
    if len(nonempty) < 20:
        return False
    single_alpha = sum(1 for l in nonempty if len(l) == 1 and l.isalpha())
    return single_alpha / len(nonempty) > 0.2


def _defragment(text: str) -> str:
    """Merge runs of single-character lines back into whole words/numbers, one per
    output line. Multi-char and blank lines (word/line breaks) are preserved, so
    headings and overall line structure survive."""
    out: List[str] = []
    frag: List[str] = []
    for raw in text.split("\n"):
        s = raw.strip()
        if len(s) == 1 and s.isalnum():
            frag.append(s)
        else:
            if frag:
                out.append("".join(frag))
                frag = []
            out.append(raw)
    if frag:
        out.append("".join(frag))
    return "\n".join(out)


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r", "\n")
    # Unfold Latin typographic ligatures that PDF fonts emit as single code points
    # (ﬁnd→find, Dragendorﬀ→Dragendorff). Left as-is they break word/typology regexes and
    # the hybrid's verbatim-quote check (the ligature char is not [a-z], so it is silently
    # dropped during normalisation and the quote no longer matches the source).
    for _lig, _rep in (("ﬀ", "ff"), ("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬃ", "ffi"),
                       ("ﬄ", "ffl"), ("ﬅ", "st"), ("ﬆ", "st")):
        if _lig in text:
            text = text.replace(_lig, _rep)
    # Repair OCR letter-fragmentation before anything else (gated to fragmented pages).
    if _looks_fragmented(text):
        text = _defragment(text)
    # Replace control characters and non-Latin script characters used as space substitutes in PDFs
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"[܀-ݏݐ-ݿ]", " ", text)  # Syriac block artifacts
    # Remove spurious 'b' separators from PDF font encoding artifacts.
    # Pass 1: letter + b + uppercase/digit  ("fromb70" → "from 70", "16bBC" base covered below)
    text = re.sub(r"(?<=[a-zA-Z])b(?=[A-Z0-9])", " ", text)
    # Pass 2: digit + b + uppercase  ("16bBC" → "16 BC") — not caught above because "6" is a digit
    text = re.sub(r"(?<=\d)b(?=[A-Z])", " ", text)
    # Pass 3: digit + b + lowercase WORD (>=2 letters): a typology code glued to the next
    # word by the artifact ("Chenet 320bdate" → "Chenet 320 date", "Drag.18/31band" →
    # "…31 and"). >=2 letters avoids touching single-letter type variants ("Drag. 18b").
    text = re.sub(r"(?<=\d)b(?=[a-z]{2,})", " ", text)
    text = re.sub(r"[\t\f\v]+", " ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    # Rejoin words hyphenated across line breaks by removing the newline but KEEPING the
    # hyphen. This handles both pure line-break hyphens ("handge-\nvormd" → "handge-vormd")
    # and compound-word hyphens broken at line end ("vroeg-4e-\neeuws" → "vroeg-4e-eeuws").
    # Keeping the hyphen is safer: dropping it would destroy compound forms like "4e-eeuws"
    # that downstream regex patterns require. Only applies when the second fragment starts
    # with a lowercase letter; uppercase starters (e.g. "Laat-\nRomeins") are left intact.
    text = re.sub(r"(\w)-\n([a-z])", r"\1-\2", text)
    # ...but a hyphen that split a Dutch diminutive/plural suffix ("schaalt-jes" →
    # "schaaltjes") is a syllable break, never a compound join, so drop it — otherwise
    # the diminutive vessel-form triggers (schaaltjes, kommetjes, …) cannot match.
    text = re.sub(r"(\w)-((?:tje|je|pje|kje|etje)s?)\b", r"\1\2", text)
    # Old / OCR'd reports often hyphenate the standard ware name ("terra-sigillata");
    # normalise to the spaced form so the multi-word trigger and naming patterns match.
    text = re.sub(r"\bterra-(sigillata|nigra|rubra)\b", r"terra \1", text, flags=re.IGNORECASE)
    # "Drag 18" (OCR / informal reports drop the period) → "Drag. 18", so the CSV
    # typology patterns (which list "Drag.") match.
    text = re.sub(r"\bDrag\s+(\d)", r"Drag. \1", text)

    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if any(p.match(line) for p in HEADER_FOOTER_PATTERNS):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize some common punctuation/spacing issues
    text = text.replace("–", "-").replace("—", "-")
    # Remove spurious space before periods ("word ." → "word.")
    text = re.sub(r"\s+\.", ".", text)
    # Insert exactly one space after a sentence-ending period. Only triggers when at least
    # 2 lowercase letters precede the period — this avoids disrupting abbreviations that
    # have a single-letter prefix such as "n.Chr." (n=1 char) and "v.Chr." (v=1 char).
    text = re.sub(r"([a-z]{2,})\. ?([A-Z])", r"\1. \2", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Archaic (pre-1947) Dutch normalization for old reports
# ---------------------------------------------------------------------------
# Old excavation reports use pre-spelling-reform orthography (silent "ch" in the
# -sch suffix: "Romeinsch", "mensch") and archaic date idioms ("onzer jaartelling"
# = "of our era" = AD). These defeat the date parser and chron_vocab, which only
# know modern spelling. normalize_archaic() maps the old forms to modern ones so
# downstream matching works. It is deliberately NOT called inside clean_text():
# the canonical cleaned text stays PDF-verbatim (for manual checking and span
# fidelity); normalization is applied locally where matching happens and exposed
# as a separate, modernized output column.

# Irregular inflected -schen adjectives (genitive/dative) → modern -se. Handled
# explicitly because a blanket "schen"→"se" rule would also corrupt archaic noun
# plurals like "menschen" (modern "mensen", not "mense").
_ARCHAIC_PHRASES = [
    # Archaic era idioms → standard era markers the date parser understands.
    (re.compile(r"\bonze[r]?\s+jaartelling\b", re.IGNORECASE), "n.Chr."),
    (re.compile(r"\bonze[r]?\s+tijdrekening\b", re.IGNORECASE), "n.Chr."),
    (re.compile(r"\bna\s+Christus\b", re.IGNORECASE), "n.Chr."),
    (re.compile(r"\bna\s+Chr\.", re.IGNORECASE), "n.Chr."),
    (re.compile(r"\bv[oó]{1,2}r\s+Christus\b", re.IGNORECASE), "v.Chr."),
    (re.compile(r"\bv[oó]{1,2}r\s+Chr\.", re.IGNORECASE), "v.Chr."),
    # Inflected -schen period adjectives → modern -se. Handled explicitly because
    # word-final "schen" has no \b after "sch", and a blanket rule would also
    # corrupt archaic noun plurals like "menschen" (modern "mensen", not "mense").
    (re.compile(r"\bRomeinschen\b", re.IGNORECASE), "Romeinse"),
    (re.compile(r"\bRomaanschen\b", re.IGNORECASE), "Romaanse"),
    (re.compile(r"\bGermaanschen\b", re.IGNORECASE), "Germaanse"),
]

# Regular word-final -sch / -sche suffix (the 1947 reform dropped the silent 'ch':
# Romeinsch→Romeins, Romaansch→Romaans, Germaansche→Germaanse, mensch→mens).
# The (?<!i) guard preserves the modern "-isch" suffix, which the reform KEPT and
# which is common in normal reports (prehistorisch, Belgisch, logisch, technisch).
# \b anchors it to the suffix, never stem-internal "sch" (school, geschiedenis).
_SCH_E_RE = re.compile(r"(?<!i)sche\b", re.IGNORECASE)
_SCH_RE = re.compile(r"(?<!i)sch\b", re.IGNORECASE)


def normalize_archaic(text: str) -> str:
    """Map pre-1947 Dutch spelling and archaic date idioms to modern forms.

    Used for date matching and for the modernized output column; does not mutate
    the verbatim cleaned text.
    """
    if not text:
        return text
    for pattern, repl in _ARCHAIC_PHRASES:
        text = pattern.sub(repl, text)
    text = _SCH_E_RE.sub("se", text)
    text = _SCH_RE.sub("s", text)
    return text


def clean_pages(pages: List[Dict]) -> List[Dict]:
    pages = strip_repeating_lines(pages)
    out = []
    for page in pages:
        rec = {"page_number": page["page_number"], "text": clean_text(page["text"])}
        if page.get("text_secondary"):          # clean the retained original layer the same way
            rec["text_secondary"] = clean_text(page["text_secondary"])
        out.append(rec)
    return out
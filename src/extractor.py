"""Layer 1 — PDF extraction.

Reads a PDF and returns one text block per page (via PyMuPDF), the raw input that
every later layer consumes. Image-only / scanned pages are routed to OCR.
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict


def _render_page_image(page) -> bytes:
    """Render a page to image bytes for OCR, capping the longest side to
    OCR_MAX_IMAGE_DIM so a large scan doesn't exceed Google Vision's ~40 MB request
    limit (base64 inflates raw bytes ~33%). Falls back to JPEG if the PNG is still big."""
    from config import OCR_DPI, OCR_MAX_IMAGE_DIM
    longest_pt = max(page.rect.width, page.rect.height) or 1
    zoom = OCR_DPI / 72.0
    if longest_pt * zoom > OCR_MAX_IMAGE_DIM:
        zoom = OCR_MAX_IMAGE_DIM / longest_pt
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = pix.tobytes("png")
    if len(img) > 28 * 1024 * 1024:  # keep base64 payload comfortably under 40 MB
        img = pix.tobytes("jpeg")
    return img


def _strip_marginalia(text: str, blocks, page_height: float) -> str:
    """Remove isolated margin headers/footers (page/folio numbers, running heads) from an OCR'd page.

    A page number printed in the top/bottom margin OCRs into a bare line (e.g. "1310") that the
    extractor mistakes for a find/registration number — OCR flattens away the position that reveals it
    as a header. Using Google Vision's per-block boxes, a block is marginalia when ALL hold: it sits in
    the margin band, is separated from the body by a large vertical gap, and is a short line (long
    captions, which carry real context, fail the length test and are kept). The matching line is then
    deleted from Vision's own text — only at the very top/bottom of reading order — so the body text is
    byte-identical otherwise. Conservative: when nothing qualifies, returns the text unchanged."""
    from config import (OCR_STRIP_MARGINALIA, OCR_MARGIN_BAND_FRAC, OCR_MARGIN_GAP_FRAC,
                        OCR_MARGIN_MAX_CHARS, OCR_MARGIN_MAX_WORDS)
    if not (OCR_STRIP_MARGINALIA and text and blocks and page_height > 0):
        return text
    norm = lambda s: " ".join((s or "").split()).lower()
    band = OCR_MARGIN_BAND_FRAC * page_height
    gap_min = OCR_MARGIN_GAP_FRAC * page_height
    ordered = sorted(blocks, key=lambda b: (b["y0"], b["x0"]))
    n = len(ordered)
    top_needles, bot_needles = set(), set()
    for i, b in enumerate(ordered):
        bt = " ".join((b["text"] or "").split())
        if not (0 < len(bt) <= OCR_MARGIN_MAX_CHARS and len(bt.split()) <= OCR_MARGIN_MAX_WORDS):
            continue
        if b["y1"] <= band:                                   # top margin band
            gap = (ordered[i + 1]["y0"] - b["y1"]) if i + 1 < n else page_height
            if gap >= gap_min:
                top_needles.add(norm(bt))
        if b["y0"] >= page_height - band:                     # bottom margin band
            gap = (b["y0"] - ordered[i - 1]["y1"]) if i - 1 >= 0 else page_height
            if gap >= gap_min:
                bot_needles.add(norm(bt))
    if not top_needles and not bot_needles:
        return text
    lines = text.split("\n")
    m = len(lines)
    kept, removed = [], []
    for idx, ln in enumerate(lines):
        nl = norm(ln)
        near_top, near_bot = idx <= 2, idx >= m - 3          # only strip at the reading-order edges
        if nl and ((near_top and nl in top_needles) or (near_bot and nl in bot_needles)):
            removed.append(ln.strip())
            continue
        kept.append(ln)
    if removed:
        print(f"[extractor] stripped marginalia: {removed}")
    return "\n".join(kept).strip("\n")


def _ocr_page(page, page_index: int) -> str:
    """Render a page to an image and OCR it. Returns "" on any failure so a single
    bad page never aborts the run."""
    from config import OCR_STRIP_MARGINALIA
    from src.ocr_client import ocr_page_image
    try:
        img = _render_page_image(page)
        if OCR_STRIP_MARGINALIA:
            text, blocks, _w, height = ocr_page_image(img, with_layout=True)
            text = _strip_marginalia(text or "", blocks, height)
        else:
            text = ocr_page_image(img) or ""
        if text:
            print(f"[extractor] OCR recovered {len(text)} chars on page {page_index + 1}")
        return text
    except Exception as e:
        print(f"[extractor] WARNING: OCR failed on page {page_index + 1}: {e}")
        return ""


def _corruption_glyph_density(text: str):
    """Glyphs per 1000 chars that signal a broken PDF font / ToUnicode map: code points outside
    Latin + common punctuation, EXCLUDING benign typographic ligatures (the cleaner unfolds those)
    and control chars (used as space substitutes). A high density means the text layer is a
    glyph-substitution cipher that OCR should re-read. Returns (per_1000, absolute_count)."""
    if not text:
        return 0.0, 0
    n = 0
    for ch in text:
        o = ord(ch)
        if o < 0x80:                continue   # ASCII
        if 0x00A0 <= o <= 0x024F:   continue   # Latin-1 + Latin Extended-A/B (Dutch accents)
        if 0x2000 <= o <= 0x206F:   continue   # general punctuation (curly quotes, dashes)
        if 0xFB00 <= o <= 0xFB4F:   continue   # ligatures — cleaner unfolds these
        if o < 0x20 or 0x80 <= o <= 0x9F:  continue   # control chars — cleaner maps to space
        n += 1
    return 1000.0 * n / len(text), n


def extract_pdf_pages(pdf_path: Path) -> List[Dict]:
    """Read a PDF into one ``{"page_number", "text"}`` dict per page. A page with too little text
    (image-only) — or one whose text layer looks font-corrupted — is rendered to an image and sent
    to OCR instead. Per-page errors are swallowed (empty page) so one bad page never aborts the run."""
    from config import (OCR_ENABLED, OCR_MIN_TEXT_LAYER_CHARS, OCR_RECHECK_CORRUPT_TEXT,
                        OCR_CORRUPTION_GLYPH_PER_1K, OCR_CORRUPTION_MIN_GLYPHS)

    pages = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"[extractor] ERROR: could not open PDF '{pdf_path}': {e}")
        return []
    try:
        for i, page in enumerate(doc):
            try:
                text = page.get_text("text") or ""
            except Exception as e:
                print(f"[extractor] WARNING: could not extract page {i + 1}: {e}")
                text = ""
            page_rec = {"page_number": i + 1, "text": text}
            # Image-only / scanned page (no usable text layer) → OCR fallback.
            if OCR_ENABLED and len(text.strip()) < OCR_MIN_TEXT_LAYER_CHARS:
                ocr_text = _ocr_page(page, i)
                if ocr_text:
                    page_rec["text"] = ocr_text
            # Long-but-corrupt text layer (broken font map) → OCR re-read, but KEEP the original
            # text layer as a secondary corpus so a clean OCR quote still validates and the rule
            # layer can cross-check it. OCR becomes the content (single source → no double-counting).
            elif OCR_ENABLED and OCR_RECHECK_CORRUPT_TEXT:
                per_1k, n_glyph = _corruption_glyph_density(text)
                if per_1k >= OCR_CORRUPTION_GLYPH_PER_1K and n_glyph >= OCR_CORRUPTION_MIN_GLYPHS:
                    print(f"[extractor] page {i + 1}: corrupt text layer "
                          f"({per_1k:.1f} glyphs/1k, {n_glyph} glyphs) → re-reading via OCR")
                    ocr_text = _ocr_page(page, i)
                    if ocr_text:
                        page_rec["text_secondary"] = text   # retain the original layer for validation
                        page_rec["text"] = ocr_text
            pages.append(page_rec)
    finally:
        doc.close()
    return pages

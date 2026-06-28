# Layer 1: Extraction

**Module:** `src/extractor.py`

## Purpose

Read the report PDF and turn it into plain text, page by page. This text is the raw input that every
later layer consumes.

## What it does

- Reads the PDF with **PyMuPDF** and returns **one text block per page**.
- **Routes scanned / image-only pages through OCR.** Such a page is rendered to an image and sent to
  the OCR service. The image's longest side is capped at `OCR_MAX_IMAGE_DIM` so a large scan stays under
  Google Vision's ~40 MB request limit, and the renderer falls back from PNG to JPEG if needed.
- OCR'd pages also get light **marginalia stripping** (isolated page/folio numbers and running heads).

## Input and output

- **In:** a PDF file path.
- **Out:** a list of per-page text blocks (page number + raw text).

## Configuration (`config.py`)

| Setting | Role |
|---|---|
| `OCR_ENABLED` | Turn OCR of scanned pages on/off |
| `OCR_DPI` | Render resolution for OCR |
| `OCR_MAX_IMAGE_DIM` | Cap on the longest image side (request-size safety) |
| `OCR_STRIP_MARGINALIA` | Drop running-header/footer marginalia from OCR text (default `True`) |
| `OCR_MARGIN_BAND_FRAC` | Block must lie within this fraction of page height from the top/bottom edge |
| `OCR_MARGIN_GAP_FRAC` | ...and be separated from the nearest body block by at least this fraction |
| `OCR_MARGIN_MAX_CHARS` | ...and be a short line (protects real captions, which are long) |
| `OCR_MARGIN_MAX_WORDS` | ...and have at most this many words |
| `GOOGLE_VISION_API_KEY` | Key for the OCR service (see [../../getting_started/api_keys.md](../../getting_started/api_keys.md)) |

## Notes

Born-digital PDFs with a real text layer are read directly and need no key. OCR is only used for
scanned/image pages and requires a Google Vision key.

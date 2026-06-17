"""
OCR abstraction for scanned / image-only PDF pages.

Call ``ocr_page_image(png_bytes)`` to turn a rendered page image into text.
The backend is selected by ``config.OCR_PROVIDER``:
  - "google": Google Cloud Vision (DOCUMENT_TEXT_DETECTION) via REST + API key.
  - "tesseract" / "auto": reserved for later (raise NotImplementedError for now).

To add another provider later, implement a ``_call_<provider>`` and dispatch below —
the same pattern as src/llm_client.py.
"""

import base64


def ocr_page_image(image_bytes: bytes, with_layout: bool = False):
    """Turn a rendered page image into text. By default returns the plain transcribed text (str).

    When ``with_layout=True`` returns ``(text, blocks, width, height)`` where ``blocks`` is a list of
    ``{"text", "x0", "y0", "x1", "y1"}`` (pixel bounding boxes) — used to drop margin headers/footers
    before the text reaches the extractor. ``width``/``height`` are the OCR'd image's pixel size."""
    from config import OCR_PROVIDER

    if OCR_PROVIDER == "google":
        return _call_google_vision(image_bytes, with_layout=with_layout)
    if OCR_PROVIDER in ("tesseract", "auto"):
        raise NotImplementedError(
            f"OCR_PROVIDER={OCR_PROVIDER!r} not implemented yet (only 'google' is available)."
        )
    raise ValueError(f"Unknown OCR_PROVIDER: {OCR_PROVIDER!r}. Supported: 'google'.")


def _vision_blocks(full_text_annotation: dict):
    """Flatten Google Vision's fullTextAnnotation into per-block text + pixel bounding boxes.
    Returns ``(blocks, width, height)``; width/height fall back to the max vertex when absent."""
    pages = full_text_annotation.get("pages") or []
    if not pages:
        return [], 0, 0
    pg = pages[0]
    width = pg.get("width") or 0
    height = pg.get("height") or 0
    blocks = []
    for blk in pg.get("blocks") or []:
        verts = (blk.get("boundingBox") or {}).get("vertices") or []
        xs = [v.get("x", 0) for v in verts]
        ys = [v.get("y", 0) for v in verts]
        if not xs or not ys:
            continue
        parts = []
        for para in blk.get("paragraphs") or []:
            for word in para.get("words") or []:
                for sym in word.get("symbols") or []:
                    parts.append(sym.get("text", ""))
                    brk = ((sym.get("property") or {}).get("detectedBreak") or {}).get("type")
                    if brk and brk != "HYPHEN":          # SPACE/SURE_SPACE/EOL_SURE_SPACE/LINE_BREAK -> space
                        parts.append(" ")
        blocks.append({"text": "".join(parts).strip(),
                       "x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys)})
    if not height:
        height = max((b["y1"] for b in blocks), default=0)
    if not width:
        width = max((b["x1"] for b in blocks), default=0)
    return blocks, width, height


def _call_google_vision(image_bytes: bytes, with_layout: bool = False):
    """Google Cloud Vision document text detection via the REST endpoint.

    Uses an API key (config.GOOGLE_VISION_API_KEY or the GOOGLE_VISION_API_KEY env var).
    Returns the full transcribed text ("" when the image has none), or — when
    ``with_layout=True`` — ``(text, blocks, width, height)`` (see ``_vision_blocks``)."""
    import os
    import requests
    from config import (
        GOOGLE_VISION_API_KEY, GOOGLE_VISION_ENDPOINT, OCR_LANG_HINTS,
    )

    api_key = GOOGLE_VISION_API_KEY or os.environ.get("GOOGLE_VISION_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No Google Vision API key. Set the GOOGLE_VISION_API_KEY environment "
            "variable (config.py is git-tracked, so do not paste the key there)."
        )

    payload = {
        "requests": [{
            "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": list(OCR_LANG_HINTS)},
        }]
    }
    # Pass the key as a header (not ?key=...) so it never appears in URLs, error
    # messages or logs.
    resp = requests.post(
        GOOGLE_VISION_ENDPOINT, json=payload, timeout=90,
        headers={"X-goog-api-key": api_key},
    )
    if resp.status_code != 200:
        # Surface Google's reason without leaking the key.
        try:
            msg = resp.json().get("error", {}).get("message", resp.text[:200])
        except Exception:
            msg = resp.text[:200]
        raise RuntimeError(f"Google Vision HTTP {resp.status_code}: {msg}")
    response0 = (resp.json().get("responses") or [{}])[0]
    if "error" in response0:
        raise RuntimeError(f"Google Vision error: {response0['error'].get('message')}")
    full = response0.get("fullTextAnnotation") or {}
    text = full.get("text", "").strip()
    if with_layout:
        blocks, width, height = _vision_blocks(full)
        return text, blocks, width, height
    return text

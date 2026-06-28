# Layer 3: Detection

**Modules:** `src/detection.py` (regex detection), `src/pottery_extractor.py` (trigger-based extraction)

## Purpose

Find candidate mentions of **pottery, periods, and centuries** in the chunked text. Detection uses
vocabulary-derived regular expressions, plus trigger words that catch pottery types not in the pattern
list.

## Regex detection (`detection.py`)

- Scans each chunk against the **generated pattern files** in `data/patterns/`
  (`pottery_patterns.json`, `chronology_patterns.json`, `century_patterns.json`) and emits one
  **candidate** per match. Each candidate carries its `CONTEXT_WINDOW_CHARS`-wide surrounding context.
  That context is snapped to sentence boundaries, with care not to break on initials like `J. Smith`,
  numbered list items, or `n.Chr.`/`v.Chr.`.
- **Merges dual typologies** such as `Lamboglia 2/Dressel 6A` into a single candidate.
- Builds the **typology-code → date lookup** (from `pottery_vocab_master.csv`) used downstream for
  dating.

The pattern files are **generated** from the vocabularies by the scripts in `tools/`, not edited by
hand. To change what gets detected, edit the vocabulary and regenerate (see
[../../reference/data_files.md](../../reference/data_files.md)).

## Trigger-based extraction (`pottery_extractor.py`)

Catches pottery mentions the pattern list misses:

1. **Trigger words.** A list in English, Dutch, and Latin (`data/patterns/pottery_triggers.json`) flags
   candidate sentences. Each trigger has a *strength*: `strong` triggers fire on their own, while `weak`
   ones need supporting cues nearby.
2. **Naming-convention patterns.** Common structured names are recognised directly: typology codes
   (`Drag. 37`, `Stuart 201`, `Dressel 20`, …) and `"… ware"` forms (`Samian ware`,
   `Gallo-Belgic ware`, …).
3. **Optional AI fallback.** For flagged sentences the deterministic cues can't confirm, an AI step can
   decide whether a real pottery name is present (gated by `POTTERY_EXTRACT_LLM_USE`).
4. **Figure catalogues.** Extracts figure plates of vessel drawings labelled only by find/catalogue
   numbers, gated on a figure marker plus a vessel/pottery word in the caption.

## Input and output

- **In:** the sections/chunks from [Layer 2](layer_2.md).
- **Out:** a list of term candidates, each with matched text, a canonical hint, and its context window.

## Configuration (`config.py`)

| Setting | Default | Role |
|---|---|---|
| `CONTEXT_WINDOW_CHARS` | `300` | Width of the context window stored per candidate |
| `POTTERY_EXTRACT_LLM_USE` | `False` | Enable the AI fallback for ambiguous trigger sentences |
| `*_PATTERNS_PATH` | (none) | The generated pattern files (see [../../reference/data_files.md](../../reference/data_files.md)) |

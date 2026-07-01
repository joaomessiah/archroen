# config.py option reference

The full per-flag rationale for `config.py`. `config.py` itself keeps short one-line
comments and points here for the detail. For the everyday settings (`WORKFLOW_MODE`,
`DEFAULT_REPORTS_DIR`, `BATCH_WORKERS`), see [../getting_started/configuration.md](../getting_started/configuration.md).
`DEFAULT_REPORTS_DIR` currently points to `workflow_evaluation_sample`.
For keys, see [../getting_started/api_keys.md](../getting_started/api_keys.md).

Sections below mirror the section banners in `config.py`.

## Secrets / credentials

API keys are read from environment variables (and from a gitignored `.env`, auto-loaded by
`config.py`; see `.env.example`). `config.py` defaults each key to an empty string, so it holds no
literal secrets. **Never commit real keys.** Keys: `LLM_API_KEY` (cloud OpenAI-compatible backend),
`ANTHROPIC_API_KEY` (Claude REST API), `GOOGLE_VISION_API_KEY` (OCR).

## Text extraction & OCR (Layers 1-2)

OCR is for scanned / image-only PDFs that have no extractable text layer.

- `OCR_ENABLED`: master on/off for OCR of scanned / image-only pages.
- `OCR_PROVIDER`: `"google"` (Cloud Vision REST). `"tesseract"`/`"auto"` are reserved for later.
- `OCR_LANG_HINTS`: Google Vision language hints (English + Dutch by default).
- `GOOGLE_VISION_ENDPOINT`: the Cloud Vision REST endpoint (rarely changed).
- `OCR_DPI`: resolution to render a page into an image before OCR.
- `OCR_MAX_IMAGE_DIM`: cap the longest rendered side (px). Large scans otherwise exceed Google
  Vision's ~40 MB request limit.
- `OCR_MIN_TEXT_LAYER_CHARS`: a page with fewer real chars is treated as image-only and sent to OCR.
- `OCR_RECHECK_CORRUPT_TEXT`: a page can have a LONG text layer that is nonetheless garbage. A
  broken PDF font / ToUnicode map renders correctly on screen but extracts as a glyph-substitution
  cipher (e.g. fi→U+087C, fl→U+087D, Syriac/Arabic space-substitutes), so such pages slip past the
  length gate above. When a page's density of corruption glyphs (non-Latin, non-punctuation,
  non-ligature, non-control code points) exceeds the threshold, re-read the page via OCR, which is
  pixel-based and so escapes the broken font map, and KEEP the original text layer as a secondary
  corpus for verbatim-quote validation.
  - `OCR_CORRUPTION_GLYPH_PER_1K`: corruption glyphs per 1000 chars to flag a page (corrupt
    reports ~3-9, clean = 0).
  - `OCR_CORRUPTION_MIN_GLYPHS`: also require this many in absolute terms (guards tiny pages).
- `OCR_STRIP_MARGINALIA`: a page/folio number or running header printed in the top/bottom margin
  gets OCR'd as an isolated bare token (e.g. "1310" top-left), which the extractor then mistakes for
  a find/registration number, because OCR flattens away the position that would reveal it as a header.
  Google Vision (DOCUMENT_TEXT_DETECTION) already returns per-block bounding boxes for free, so we
  drop a block when ALL of the following hold: it sits in the margin band, it is isolated from the
  body by a large vertical gap, and it is a short line. Long captions, which carry real context, fail
  the length test and are kept. This only affects OCR'd pages; text-layer PDFs keep their native
  reading structure.
  - `OCR_MARGIN_BAND_FRAC`: block must lie within this fraction of page height from the top/bottom edge.
  - `OCR_MARGIN_GAP_FRAC`: ...and be separated from the nearest body block by at least this fraction of page height.
  - `OCR_MARGIN_MAX_CHARS`: ...and be a short line (protects real captions, which are long).
  - `OCR_MARGIN_MAX_WORDS`: ...and have at most this many words.

## Chunking

Cleaned text is split into overlapping character chunks that bound the context window used by
detection and the LLM layers (see [layer_2](../workflow/specs/layer_2.md)).

- `CHUNK_SIZE`: chunk length in characters.
- `CHUNK_OVERLAP`: overlap between consecutive chunks, so a term near a chunk edge keeps context on
  both sides.
- `CONTEXT_WINDOW_CHARS`: width of the context window stored with each detected candidate.

## LLM backend & master switch

`WORKFLOW_MODE` is the MASTER switch for which model the ENTIRE workflow talks to: both the hybrid
extractor AND the rule-layer helpers (context classification, dedup, consolidation, chronology),
with NO mixing. Each mode is pure. `"claude"` ONLY ever calls Claude, the llama modes NEVER call
Claude (even if `ANTHROPIC_API_KEY` is set), and `"rules-only"` calls no LLM:

- `"claude"` -> everything on Claude (Anthropic API)
- `"cloud-llama"` -> everything on the cloud OpenAI-compatible model (Together Llama-3.3-70B)
- `"local-llama"` -> everything on local Ollama (`LLM_MODEL`)
- `"rules-only"` -> NO LLM at all (fully deterministic; disables the hybrid + every `*_LLM_USE`)

`LLM_PROVIDER` and `LLM_USE` are DERIVED from `WORKFLOW_MODE`; do not set them directly.
`LLM_MODEL` is the Ollama model name (default `llama3.2:1b`), used only when
`WORKFLOW_MODE == "local-llama"`.

### Cloud backend (OpenAI-compatible) presets

Used when `LLM_PROVIDER == "cloud"`. Pick a host's `LLM_API_BASE_URL` + `LLM_API_MODEL`:

| Host | base_url | model |
|---|---|---|
| Together | `https://api.together.xyz/v1` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| OpenRouter | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct` |
| Fireworks | `https://api.fireworks.ai/inference/v1` | `accounts/fireworks/models/llama-v3p3-70b-instruct` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` (free tier; rate-limited) |
| Cerebras | `https://api.cerebras.ai/v1` | `llama-3.3-70b` |

70B is serverless on Together and gives the best soft columns (`context_label`/`find_status`).
The gradeable columns are regex/rule-driven, and so model-independent, which leaves cost as the only
tradeoff, and it is negligible here (~cents/sweep). NOTE: Llama 3.1-8B/3.2-3B Turbo are
NON-serverless on Together (they need a paid dedicated endpoint); the cheap serverless options are
`meta-llama/Meta-Llama-3-8B-Instruct-Lite` or `Qwen/Qwen2.5-7B-Instruct-Turbo`.

- `LLM_CONFIDENCE_THRESHOLD`: records below this go to LLM fallback.
- `LLM_BATCH_SIZE`: Layer 5 batching, how many low-confidence records to classify per LLM call.
  `0` = auto per backend (Claude 30 / Llama-70B 20 / small 3B-8B 10 / Ollama 8); `1` = one call per
  record (the old behavior, for an A/B comparison); `N` = fixed batch size.
- `ANTHROPIC_MODEL`: the Claude model for the REST API path (default `claude-sonnet-4-6`).
  Roughly deterministic (temperature=0), about 3× cheaper, and roughly on par with opus on findings.
  This is the model used in **Claude mode** by default (the CLI path's `CLAUDE_CLI_MODEL` only applies
  when `HYBRID_USE_CLAUDE_CLI`).
- `ANTHROPIC_ENDPOINT` / `ANTHROPIC_VERSION`: the Anthropic REST endpoint URL and API version header
  (rarely changed).

## Context & Chronology (Layers 5-6)

- `CHRONO_PROCESS_UNCERTAIN`: whether uncertain records get a chronology attempt.
- `CHRONO_UNCERTAIN_THRESHOLD`: min `context_confidence` for uncertain records to qualify.
- `CHRONO_LLM_USE`: set False to disable LLM context interpretation fallback.
- `CHRONO_DATE_LLM_USE`: set True to enable LLM date extraction (prone to hallucination).

## Pottery summary feature flags (Layer 3b + 7)

Layer 3b extraction + Layer 7 summary; see `src/pottery_summary.py`.

Codes like `P2.5`, `P4`, `C2`, and `5c` below are internal pipeline step labels (cross-references to
specific stages in the summary cascade), not config values.

- `POTTERY_EXTRACT_LLM_USE`: LLM fallback in pottery name extraction.
- `POTTERY_CONTEXT_LLM_USE`: LLM context classification + date improvement (P2.5).
- `POTTERY_DATE_LLM_USE`: LLM typological date fallback (P4, last resort).
- `POTTERY_LLM_DATE_OVERRIDE`: C2 (experimental, off), passage-grounded LLM date override.
  Forward-focused context fixes findings 2/3 but regresses finding 1, whose date precedes it in a
  shared sentence. Resolving all of them would need a context bounded by the neighboring finds; this
  is not worth the complexity for now.
- `POTTERY_DEDUP_LLM_USE`: LLM fallback for ambiguous prose-vs-table-reference dedup (deterministic
  markers run first).
- `POTTERY_SUPPRESS_SUMMARY_MENTIONS`: drop LLM-judged GENERAL recap/summary/interpretation
  re-mentions when the same pot is also a SPECIFIC find (prose over-detection).
- `POTTERY_CONSOLIDATE_LLM_USE`: Layer 7.4 find consolidation (coreference). Group same-ware
  mentions per site and let the LLM collapse recaps/duplicates of the same physical find (table+text
  and paragraph-to-paragraph). Conservative (keep-when-unsure); table cells never dropped.
- `POTTERY_SITE_CAPTION_BACKSTOP`: when the hybrid extracts NO site for a report, infer the single
  excavation site from the title + figure/plate captions via one focused LLM call (at settlement
  level, with hyphenated names kept). Strictly additive: it only fills an all-blank report and never
  overrides an extracted site. It is immune to chunking because it works on focused input, not the
  whole report.
- `POTTERY_REGNUM_UNION`: deterministic stabilizer for registration-numbered catalogs. It keys
  reg#-bearing finds by their reg#, collapses duplicate LLM emissions, and recovers catalog entries
  the LLM dropped (from the rule layer), so the catalog count == the distinct reg# set on every run.
  It is a no-op for finds without a registration number (non-catalog reports are unaffected).
- `POTTERY_CAI_SITE_CODES`: deterministic site key for Flemish CAI inventory extracts. It overrides
  `site_name` with the standalone 6-digit inventory code heading each find block (the authoritative
  location id), rather than the toponym the model grabs from a "Bron:" citation. It is gated on a
  strong format signal (at least 2 standalone 6-digit codes AND a corroborator: "NK:", an
  investigation keyword, or an explicit CAI mention), and is a no-op on every non-CAI report.

## Claude-hybrid full-report extraction (Layer 7)

See [design_notes.md](../design/design_notes.md).

- `POTTERY_HYBRID_LLM_USE`: when True, a frontier LLM reads the WHOLE report and produces the
  pottery summary directly (one `<report>.csv` per report), with a verbatim-quote anti-hallucination
  contract and deterministic typology-date grounding. The rule-based pipeline still runs and its
  output is passed to the hybrid as a temporary cross-check file (not kept). Model-agnostic: uses
  Claude when `ANTHROPIC_API_KEY` is set, else falls back to the configured cloud LLM (`LLM_API_*`),
  so the architecture is runnable without a Claude key.
- `POTTERY_HYBRID_RULE_CONFIRM`: Option 5c, rule-confirm merge. After Claude extracts, the rule
  pipeline's finds that Claude did NOT emit (per-ware surplus) are offered BACK to Claude as
  candidates; Claude confirms the genuine misses and rejects rule noise. The ensemble combines rule
  recall with LLM precision. It needs the rule output (run_pipeline passes it as a temporary
  cross-check file).
- `POTTERY_HYBRID_CONFIRM_THRESHOLD`: 5c confirm tuning. Candidates are pre-filtered to the rules'
  own "present" finds (#4), shown to Claude with surrounding context (#1), classified
  present/comparison/absent/duplicate/non_pottery with a confidence (#2,#6); kept only when
  label==present AND confidence ≥ this threshold.
- Provider priority for the hybrid extractor:
  1. `HYBRID_USE_CLAUDE_CLI` -> Claude Code CLI in headless mode (`claude -p`), which uses your Claude
     **Max/Pro subscription** (no API key, no per-token cost). Requires the `claude` CLI installed +
     logged in. Subject to subscription usage limits; slower.
  2. else `ANTHROPIC_API_KEY` set -> Anthropic REST API (pay-as-you-go).
  3. else -> fall back to the configured cloud LLM (Together/Llama) so it runs anyway.
- `CLAUDE_CLI_PATH`: path to the Claude Code CLI (if not on PATH).
- `CLAUDE_CLI_MODEL`: optional `--model` (e.g. `claude-opus-4-8`); `""` = CLI default.

## Roman scope filter (Layer 7)

The thesis covers the Roman period. The `roman_overlaps()` / `roman_in_scope()` predicates that
apply `ROMAN_WINDOW` live in `src/periods.py` (logic), keeping `config.py` declarative.

- `POTTERY_ROMAN_ONLY`: when ON, a find is kept only if it is UNDATED or its date range OVERLAPS
  the Roman window (so early-Roman/Augustan, Republican imports and late-Roman finds are all kept;
  purely medieval/modern finds are dropped). Applied to both the pipeline output and the gold side
  of the scorers so comparisons stay fair.
- `ROMAN_WINDOW`: POSITIVE-WIDTH overlap test (see `roman_overlaps`). A find is kept if it is
  undated or its date range genuinely overlaps this window. A mere boundary touch does NOT count, so
  a Medieval find dated 450..1500 (which only meets the window at the single point 450) is dropped,
  while a late-Roman find ending at 450 (starting earlier) is kept. Lower bound −52 = 52 BCE, the
  Battle of Alesia (Caesar's decisive victory over the Gauls), taken as the onset of Roman presence;
  upper bound 450 = end of the Roman period. Deliberately wider on the early side than `ROMAN_PERIOD`.
- `ROMAN_PERIOD`: conventional Roman period, used ONLY to FILL missing date endpoints from context
  (distinct from `ROMAN_WINDOW`, the scope filter). A find dated "2nd century or later" gets its
  missing end clamped to 450; "until the 3rd century" gets its missing start set to −12.
- `POTTERY_DROP_NONROMAN_LABELS`: secondary, DATES-SUBORDINATE label gate. It drops a find ONLY when
  the find is fully UNDATED and its label/context clearly names a SOLE non-Roman period, with no Roman
  mention to veto it. This catches undated "Medieval ware"-type leftovers that the date filter cannot,
  since that filter keeps undated finds. A find carrying any real date is governed solely by the
  `ROMAN_WINDOW` overlap above, so a "Roman to Medieval" span (dated with a Roman start), and anything
  that mentions Roman, is always kept.
- `ROMAN_MARKERS`: veto, any present means never flag as non-Roman.
- `NONROMAN_PERIOD_MARKERS`: period names (multilingual) that mark a find as non-Roman when undated.

## Standard-vocabulary mapping (Layer 7 tail)

Maps each find to an external standard controlled vocabulary, appending the `std_*` columns to the
summary CSV (see [output_schema.md](output_schema.md)). It is a deterministic, mode-independent
standards layer: each find is mapped to the Dutch national ABR vocabulary, so the results are reusable
alongside Archis and other national heritage data. It is separate from the scored evaluation (Layer 8
scores the find list and dates, not these mappings).

- `STANDARD_VOCAB_USE`: master toggle (default ON). When OFF, the `std_*` columns are not emitted and
  the output is byte-identical to the pre-feature schema.
- `STANDARD_VOCAB_STYLE`: which standard to use (default `"abr"`). Only `abr` (Dutch Archeologisch
  Basisregister) is implemented; a new style is a drop-in folder under
  `data/vocabularies/standards/<style>/`.

The maps are plain CSVs (no `rdflib` at runtime); regenerate them from the frozen ABR snapshot with
`tools/build_abr_maps.py`. See [data_files.md](data_files.md).

## rules-only enforcement

`LLM_USE` is the single global switch (derived from `WORKFLOW_MODE`). When it is False, the block at
the END of `config.py` forces EVERY other `*_LLM_USE` flag off, so the run is fully deterministic:
no LLM, no Claude-hybrid, no API calls. When it is True, the individual flags decide which LLM
features run. That block must stay last, after all flags are defined.

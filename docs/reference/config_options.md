# config.py option reference

The full per-flag rationale for `config.py`. `config.py` itself keeps short one-line
comments and points here for the detail. For the everyday settings (`WORKFLOW_MODE`,
`DEFAULT_REPORTS_DIR`, `BATCH_WORKERS`) see [../getting_started/configuration.md](../getting_started/configuration.md);
for keys see [../getting_started/api_keys.md](../getting_started/api_keys.md).

Sections below mirror the section banners in `config.py`.

## Secrets / credentials

API keys are read from environment variables (see `.env.example`); the literal fallbacks in
`config.py` are for local/private use only. **Strip the fallbacks and rotate the keys before this
repository is, or becomes, public.** Keys: `LLM_API_KEY` (cloud OpenAI-compatible backend),
`ANTHROPIC_API_KEY` (Claude REST API), `GOOGLE_VISION_API_KEY` (OCR).

## Text extraction & OCR (Layers 1–2)

OCR is for scanned / image-only PDFs that have no extractable text layer.

- `OCR_ENABLED` — master on/off for OCR of scanned / image-only pages.
- `OCR_PROVIDER` — `"google"` (Cloud Vision REST). `"tesseract"`/`"auto"` are reserved for later.
- `OCR_LANG_HINTS` — Google Vision language hints (English + Dutch by default).
- `GOOGLE_VISION_ENDPOINT` — the Cloud Vision REST endpoint (rarely changed).
- `OCR_DPI` — resolution to render a page → image before OCR.
- `OCR_MAX_IMAGE_DIM` — cap the longest rendered side (px): large scans otherwise exceed Google
  Vision's ~40 MB request limit.
- `OCR_MIN_TEXT_LAYER_CHARS` — a page with fewer real chars is treated as image-only → OCR.
- `OCR_RECHECK_CORRUPT_TEXT` — a page can have a LONG text layer that is nonetheless garbage: a
  broken PDF font / ToUnicode map renders correctly on screen but extracts as a glyph-substitution
  cipher (e.g. fi→U+087C, fl→U+087D, Syriac/Arabic space-substitutes). Such pages slip past the
  length gate above. When a page's density of corruption glyphs (non-Latin, non-punctuation,
  non-ligature, non-control code points) exceeds the threshold, re-read it via OCR (pixel-based, so
  it escapes the broken font map) and KEEP the original text layer as a secondary corpus for
  verbatim-quote validation.
  - `OCR_CORRUPTION_GLYPH_PER_1K` — corruption glyphs per 1000 chars to flag a page (corrupt
    reports ~3–9, clean = 0).
  - `OCR_CORRUPTION_MIN_GLYPHS` — also require this many in absolute terms (guards tiny pages).
- `OCR_STRIP_MARGINALIA` — a page/folio number or running header printed in the top/bottom margin
  gets OCR'd as an isolated bare token (e.g. "1310" top-left) which the extractor then mistakes for
  a find/registration number — OCR flattens away the position that would reveal it as a header.
  Google Vision (DOCUMENT_TEXT_DETECTION) already returns per-block bounding boxes for free, so we
  drop a block when ALL hold: it sits in the margin band, is isolated from the body by a large
  vertical gap, and is a short line. Long captions (which carry real context) fail the length test
  and are kept. Only affects OCR'd pages; text-layer PDFs keep their native reading structure.
  - `OCR_MARGIN_BAND_FRAC` — block must lie within this fraction of page height from the top/bottom edge.
  - `OCR_MARGIN_GAP_FRAC` — ...and be separated from the nearest body block by ≥ this fraction of page height.
  - `OCR_MARGIN_MAX_CHARS` — ...and be a short line (protects real captions, which are long).
  - `OCR_MARGIN_MAX_WORDS` — ...and have at most this many words.

## Chunking

Cleaned text is split into overlapping character chunks that bound the context window used by
detection and the LLM layers (see [layer_2](../workflow/specs/layer_2.md)).

- `CHUNK_SIZE` — chunk length in characters.
- `CHUNK_OVERLAP` — overlap between consecutive chunks, so a term near a chunk edge keeps context on
  both sides.
- `CONTEXT_WINDOW_CHARS` — width of the context window stored with each detected candidate.

## LLM backend & master switch

`WORKFLOW_MODE` is the MASTER switch for which model the ENTIRE workflow talks to — both the hybrid
extractor AND the rule-layer helpers (context classification, dedup, consolidation, chronology) —
with NO mixing. Each mode is pure: `"claude"` ONLY ever calls Claude, the llama modes NEVER call
Claude (even if `ANTHROPIC_API_KEY` is set), and `"rules-only"` calls no LLM:

- `"claude"` → everything on Claude (Anthropic API)
- `"cloud-llama"` → everything on the cloud OpenAI-compatible model (Together Llama-3.3-70B)
- `"local-llama"` → everything on local Ollama (`LLM_MODEL`)
- `"rules-only"` → NO LLM at all (fully deterministic; disables the hybrid + every `*_LLM_USE`)

`LLM_PROVIDER` and `LLM_USE` are DERIVED from `WORKFLOW_MODE` — do not set them directly.
`LLM_MODEL` is the Ollama model name, used only when `WORKFLOW_MODE == "local-llama"`.

### Cloud backend (OpenAI-compatible) presets

Used when `LLM_PROVIDER == "cloud"`. Pick a host's `LLM_API_BASE_URL` + `LLM_API_MODEL`:

| Host | base_url | model |
|---|---|---|
| Together | `https://api.together.xyz/v1` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| OpenRouter | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct` |
| Fireworks | `https://api.fireworks.ai/inference/v1` | `accounts/fireworks/models/llama-v3p3-70b-instruct` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` (free tier; rate-limited) |
| Cerebras | `https://api.cerebras.ai/v1` | `llama-3.3-70b` |

70B is serverless on Together and gives the best soft columns (`context_label`/`find_status`);
gradeable columns are regex/rule-driven (model-independent) so cost is the only tradeoff, and it's
negligible here (~cents/sweep). NOTE: Llama 3.1-8B/3.2-3B Turbo are NON-serverless on Together (need
a paid dedicated endpoint); serverless cheap options are `meta-llama/Meta-Llama-3-8B-Instruct-Lite`
or `Qwen/Qwen2.5-7B-Instruct-Turbo`.

- `LLM_CONFIDENCE_THRESHOLD` — records below this go to LLM fallback.
- `LLM_BATCH_SIZE` — Layer 5 batching: how many low-confidence records to classify per LLM call.
  `0` = auto per backend (Claude 30 / Llama-70B 20 / small 3B-8B 10 / Ollama 8); `1` = one call per
  record (the old behaviour, for an A/B comparison); `N` = fixed batch size.
- `ANTHROPIC_MODEL` — the Claude model for the REST API path (default `claude-sonnet-4-6`):
  deterministic-ish (temperature=0); ~3× cheaper; ≈ opus on findings. This is the model used in
  **Claude mode** by default (the CLI path's `CLAUDE_CLI_MODEL` only applies when `HYBRID_USE_CLAUDE_CLI`).
- `ANTHROPIC_ENDPOINT` / `ANTHROPIC_VERSION` — the Anthropic REST endpoint URL and API version header
  (rarely changed).

## Context & Chronology (Layers 5–6)

- `CHRONO_PROCESS_UNCERTAIN` — whether uncertain records get a chronology attempt.
- `CHRONO_UNCERTAIN_THRESHOLD` — min `context_confidence` for uncertain records to qualify.
- `CHRONO_LLM_USE` — set False to disable LLM context interpretation fallback.
- `CHRONO_DATE_LLM_USE` — set True to enable LLM date extraction (prone to hallucination).

## Pottery summary feature flags (Layer 3b + 7)

Layer 3b extraction + Layer 7 summary; see `src/pottery_summary.py`.

- `POTTERY_EXTRACT_LLM_USE` — LLM fallback in pottery name extraction.
- `POTTERY_CONTEXT_LLM_USE` — LLM context classification + date improvement (P2.5).
- `POTTERY_DATE_LLM_USE` — LLM typological date fallback (P4, last resort).
- `POTTERY_LLM_DATE_OVERRIDE` — C2 (experimental, off): passage-grounded LLM date override.
  Forward-focused context fixes findings 2/3 but regresses finding 1 (its date precedes it in a
  shared sentence). A neighbouring-find-bounded context would be needed to resolve all; not worth
  the complexity for now.
- `POTTERY_DEDUP_LLM_USE` — LLM fallback for ambiguous prose-vs-table-reference dedup (deterministic
  markers run first).
- `POTTERY_SUPPRESS_SUMMARY_MENTIONS` — drop LLM-judged GENERAL recap/summary/interpretation
  re-mentions when the same pot is also a SPECIFIC find (prose over-detection).
- `POTTERY_CONSOLIDATE_LLM_USE` — Layer 7.4 find consolidation (coreference): group same-ware
  mentions per site and let the LLM collapse recaps/duplicates of the same physical find (table+text
  and paragraph-to-paragraph). Conservative (keep-when-unsure); table cells never dropped.
- `POTTERY_SITE_CAPTION_BACKSTOP` — when the hybrid extracts NO site for a report, infer the single
  excavation site from the title + figure/plate captions via one focused LLM call (settlement-level,
  hyphenated names kept). Strictly additive: only fills an all-blank report, never overrides an
  extracted site. Chunking-immune (focused input, not the whole report).
- `POTTERY_REGNUM_UNION` — deterministic stabiliser for registration-numbered catalogues: key
  reg#-bearing finds by their reg#, collapse LLM duplicate emissions, and recover catalogue entries
  the LLM dropped (from the rule layer) → the catalogue count == the distinct reg# set on every run.
  No-op for finds without a registration number (non-catalogue reports unaffected).
- `POTTERY_CAI_SITE_CODES` — deterministic site key for Flemish CAI inventory extracts: override
  `site_name` with the standalone 6-digit inventory code heading each find block (the authoritative
  location id), not the toponym the model grabs from a "Bron:" citation. Gated on a strong format
  signal (≥2 standalone 6-digit codes AND a corroborator: "NK:", an investigation keyword, or an
  explicit CAI mention); no-op on every non-CAI report.

## Claude-hybrid full-report extraction (Layer 7)

See [design_notes.md](../design/design_notes.md).

- `POTTERY_HYBRID_LLM_USE` — when True, a frontier LLM reads the WHOLE report and produces the
  pottery summary directly (one `<report>.csv` per report), with a verbatim-quote anti-hallucination
  contract and deterministic typology-date grounding. The rule-based pipeline still runs and its
  output is passed to the hybrid as a temporary cross-check file (not kept). Model-agnostic: uses
  Claude when `ANTHROPIC_API_KEY` is set, else falls back to the configured cloud LLM (`LLM_API_*`),
  so the architecture is runnable without a Claude key.
- `POTTERY_HYBRID_RULE_CONFIRM` — Option 5c, rule-confirm merge: after Claude extracts, the rule
  pipeline's finds that Claude did NOT emit (per-ware surplus) are offered BACK to Claude as
  candidates; Claude confirms the genuine misses and rejects rule noise. Ensemble = rule recall +
  LLM precision. Needs the rule output (run_pipeline passes it as a temporary cross-check file).
- `POTTERY_HYBRID_CONFIRM_THRESHOLD` — 5c confirm tuning: candidates are pre-filtered to the rules'
  own "present" finds (#4), shown to Claude with surrounding context (#1), classified
  present/comparison/absent/duplicate/non_pottery with a confidence (#2,#6); kept only when
  label==present AND confidence ≥ this threshold.
- Provider priority for the hybrid extractor:
  1. `HYBRID_USE_CLAUDE_CLI` → Claude Code CLI in headless mode (`claude -p`), which uses your Claude
     **Max/Pro subscription** (no API key, no per-token cost). Requires the `claude` CLI installed +
     logged in. Subject to subscription usage limits; slower.
  2. else `ANTHROPIC_API_KEY` set → Anthropic REST API (pay-as-you-go).
  3. else → fall back to the configured cloud LLM (Together/Llama) so it runs anyway.
- `CLAUDE_CLI_PATH` — path to the Claude Code CLI (if not on PATH).
- `CLAUDE_CLI_MODEL` — optional `--model` (e.g. `claude-opus-4-8`); `""` = CLI default.

## Roman scope filter (Layer 7)

The thesis covers the Roman period. The `roman_overlaps()` / `roman_in_scope()` predicates that
apply `ROMAN_WINDOW` live in `src/periods.py` (logic), keeping `config.py` declarative.

- `POTTERY_ROMAN_ONLY` — when ON, a find is kept only if it is UNDATED or its date range OVERLAPS
  the Roman window (so early-Roman/Augustan, Republican imports and late-Roman finds are all kept;
  purely medieval/modern finds are dropped). Applied to both the pipeline output and the gold side
  of the scorers so comparisons stay fair.
- `ROMAN_WINDOW` — POSITIVE-WIDTH overlap test (see `roman_overlaps`): a find is kept if it is
  undated or its date range genuinely overlaps this window — a mere boundary touch does NOT count, so
  a Medieval find dated 450..1500 (which only meets the window at the single point 450) is dropped,
  while a late-Roman find ending at 450 (starting earlier) is kept. Lower bound −52 = 52 BCE, the
  Battle of Alesia (Caesar's decisive victory over the Gauls), taken as the onset of Roman presence;
  upper bound 450 = end of the Roman period. Deliberately wider on the early side than `ROMAN_PERIOD`.
- `ROMAN_PERIOD` — conventional Roman period, used ONLY to FILL missing date endpoints from context
  (distinct from `ROMAN_WINDOW`, the scope filter). A find dated "2nd century or later" gets its
  missing end clamped to 450; "until the 3rd century" gets its missing start set to −12.
- `POTTERY_DROP_NONROMAN_LABELS` — secondary, DATES-SUBORDINATE label gate: drop a find ONLY when it
  is fully UNDATED and its label/context clearly names a SOLE non-Roman period, with no Roman mention
  to veto it. This catches undated "Medieval ware"-type leftovers that the date filter (which keeps
  undated finds) cannot. A find carrying any real date is governed solely by the `ROMAN_WINDOW`
  overlap above, so a "Roman → Medieval" span (dated with a Roman start) — and anything that mentions
  Roman — is always kept.
- `ROMAN_MARKERS` — veto: any present → never flag as non-Roman.
- `NONROMAN_PERIOD_MARKERS` — period names (multilingual) that mark a find as non-Roman when undated.

## rules-only enforcement

`LLM_USE` is the single global switch (derived from `WORKFLOW_MODE`). When False, the block at the
END of `config.py` forces EVERY other `*_LLM_USE` flag off so the run is fully deterministic — no
LLM, no Claude-hybrid, no API calls. When True, the individual flags decide which LLM features run.
That block must stay last, after all flags are defined.

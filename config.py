"""Central configuration for the chronology pipeline.

All filesystem paths and behaviour toggles live here so the pipeline can be steered
without touching code. Sections (in pipeline order):
  Paths · Secrets · Text extraction & OCR (L1-2) · Chunking · LLM backend & master switch ·
  Context & Chronology (L5-6) · Pottery summary flags (L3b+7) · Claude-hybrid extraction (L7) ·
  Roman scope filter (L7) · rules-only enforcement.

Per-flag rationale (the long version) lives in docs/reference/config_options.md; the comments
here are deliberately short. API keys are read from environment variables (see .env.example);
never commit real keys when this repository is, or becomes, public.
"""
import os
from pathlib import Path

# =============================== Paths ===============================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PATTERNS_DIR = DATA_DIR / "patterns"          # generated regex detection patterns
VOCAB_DIR = DATA_DIR / "vocabularies"         # source vocabularies (CSV) + reference maps (JSON)

# --- Input reports ---
# The batch folder is given on the command line: `run_pipeline.py input_files/reports/<folder>`.
# The workflow processes EVERY PDF in that folder, writing one <report>.csv per report to
# output_files/reports/<folder>/.
BATCH_WORKERS = 4    # reports processed in parallel (1 = sequential with live console output)

# --- Detection pattern files (generated from the master vocab CSVs; see tools/csv_to_patterns.py) ---
CHRONOLOGY_PATTERNS_PATH = PATTERNS_DIR / "chronology_patterns.json"
CENTURY_PATTERNS_PATH = PATTERNS_DIR / "century_patterns.json"
POTTERY_TRIGGERS_PATH = PATTERNS_DIR / "pottery_triggers.json"
POTTERY_PATTERNS_PATH = PATTERNS_DIR / "pottery_patterns.json"

# --- Reference vocabularies (single source of truth for pottery dates/names) ---
POTTERY_CSV_REF_PATH = VOCAB_DIR / "pottery_vocab_normalized.csv"

# --- Output files ---
# One pottery-summary CSV per report at output_files/reports/<folder>/<report>.csv, where <folder>
# mirrors the input batch folder. (Legacy results.json/csv/review sidecars are no longer written.)
OUTPUT_REPORTS_DIR = BASE_DIR / "output_files" / "reports"

# --- Standard-vocabulary mapping (Layer 7 tail) ---
# When on, each find is mapped to a standard controlled vocabulary and the std_* columns
# (ware/form/combiterm code+label) are appended to the summary CSV — interoperability only,
# deterministic, mode-independent, and unscored by Layer 8. Maps live under
# data/vocabularies/standards/<style>/ (see tools/build_abr_maps.py).
# Only "abr" is implemented at the moment.
STANDARD_VOCAB_USE = True
STANDARD_VOCAB_STYLE = "abr"

# ========================= Secrets / credentials =========================
# Auto-load a .env file (if present) so the keys below are picked up WITHOUT manually sourcing it.
# A real environment variable (e.g. an explicit `export`/`set -a && . ./.env`) takes precedence —
# load_dotenv does not override what is already set. If python-dotenv is not installed the keys
# simply come from the real environment as before. See docs/getting_started/api_keys.md.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Keys are read from the environment / .env. Never commit real keys (config.py is git-tracked; the
# .env is gitignored). STRIP any literal fallbacks and ROTATE the keys before this repo goes public.
GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", "")     # OCR (Google Cloud Vision)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # Claude REST API
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")            # cloud OpenAI-compatible backend

# ===================== Text extraction & OCR (Layers 1-2) =====================
# OCR is for scanned / image-only PDFs with no extractable text layer. See docs/reference/config_options.md.
OCR_ENABLED = True
OCR_PROVIDER = "google"          # "google" (Cloud Vision REST). "tesseract"/"auto" reserved for later.
OCR_DPI = 350                    # resolution to render a page -> image before OCR
OCR_MAX_IMAGE_DIM = 4500         # cap longest rendered side (px); keeps under Vision's ~40 MB limit
OCR_LANG_HINTS = ["en", "nl"]    # Google Vision language hints (English + Dutch)
OCR_MIN_TEXT_LAYER_CHARS = 10    # a page with fewer real chars is treated as image-only -> OCR
GOOGLE_VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
# Re-OCR pages whose text layer is a glyph-substitution cipher (broken PDF font), keeping the
# original layer as a secondary corpus for verbatim-quote validation.
OCR_RECHECK_CORRUPT_TEXT = True
OCR_CORRUPTION_GLYPH_PER_1K = 0.5   # corruption glyphs per 1000 chars to flag a page (corrupt ~3-9, clean = 0)
OCR_CORRUPTION_MIN_GLYPHS = 3       # also require this many in absolute terms (guards tiny pages)
# Strip page numbers / running headers OCR'd as isolated bare tokens (else mistaken for find/reg
# numbers). Uses Vision bounding boxes; only affects OCR'd pages. Long captions are kept.
OCR_STRIP_MARGINALIA = True
OCR_MARGIN_BAND_FRAC = 0.08         # block must lie within this fraction of page height from top/bottom edge
OCR_MARGIN_GAP_FRAC = 0.03          # ...and be separated from the nearest body block by >= this fraction
OCR_MARGIN_MAX_CHARS = 30           # ...and be a short line (protects real captions, which are long)
OCR_MARGIN_MAX_WORDS = 5            # ...and have at most this many words

# ============================= Chunking =============================
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
CONTEXT_WINDOW_CHARS = 300

# ==================== LLM backend & master switch ====================
# WORKFLOW_MODE is the MASTER switch for which model the ENTIRE workflow talks to (hybrid extractor
# AND rule-layer helpers), with NO mixing. Each mode is pure. See docs/reference/config_options.md.
#   "claude"      -> everything on Claude (Anthropic API)
#   "cloud-llama" -> everything on the cloud OpenAI-compatible model (Together Llama-3.3-70B)
#   "local-llama" -> everything on local Ollama (LLM_MODEL)
#   "rules-only"  -> NO LLM at all (fully deterministic; disables the hybrid + every *_LLM_USE)
WORKFLOW_MODE = "claude"
_WORKFLOW_MODES = {            # mode -> (LLM_PROVIDER, LLM_USE)
    "claude":      ("anthropic", True),
    "cloud-llama": ("cloud",     True),
    "local-llama": ("ollama",    True),
    "rules-only":  ("anthropic", False),   # provider irrelevant (no LLM calls)
}
if WORKFLOW_MODE not in _WORKFLOW_MODES:
    raise ValueError(f"Unknown WORKFLOW_MODE {WORKFLOW_MODE!r}; pick one of {list(_WORKFLOW_MODES)}")
# LLM_PROVIDER and LLM_USE are DERIVED from WORKFLOW_MODE -- do not set them directly.
LLM_PROVIDER, LLM_USE = _WORKFLOW_MODES[WORKFLOW_MODE]   # "ollama" | "cloud" | "anthropic"
LLM_MODEL = "llama3.2:1b"        # ollama model (used when WORKFLOW_MODE == "local-llama")

# --- Cloud backend (OpenAI-compatible: Together / OpenRouter / Fireworks / Groq / Cerebras) ---
# Used when LLM_PROVIDER == "cloud". Host presets (base_url + model) in docs/reference/config_options.md.
LLM_API_BASE_URL = "https://api.together.xyz/v1"
LLM_API_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"   # 70B is serverless on Together; key in Secrets above
LLM_CONFIDENCE_THRESHOLD = 0.75  # records below this go to LLM fallback
LLM_BATCH_SIZE = 0               # Layer 5 batching: 0 = auto per backend; 1 = one call/record; N = fixed size

# --- Anthropic backend (Claude REST API; key in Secrets above) ---
ANTHROPIC_MODEL = "claude-sonnet-4-6"   # deterministic-ish (temperature=0); ~3x cheaper; ~= opus on findings
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# ==================== Context & Chronology (Layers 5-6) ====================
CHRONO_PROCESS_UNCERTAIN = True   # whether uncertain records get a chronology attempt
CHRONO_UNCERTAIN_THRESHOLD = 0.6  # min context_confidence for uncertain records to qualify
CHRONO_LLM_USE = True             # set False to disable LLM context interpretation fallback
CHRONO_DATE_LLM_USE = False       # set True to enable LLM date extraction (prone to hallucination)

# ================= Pottery summary feature flags (Layer 3b + 7) =================
# Layer 3b extraction + Layer 7 summary (src/pottery_summary.py). Detail in docs/reference/config_options.md.
POTTERY_EXTRACT_LLM_USE = False    # LLM fallback in pottery name extraction
POTTERY_CONTEXT_LLM_USE = True     # LLM context classification + date improvement (P2.5)
POTTERY_DATE_LLM_USE = False       # LLM typological date fallback (P4, last resort)
POTTERY_LLM_DATE_OVERRIDE = False  # C2 (experimental, off): passage-grounded LLM date override
POTTERY_DEDUP_LLM_USE = True       # LLM fallback for ambiguous prose-vs-table dedup (markers run first)
POTTERY_SUPPRESS_SUMMARY_MENTIONS = True  # drop GENERAL recap re-mentions when the pot is also a SPECIFIC find
POTTERY_CONSOLIDATE_LLM_USE = True  # Layer 7.4 find consolidation/coreference (conservative; table cells kept)
POTTERY_SITE_CAPTION_BACKSTOP = True  # infer the site from title+captions when the hybrid extracts none (additive)
POTTERY_REGNUM_UNION = True        # deterministic stabiliser for registration-numbered catalogues (key by reg#)
POTTERY_CAI_SITE_CODES = True      # deterministic site key for Flemish CAI extracts (6-digit inventory code)

# ==================== Claude-hybrid extraction (Layer 7) ====================
# Frontier LLM reads the WHOLE report and produces the summary directly, with a verbatim-quote
# anti-hallucination contract. Rule pipeline still runs as a temporary cross-check. Model-agnostic
# (Claude if keyed, else the cloud LLM). See docs/design/design_notes.md + docs/reference/config_options.md.
POTTERY_HYBRID_LLM_USE = True
POTTERY_HYBRID_RULE_CONFIRM = True      # Option 5c: offer rule-only finds back to Claude to confirm/reject
POTTERY_HYBRID_CONFIRM_THRESHOLD = 0.7  # 5c: keep a candidate only when label==present AND confidence >= this
# Provider priority: 1) Claude Code CLI (subscription, no API key) if HYBRID_USE_CLAUDE_CLI;
# 2) else Anthropic REST API if ANTHROPIC_API_KEY set; 3) else the configured cloud LLM.
HYBRID_USE_CLAUDE_CLI = False
CLAUDE_CLI_PATH = "claude"              # path to the Claude Code CLI (if not on PATH)
CLAUDE_CLI_MODEL = "claude-opus-4-8"    # optional --model; "" = CLI default

# ======================== Roman scope filter (Layer 7) ========================
# The thesis covers the Roman period. Overlap predicates live in src/periods.py (this stays declarative).
# Full rationale (incl. the boundary-touch rule and the -52 BCE / Alesia choice) in docs/reference/config_options.md.
POTTERY_ROMAN_ONLY = True          # keep a find only if UNDATED or its date range overlaps ROMAN_WINDOW
ROMAN_WINDOW = (-52, 450)          # scope filter (positive-width overlap; -52 BCE Alesia .. 450 CE end of Roman)
ROMAN_PERIOD = (-12, 450)          # used ONLY to FILL missing date endpoints from context (not to filter)
POTTERY_DROP_NONROMAN_LABELS = True  # also drop fully-UNDATED finds whose label names a SOLE non-Roman period
ROMAN_MARKERS = ("roman", "romein", "römisch", "romain")   # veto: any present -> never flag as non-Roman
NONROMAN_PERIOD_MARKERS = (
    "medieval", "middeleeuw", "mittelalter", "médiéval",                            # Medieval
    "post-medieval", "post-middeleeuw", "nieuwe tijd", "neuzeit", "moderne tijd",   # post-medieval / modern
    "iron age", "ijzertijd", "eisenzeit",                                           # Iron Age
    "bronze age", "bronstijd", "bronzezeit",                                        # Bronze Age
    "neolithic", "neolithicum", "neolithikum",                                      # Neolithic
    "mesolithic", "mesolithicum", "palaeolithic", "paleolithic", "paleolithicum",   # Meso / Paleo
    "merovingian", "merovingisch", "carolingian", "karolingisch",                   # early-medieval Frankish
    "migration period", "völkerwanderung", "volksverhuizing",                       # Migration period
)

# ======================= rules-only enforcement (KEEP LAST) =======================
# When LLM_USE is False (WORKFLOW_MODE == "rules-only"), force EVERY *_LLM_USE flag off so the run is
# fully deterministic -- no LLM, no Claude-hybrid, no API calls. Must stay last, after all flags exist.
if not LLM_USE:
    POTTERY_EXTRACT_LLM_USE = POTTERY_CONTEXT_LLM_USE = POTTERY_DATE_LLM_USE = \
        POTTERY_LLM_DATE_OVERRIDE = POTTERY_DEDUP_LLM_USE = POTTERY_CONSOLIDATE_LLM_USE = \
        POTTERY_HYBRID_LLM_USE = POTTERY_HYBRID_RULE_CONFIRM = \
        CHRONO_LLM_USE = CHRONO_DATE_LLM_USE = False

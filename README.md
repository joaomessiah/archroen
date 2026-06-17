# ARCHROEN - Archaeological Chronology Extraction and Normalization 

A **workflow** that reads archaeological excavation reports (PDFs) and produces, for each report, a
per-report **pottery summary**: which pots a report says were found, with their typologies, dates, and
find sites, scoped to the Roman period. Built for a master's thesis.

## Documentation

Full documentation is in [docs/](docs/):

- **New here?** Start with [docs/getting_started/](docs/getting_started/) — from installing Python to
  running the workflow on your first report (written for non-IT readers).
- **How it works:** [docs/workflow/](docs/workflow/) — the architecture and the per-layer specs.
- **The research:** [docs/research/](docs/research/) — methodology, datasets, evaluation, and results.
- **Reference:** [docs/reference/](docs/reference/) — the output columns, the data files, a glossary.
- **Design rationale:** [docs/design/](docs/design/) — why it's built this way, and the workflow modes.

## Workflow overview

| Layer | Module(s) | What it does |
|---|---|---|
| 1 · Extraction | `extractor.py` | PDF → per-page text (OCR for scans) |
| 2 · Cleaning | `cleaner.py`, `structure.py` | clean text, then split into sections + overlapping chunks |
| 3 · Detection | `detection.py`, `pottery_extractor.py` | regex + trigger-word detection of pottery, periods, centuries |
| 4 · Normalization | `normalization.py` | collapse terms to canonical labels |
| 5 · Context interpretation | `interpretation.py` | classify as `present` / `absent` / `comparison` / `uncertain` / `irrelevant` |
| 6 · Chronology assignment | `chronology.py`, `date_parser.py`, `periods.py` | attach a date range by a strict priority order |
| 7 · Output, validation, dedup, consolidation | `output_builder.py`, `validator.py`, `pottery_summary.py`, `site_norm.py`, `consolidation.py`, `hybrid_extractor.py` | build per-find records → the pottery summary |
| 8 · Evaluation | `evaluation/evaluate.py`, `evaluation/evaluate_granular.py` | score the output against gold standards (separate harness) |

Layers 1–7 run in `run_pipeline.py`; Layer 8 is a standalone harness. See
[docs/workflow/architecture.md](docs/workflow/architecture.md) for the full data flow and
[docs/workflow/specs/](docs/workflow/specs/) for the per-layer specifications.

## Quick start

Requires **Python 3.12**.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The workflow runs in one of four **modes** via `WORKFLOW_MODE` in `config.py`: `rules-only` (no AI,
free, deterministic), `claude`, `cloud-llama`, or `local-llama`. Rules-only needs no API key — a good
first run. The AI modes read keys from the environment (copy [.env.example](.env.example) to `.env`).
Then:

```bash
.venv/bin/python3 run_pipeline.py        # process every PDF in DEFAULT_REPORTS_DIR
.venv/bin/python3 evaluation/evaluate.py # score the output against gold standards
```

Full setup and usage: [docs/getting_started/](docs/getting_started/). Modes and trade-offs:
[docs/design/workflow_modes.md](docs/design/workflow_modes.md).

## Repository layout

```
.
├── config.py              # all paths and behaviour toggles (incl. WORKFLOW_MODE)
├── run_pipeline.py        # orchestrator — Layers 1–7 (run_batch / main)
├── src/                   # workflow modules (Layers 1–7)
├── evaluation/            # Layer 8 scoring harness
├── tools/                 # pattern + dataset generators
├── data/
│   ├── patterns/          # generated regex detection patterns (JSON)
│   └── vocabularies/      # source vocabularies (CSV) + reference maps (JSON)
├── input_files/
│   ├── reports/<folder>/        # source report PDFs, grouped into batch folders
│   └── gold_standards/<folder>/ # manual gold-standard CSV per report, mirroring reports/<folder>/
├── output_files/reports/<folder>/ # results — one <report>.csv per report
├── docs/                  # documentation (start here)
└── notes/                 # working notes / scratch
```

## Inputs and outputs

A shared `<folder>` (batch) name mirrors across the tree, tied by the report's filename stem
(`new_rep_1.pdf` ↔ `new_rep_1.csv`):

| Role | Path |
|---|---|
| Input report PDF | `input_files/reports/<folder>/<report>.pdf` |
| Gold standard | `input_files/gold_standards/<folder>/<report>.csv` |
| **Output** | `output_files/reports/<folder>/<report>.csv` — the per-report pottery summary, the one deliverable |

The output columns are documented in [docs/reference/output_schema.md](docs/reference/output_schema.md).

## License

Code is released under the [MIT License](LICENSE). Note that the excavation report PDFs and the
pottery vocabularies may carry separate third-party terms.

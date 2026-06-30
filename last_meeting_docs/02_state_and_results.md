# 2 · Current State & Results

*Where the workflow stands today, and the numbers you'll be asked about.*

## Current state

- **Pipeline complete.** All layers (1-7) are implemented and run end-to-end via `run_pipeline.py`.
  The standalone evaluation harness (Layer 8) is also complete.
- **Three modes evaluated**: Rules-only, Claude, and Llama (cloud), on a frozen validation set.
- **One deliverable per report**: the pottery-summary CSV. Legacy per-record exports were dropped;
  validation now runs as a console sanity count only.
- **Standard-vocabulary mapping**: each find is also mapped to **the Dutch national standard**
  (Archeologisch Basisregister / Archis) via the `std_*` columns, so the output is directly reusable in
  Archis. Default on and deterministic; an interoperability layer, not one of the scored fields.
- **Datasets are in the repo and frozen**: the validation set's inputs, gold standards, and the
  per-mode outputs and scores all live under `docs/research/datasets/validation_set/`, so the
  results below are reproducible.
- **Repo is being prepared for public release** (cleanup, documentation, API keys moved to
  environment / `.env`). Code is MIT-licensed; report PDFs and vocabularies may carry separate terms.

## Headline results

Measured on the **validation set: 20 reports**, scored against hand-made gold standards.

**Metric (field-level correctness)** = (`exact` + `acceptable`) ÷ all field verdicts, over the union
of gold and workflow findings, across **five fields per finding** (site, pottery, typology, start
date, end date).

| Mode | Field-level correctness |
|---|---|
| **Claude mode** | **95.6 %** |
| **Llama mode** (cloud Llama-3.3-70B) | **77.3 %** |
| **Rules-only mode** | **47.9 %** |

Claude mode is clearly strongest; Llama is a solid mid-point; Rules-only is the deterministic floor.
The AI modes' advantage is on the **context-dependent judgments rules alone can't make**.

## Per-field breakdown

Field-level correctness by field:

| Field | Claude | Llama | Rules-only |
|---|---:|---:|---:|
| Site name | 95.9 % | 75.1 % | **3.3 %** |
| Pottery name | 97.9 % | 81.9 % | 66.9 % |
| Typology | 97.9 % | 77.5 % | 64.5 % |
| Start date | 93.8 % | 76.3 % | 54.9 % |
| End date | 92.2 % | 75.5 % | 50.1 % |

## What the numbers actually show (the talking points)

- **Site resolution is where Rules-only collapses (3.3 %).** Without an AI step, the deterministic
  string matching can't pick the right place from messy, multi-site report text. Both AI modes
  recover this almost completely (Claude 95.9 %). → *strongest single argument for the LLM-led design.*
- **Rules-only massively over-claims** (≈470 over-claim field-slots vs 10 for Claude). With no AI
  presence-filtering, dedup, or consolidation, it emits many findings the gold doesn't contain,
  inflating the list. This is the biggest driver of its low score.
- **Llama's main gap is recall** (it omits more genuine findings than Claude), while keeping
  over-claiming modest.
- **Typology and pottery name are the strongest fields even for Rules-only**, because they rest on
  the deterministic vocabulary / typology tables. Dates and especially site names are where the AI
  adds the most.

## Known limitations (be ready to volunteer these)

- **Gold standards are deliberately conservative** ("silver gold"). Some workflow extras are actually
  real but not in the gold, so the AI modes' recall is, if anything, **understated**, not inflated.
- **AI modes are not perfectly reproducible**, low temperature, but not exact across runs. Only
  Rules-only is fully deterministic.
- **Coverage is bounded by the vocabularies** in `data/`, a pottery type not in the vocab can be
  missed in the rule layer (the LLM read mitigates this).
- **Validation set is 20 reports**, representative but small; broader generalization is a fair
  question (see doc 4).
- **Roman-scope filtering** removes non-Roman finds; there's a small risk of dropping borderline
  real finds (the window is deliberately generous: 52 BCE to 450 CE).

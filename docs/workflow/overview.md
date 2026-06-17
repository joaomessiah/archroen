# Workflow overview

## What the workflow does

It reads archaeological excavation reports (PDFs) and produces, for each report, a single tidy table:
**the pottery summary** — one row per distinct pottery find the report mentions, with the find's name,
typology, quantity, find site, and the **date range** it belongs to. The focus is the **Roman period**.

The reports are real-world grey literature — mostly Dutch and English, sometimes scanned, with finds
described in running prose, in tables, and in figure captions. Turning that into a clean, comparable
table of dated finds is the problem the workflow solves.

## The single deliverable

For every report `<report>.pdf` the workflow writes exactly one file:

```
output_files/reports/<folder>/<report>.csv
```

This pottery summary is **the** output. Its columns are documented in
[../reference/output_schema.md](../reference/output_schema.md).

## How it's organised: layers

The workflow is a sequence of **layers**, each doing one well-defined job and passing its result to the
next. This makes each step independently understandable and testable.

| Layer | Job |
|---|---|
| 1 | **Extraction** — read text from the PDF, page by page (OCR for scans) |
| 2 | **Cleaning** — clean the text, then split it into sections and overlapping chunks |
| 3 | **Detection** — find pottery/period/century mentions with regex patterns + trigger words |
| 4 | **Normalization** — collapse each detected term to a canonical label |
| 5 | **Context interpretation** — is the find *present*, *absent*, a *comparison*, *uncertain*, or *irrelevant*? |
| 6 | **Chronology assignment** — attach a date range by a strict priority order |
| 7 | **Output assembly, validation, deduplication, and consolidation** — build the per-find records and collapse repeats into the pottery summary |
| 8 | **Evaluation** — score the summaries against hand-made gold standards (separate harness) |

Layers 1–7 run inside `run_pipeline.py`. **Layer 8 (evaluation)** is a standalone harness used for the
research, not part of producing a summary. See [architecture.md](architecture.md) for the full data
flow and [specs/](specs/) for each layer in detail.

## An LLM-led hybrid

The workflow is **LLM-led**. In its default and best-performing mode, a frontier model (Claude) reads
the *whole report* and produces the find list directly — this whole-report read is the hybrid step in
Layer 7. An earlier rules-only design did not generalise to the messiness of real grey literature, so
the language model became the primary reader.

The deterministic rules remain essential, in a **supporting** role: they *ground and check* the model.
Dates come from the typology/period tables (never the model's numbers), names from the vocabulary, and
site resolution is purely string-based; every model-produced find must carry a **verbatim quote** from
the report (anti-hallucination). And run with no model at all (**Rules-only mode**), the same rule
pipeline is a fully deterministic, free baseline.

How much the model is used is set by one master switch, `WORKFLOW_MODE`, with four settings:
**Claude mode** and **Llama mode** (the cloud hybrids), a local-Llama option, and **Rules-only mode**
(no AI). The trade-offs and the measured comparison live in
[../design/workflow_modes.md](../design/workflow_modes.md) and
[../research/results.md](../research/results.md).

## Scope and limits

- The workflow targets **Roman-period** pottery; finds clearly outside that window are filtered out
  (`POTTERY_ROMAN_ONLY`).
- Detection coverage is bounded by the **vocabularies** in `data/` (see
  [../reference/data_files.md](../reference/data_files.md)).
- The AI-assisted steps are low-temperature but **not perfectly reproducible**; Rules-only mode is
  fully deterministic. See [../research/limitations.md](../research/limitations.md).

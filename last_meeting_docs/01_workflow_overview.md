# 1 · Workflow Overview

*Read this first. Plain-language picture of what the workflow is and how it works.*

## What it does (one paragraph)

The workflow reads **archaeological excavation reports (PDFs)** and produces, for each report, a
single tidy table, the **pottery summary**. One row per distinct pottery find the report mentions,
with the find's **name, typology, quantity, find site, and date range**. The focus is the
**Roman period**: finds clearly outside that window are filtered out. The reports are real-world
"grey literature", mostly Dutch and English, sometimes scanned, with finds described in running
prose, in tables, and in figure captions. Turning that mess into a clean, comparable table of dated
finds is the problem the workflow solves.

**The single deliverable:** for every `report.pdf` it writes exactly one file,
`output_files/reports/<folder>/<report>.csv`. That CSV *is* the output. Nothing else matters
downstream.

## How it's built: 7 layers (+ a separate evaluation step)

The workflow is a pipeline of **layers**, each doing one job and passing its result to the next.
You don't need the internals, just the shape:

| Layer | Job (in plain terms) |
|---|---|
| 1 · Extraction | Read the text out of the PDF, page by page (OCR for scanned pages) |
| 2 · Cleaning | Clean the text and split it into sections / chunks |
| 3 · Detection | Find pottery, period, and century mentions (regex patterns + trigger words) |
| 4 · Normalization | Collapse each detected term to one canonical name |
| 5 · Context interpretation | Is this find *present*, *absent*, a *comparison*, *uncertain*, or *irrelevant*? |
| 6 · Chronology assignment | Attach a date range, using a strict priority order |
| 7 · Output + dedup + consolidation | Build the per-find rows and collapse repeats into the final summary |
| 8 · Evaluation | Score the summaries against hand-made gold standards (**separate**, not part of producing a summary) |

Layers 1-7 run inside `run_pipeline.py`. Layer 8 is a standalone research harness used to measure
accuracy, not to produce output.

## The key idea: it's **LLM-led**, with rules as the safety net

This is the most important conceptual point and likely the center of the meeting.

- In its best mode, a **frontier model (Claude) reads the whole report** and produces the find list
  directly. This whole-report read is the "hybrid" step in Layer 7.
- **Why:** an earlier *rules-only* design did not generalize to the messiness of real grey
  literature. So the language model became the **primary reader**.
- **The deterministic rules stay essential, in a supporting role, they ground and check the model:**
  - **Dates** come from the typology / period **tables**, never from the model's own numbers.
  - **Names** come from the controlled vocabulary.
  - **Site resolution** is purely string-based.
  - Every model-produced find must carry a **verbatim quote** from the report
    (anti-hallucination contract).
- With no model at all (**Rules-only mode**), the same rule pipeline runs as a fully deterministic,
  free baseline.

> One-liner for the meeting: *"The LLM reads and judges; the rules constrain and verify. Numbers and
> names come from tables and vocabularies, not from the model's imagination."*

## The 3 modes (one master switch: `WORKFLOW_MODE`)

The whole workflow talks to **one** backend per run, there is **no mixing**. Three modes were
evaluated in the thesis (a 4th, `local-llama`, exists for offline experiments but was not evaluated).

### Rules-only mode: the deterministic baseline
- **No AI at all.** Pure regex / vocabulary / table lookups.
- **Free, offline, fully reproducible** (same input → same output every time).
- The honest floor: shows what is achievable *without* a language model.
- This is where you can start with no API key.

### Claude mode: the best performer
- The full **LLM-led hybrid** using Claude (Anthropic API).
- Claude reads the whole report; rules ground and check it.
- **Highest accuracy in the thesis** (see doc 2).
- Needs an API key + internet; low-temperature but not perfectly reproducible.

### Llama mode (cloud): the open-model comparison point
- Same hybrid design, but the backend is a **cloud open model (Llama-3.3-70B, via Together)**.
- The fair "could an open model do this?" comparison.
- **Mid-range accuracy**, solid, but below Claude (its main weakness is recall: it misses more
  genuine finds).

### Trade-offs at a glance

| | Rules-only | Claude | Llama (cloud) |
|---|---|---|---|
| **Cost** | free | paid API | paid API |
| **Internet** | not needed | required | required |
| **Reproducibility** | fully deterministic | not exact | not exact |
| **Accuracy (thesis)** | floor / baseline | **highest** | mid |
| **Setup** | none | Anthropic key | Together key |

## What a row in the output looks like

The CSV has one row per distinct find. The columns (you don't need to memorize these, just recognize
the shape):

`report_id, site_name, page, pottery, typology, term_found, term_found_normalized_en, quantity,
start_date, end_date, date_method, context_label, ...certainty levels & LLM reasoning..., original_text`

The important ones for a discussion: **site_name, pottery, typology, start_date, end_date**, these
are the five fields the evaluation scores (see doc 2). Each find also carries the **verbatim quote**
(`original_text`) that justifies it.

By default the workflow then appends seven **ABR standard-vocabulary** columns (`std_*`) that map each
find to **the Dutch national archaeological standard** (Archeologisch Basisregister / Archis), so the
output feeds straight into the national heritage infrastructure without manual re-coding. The mapping is
deterministic; it is an interoperability layer rather than one of the five scored fields.

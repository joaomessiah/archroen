# How to run the workflow

This is the full guide to running the workflow. It covers choosing a mode, running one report or a
whole folder, where the results go, and how to score them against gold standards. If you just want a
quick first result, start with [quickstart.md](quickstart.md).

Run all commands from the project folder, in the terminal you set up in
[prerequisites.md](prerequisites.md) (**PowerShell** on Windows, **Terminal** on macOS/Linux).

> Commands are shown for **macOS / Linux** and **Windows**; run the one for your system.

## 1. Choose a mode

The workflow has one master switch, `WORKFLOW_MODE` in `config.py`, that decides whether and how it
uses AI. Each mode is "pure": there is no mixing between them.

| `WORKFLOW_MODE` | In this documentation | What it does | Key needed |
|---|---|---|---|
| `"rules-only"` | **Rules-only mode** | No AI at all: fully deterministic | none |
| `"claude"` | **Claude mode** | Everything via Claude (Anthropic) | `ANTHROPIC_API_KEY` |
| `"cloud-llama"` | **Llama mode** | Everything via the cloud Llama-3.3-70B model (Together) | `LLM_API_KEY` |
| `"local-llama"` | *(local Llama)* | Everything via a local model through [Ollama](https://ollama.com) | none (runs locally) |

The thesis evaluated **Rules-only mode**, **Claude mode**, and **Llama mode**. To switch, edit the line
in `config.py`:

```python
WORKFLOW_MODE = "claude"
```

> **local-Llama mode** also needs [Ollama](https://ollama.com) installed and the model pulled
> (`ollama pull llama3.2:1b`). It is experimental and was not part of the thesis evaluation.

> **Keys load automatically** from `.env` when you run the workflow, so there's nothing extra to do (see
> [api_keys.md](api_keys.md)).
>
> **One exception to the table above:** reading scanned PDFs (OCR) always needs the Google Vision key
> (`GOOGLE_VISION_API_KEY`), whatever mode you choose. If you don't need it, set `OCR_ENABLED = False`.

## 2. Run a whole folder (batch)

This is the normal way to run. Pass a folder of PDFs as an argument, and the workflow processes every
PDF in it:

**macOS / Linux:**

```bash
.venv/bin/python3 run_pipeline.py input_files/reports/workflow_evaluation_sample
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\python run_pipeline.py input_files/reports/workflow_evaluation_sample
```

> **Running with no keys:** the shipped default is `claude`, which needs `ANTHROPIC_API_KEY`. For a
> key-free run, set `WORKFLOW_MODE = "rules-only"`. The sample folder also contains scanned PDFs
> (`ocr_*.pdf`); to process it without a Google Vision key, set `OCR_ENABLED = False` (otherwise those
> pages need `GOOGLE_VISION_API_KEY`).

It writes one result CSV per report (see [where results go](#4-where-results-go)). `BATCH_WORKERS` in
`config.py` controls how many reports run in parallel; the default is `4`, which shows a live progress
bar (on a terminal) while each report's detailed output goes to `logs/<report>.log`. Set it to `1` for a slower,
sequential run with full per-step output in the console. Every other `config.py` setting is explained
flag-by-flag in [../reference/config_options.md](../reference/config_options.md).

### Running on your own reports

1. Create a new folder under `input_files/reports/`, e.g. `input_files/reports/my_reports/`.
2. Put your PDF reports inside it.
3. Run the batch command above with your folder as the argument.

## 3. Run a single report

Useful for a quick test.

**macOS / Linux:**

```bash
.venv/bin/python3 run_pipeline.py input_files/reports/workflow_evaluation_sample/new_rep_1.pdf
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\python run_pipeline.py input_files/reports/workflow_evaluation_sample/new_rep_1.pdf
```

## 4. Where results go

Each report produces **one CSV**, the pottery summary, which is the workflow's single deliverable:

```
output_files/reports/<folder>/<report>.csv
```

`<folder>` mirrors the input folder name, and `<report>` matches the PDF's filename (so
`new_rep_1.pdf` becomes `new_rep_1.csv`). Batch runs also write a per-report log to
`output_files/reports/<folder>/logs/<report>.log`. The columns of the CSV are documented in
[../reference/output_schema.md](../reference/output_schema.md).

By default each CSV also carries seven **ABR standard-vocabulary** columns (`std_*`) that map every find
to the Dutch national standard (ABR/Archis), for interoperability with Archis. Toggle them with
`STANDARD_VOCAB_USE`; the standard is selected by `STANDARD_VOCAB_STYLE` (only `abr` implemented so far).
See [../reference/output_schema.md](../reference/output_schema.md).

## 5. Score the results against gold standards

If a folder has matching **gold standards** (hand-checked answers) under
`input_files/gold_standards/<folder>/`, you can measure how accurate the workflow was.

**macOS / Linux:**

```bash
.venv/bin/python3 evaluation/evaluate.py
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\python evaluation/evaluate.py
```

This reports detection precision/recall/F1, date accuracy, and site accuracy, per report and overall.
By default it scores `workflow_evaluation_sample`; pass `--folder <name>` to score a different batch
folder (it compares `output_files/reports/<folder>/` against `input_files/gold_standards/<folder>/`).
For the research details and the thesis numbers, see [../research/evaluation.md](../research/evaluation.md)
and [../research/results.md](../research/results.md).

## 6. Reproduce the thesis runs

The validation reports and their gold standards ship with the project. To reproduce one mode's run:

1. In `config.py`, set `WORKFLOW_MODE` to the mode you want.
2. Run the batch command from [§2](#2-run-a-whole-folder-batch) on `input_files/reports/workflow_evaluation_sample`.
3. Run the evaluation command from [§5](#5-score-the-results-against-gold-standards) to score it.

The exact outputs and scores reported in the thesis are also frozen under
[../research/datasets/](../research/datasets/) so you can compare. See
[../research/datasets/validation_set.md](../research/datasets/validation_set.md).

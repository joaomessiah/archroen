# How to run the workflow

This is the full guide to running the workflow. It covers choosing a mode, running one report or a
whole folder, where the results go, and how to score them against gold standards. If you just want a
quick first result, start with [quickstart.md](quickstart.md).

Run all commands from the project folder, in the terminal. If you're using an AI mode, your keys in
`.env` are loaded automatically (`config.py` reads `.env` on its own), so this preamble is **optional**.
Run it only if you want to load the keys into your terminal session yourself (see
[api_keys.md](api_keys.md)):

```bash
set -a && . ./.env && set +a
```

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

## 2. Run a whole folder (batch)

This is the normal way to run. The workflow processes **every PDF** in the folder named by
`DEFAULT_REPORTS_DIR` in `config.py`:

```bash
.venv/bin/python3 run_pipeline.py
```

It writes one result CSV per report (see [where results go](#4-where-results-go)). `BATCH_WORKERS` in
`config.py` controls how many reports run in parallel. The default is `2`; set it to `1` for slower
runs that show live per-report output. Every other `config.py` setting is explained flag-by-flag in
[../reference/config_options.md](../reference/config_options.md).

### Running on your own reports

1. Create a new folder under `input_files/reports/`, e.g. `input_files/reports/my_reports/`.
2. Put your PDF reports inside it.
3. Point the workflow at it in `config.py`:

   ```python
   DEFAULT_REPORTS_DIR = BASE_DIR / "input_files" / "reports" / "my_reports"
   ```

4. Run `.venv/bin/python3 run_pipeline.py`.

## 3. Run a single report

Useful for a quick test:

```bash
.venv/bin/python3 -c "from run_pipeline import main; from pathlib import Path; main(Path('input_files/reports/workflow_evaluation_sample/new_rep_1.pdf'))"
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
`input_files/gold_standards/<folder>/`, you can measure how accurate the workflow was:

```bash
.venv/bin/python3 evaluation/evaluate.py
```

This reports detection precision/recall/F1, date accuracy, and site accuracy, per report and overall.
By default it scores the folder set in `config.py`; pass `--folder <name>` to score a different batch
folder (it compares `output_files/reports/<folder>/` against `input_files/gold_standards/<folder>/`).
For the research details and the thesis numbers, see [../research/evaluation.md](../research/evaluation.md)
and [../research/results.md](../research/results.md).

## 6. Reproduce the thesis runs

The validation reports and their gold standards ship with the project. To reproduce one mode's run:

1. In `config.py`, set `WORKFLOW_MODE` to the mode you want and point `DEFAULT_REPORTS_DIR` at
   `input_files/reports/workflow_evaluation_sample`.
2. Run `.venv/bin/python3 run_pipeline.py`.
3. Run `.venv/bin/python3 evaluation/evaluate.py` to score it.

The exact outputs and scores reported in the thesis are also frozen under
[../research/datasets/](../research/datasets/) so you can compare. See
[../research/datasets/validation_set.md](../research/datasets/validation_set.md).

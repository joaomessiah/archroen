# 3 · Running It & Repo Layout

*Practical cheat-sheet: where things live and the exact commands.*

## Main folders (what's where)

```
Workflow/
├── config.py            ← all settings & toggles, incl. WORKFLOW_MODE  (the file you edit)
├── run_pipeline.py      ← the runner, processes every PDF in a folder
├── src/                 ← the workflow modules (Layers 1-7)
├── evaluation/          ← Layer 8 scoring harness (run separately)
├── tools/               ← pattern & dataset generators (one-off helpers)
├── data/
│   ├── patterns/        ← generated regex detection patterns (JSON)
│   └── vocabularies/    ← source pottery/period vocabularies (CSV) + reference maps
├── input_files/
│   ├── reports/<folder>/        ← drop the report PDFs here, grouped into a batch folder
│   └── gold_standards/<folder>/ ← hand-made gold CSV per report (for evaluation only)
├── output_files/reports/<folder>/ ← RESULTS land here, one <report>.csv per report
└── docs/                ← full documentation (overview, specs, research, reference)
```

The `<folder>` name ties everything together: `input_files/reports/my_batch/new_rep_1.pdf`
→ `output_files/reports/my_batch/new_rep_1.csv`.

## One-time setup

Requires **Python 3.12**.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

For the AI modes only: copy `.env.example` → `.env` and put the API key(s) in it
(`ANTHROPIC_API_KEY` for Claude mode, `LLM_API_KEY` for Llama mode). Rules-only needs no key.

## How to run on some PDF(s): the normal path

**The runner processes every PDF in one folder.** So to run on specific reports:

1. **Put the PDFs in a batch folder:** `input_files/reports/<your_folder>/`
2. **Point the workflow at it**, in `config.py`, set:
   ```python
   DEFAULT_REPORTS_DIR = BASE_DIR / "input_files" / "reports" / "<your_folder>"
   ```
3. **Pick the mode**, in `config.py`, set `WORKFLOW_MODE` to one of:
   `"rules-only"`, `"claude"`, or `"cloud-llama"` (Llama).
4. **Run it:**
   ```bash
   .venv/bin/python3 run_pipeline.py
   ```
5. **Read the results** in `output_files/reports/<your_folder>/`, one `<report>.csv` per PDF. By
   default each CSV also ends with the seven ABR `std_*` standard-vocabulary columns (interoperability).

That's the whole loop: drop PDFs → set folder + mode → run → read the CSVs.

### Notes
- **Just want to try it with no key/cost?** Set `WORKFLOW_MODE = "rules-only"` and run, that's the
  easiest first run.
- **Parallelism:** `BATCH_WORKERS` in `config.py` sets how many reports run at once
  (1 = sequential with live console output; >1 writes each report's log to
  `output_files/reports/<folder>/logs/`).
- One bad report can't kill the batch, failures are isolated and reported at the end.

## How to score against gold standards (research / Layer 8)

Only needed to reproduce the accuracy numbers, **not** to produce summaries:

```bash
.venv/bin/python3 evaluation/evaluate.py          # report-level scores
.venv/bin/python3 evaluation/evaluate_granular.py # per-field audit
```

This compares the outputs in `output_files/` against the gold standards in
`input_files/gold_standards/<folder>/`.

## Switching modes quickly

Everything is the one master switch in `config.py`:

| You want… | Set |
|---|---|
| No AI, free, deterministic | `WORKFLOW_MODE = "rules-only"` |
| Best accuracy (Claude) | `WORKFLOW_MODE = "claude"` (+ `ANTHROPIC_API_KEY` in `.env`) |
| Open-model comparison | `WORKFLOW_MODE = "cloud-llama"` (+ `LLM_API_KEY` in `.env`) |

No other code changes are needed, the rest of the workflow derives its behavior from this switch.

# Quickstart

This gets you a result in a few minutes, running on **one report** with **no API key** required. For
the full set of options (batches, AI modes, evaluation), see [how_to_run.md](how_to_run.md).

Before you start, make sure you've finished [installation.md](installation.md).

## 1. Use Rules-only mode (no key needed)

Open `config.py` in the project folder and set the mode to `rules-only`:

```python
WORKFLOW_MODE = "rules-only"
```

This runs the workflow with no AI, so you don't need any API key to try it.

The single-report run in step 2 reads `WORKFLOW_MODE` straight from `config.py`, so **save this change
before running step 2** (there's no command-line flag for the mode).

## 2. Run it on one report

In the terminal (from the project folder), run the workflow on a single report:

```bash
.venv/bin/python3 -c "from run_pipeline import main; from pathlib import Path; main(Path('input_files/reports/workflow_evaluation_sample/new_rep_1.pdf'))"
```

You'll see progress printed for each step (extracting text, detecting terms, assigning dates…). When
it finishes, it prints where it saved the result.

## 3. Open the result

The workflow writes **one CSV file**, a spreadsheet you can open in Excel, LibreOffice, or Google
Sheets:

```
output_files/reports/workflow_evaluation_sample/new_rep_1.csv
```

Each row is **one pottery find** the report mentioned, with columns for the pottery name, its typology,
how much was found, the find site, and the date range (`start_date` / `end_date`); by default it also
ends with seven ABR standard-vocabulary `std_*` columns (interoperability). The full list of columns is
in [../reference/output_schema.md](../reference/output_schema.md).

## What next?

- **Run on a whole folder of reports, or turn on the AI modes** → [how_to_run.md](how_to_run.md)
- **Understand what each step does** → [../workflow/architecture.md](../workflow/architecture.md)
- **See the thesis results** → [../research/results.md](../research/results.md)

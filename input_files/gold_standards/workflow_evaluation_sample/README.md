# Workflow evaluation sample: gold standards

This folder holds the **20 hand-checked gold standards** for the validation corpus: one `<report>.csv`
per report, listing the pottery finds a correct reading *should* produce. They are the reference the
workflow's output is scored against by `evaluation/evaluate.py`.

- **Matching reports:** `input_files/reports/workflow_evaluation_sample/` (same filename stem).
- **Full description:** see [`docs/research/datasets/validation_set.md`](../../../docs/research/datasets/validation_set.md).

## Columns

Each gold CSV has these columns: `Site_name`, `ID (temp)`, `Pot_name`, `Typology`, `Start_date`,
`End_date`, `Original_text`, `Page`, `Reference_File_Name`. The fields scored against the workflow
output are `Site_name`, `Pot_name`, `Typology`, `Start_date` and `End_date`.

## Scoring

Two harnesses score against these golds: report-level `evaluation/evaluate.py`, and per-field
(granular) `evaluation/evaluate_granular.py`.

> Note: the gold standards are intentionally conservative. See the limitations discussion in
> [`docs/research/limitations.md`](../../../docs/research/limitations.md).

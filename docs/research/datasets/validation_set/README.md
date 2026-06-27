# Validation set — frozen reports, outputs & scores

The **accuracy-measurement** corpus: 20 reports with hand-made gold standards, used to measure the
workflow's accuracy in the thesis. This folder keeps **frozen copies** of the source reports and the
per-mode results.

| Folder | What's inside |
|---|---|
| [input_reports/](input_reports/) | The 20 source report PDFs (`new_rep_*`, `old_rep_*`, `ocr_*`, `table_*`, five of each). |
| [outputs/](outputs/) | Each mode's pottery-summary CSVs (`claude/`, `llama/`, `rules_only/`). |
| [scores/](scores/) | Each mode's evaluation scores (`granular_detail.csv` + `granular_summary.csv`). |

The gold standards live under
[input_files/gold_standards/workflow_evaluation_sample/](../../../../input_files/gold_standards/workflow_evaluation_sample/).
For how the set is built, scored, and reproduced, see the [datasets overview](../README.md) and
[../validation_set.md](../validation_set.md).

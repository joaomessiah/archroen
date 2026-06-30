# Validation set (accuracy-measurement corpus)

The **20 reports** used to measure the workflow's accuracy, each with a hand-made **gold standard**.
Because the correct answers are known, this set is where the workflow's output is scored, and where the
three modes (Rules-only / Claude / Llama) are compared.

## Files

| Item | Location |
|---|---|
| Report PDFs (20, frozen snapshot) | [validation_set/input_reports/](validation_set/input_reports/) |
| Live report PDFs | [input_files/reports/workflow_evaluation_sample/](../../../input_files/reports/workflow_evaluation_sample/) |
| Gold standards (20) | [input_files/gold_standards/workflow_evaluation_sample/](../../../input_files/gold_standards/workflow_evaluation_sample/) |
| Outputs per mode (frozen) | [validation_set/outputs/](validation_set/outputs/): `claude/`, `llama/`, `rules_only/` |
| Scores per mode (frozen) | [claude granular_summary.csv](validation_set/scores/claude/granular_summary.csv) ([detail](validation_set/scores/claude/granular_detail.csv)) · [llama granular_summary.csv](validation_set/scores/llama/granular_summary.csv) ([detail](validation_set/scores/llama/granular_detail.csv)) · [rules_only granular_summary.csv](validation_set/scores/rules_only/granular_summary.csv) ([detail](validation_set/scores/rules_only/granular_detail.csv)) |
| Live output of a run | `output_files/reports/workflow_evaluation_sample/` (mirrors the shared input folder) |
| Live scores of a run | `output_files/evaluation/<output-folder-name>/` |
| ABR demonstration (frozen) | [validation_set/outputs/std_abr/](validation_set/outputs/std_abr/): the Claude output mapped to the **ABR** (Dutch national standard) through the `std_*` columns, so it can feed straight into Archis. A separate capability demonstration, not a scored mode. |

> **On the `_mode_<mode>` names.** The three modes share one input folder, so a pipeline run always
> writes to `output_files/reports/workflow_evaluation_sample/`. To keep the three runs side by side, each
> mode's output folder was renamed to `…_mode_<mode>` after its run, and the evaluation was then pointed
> at the renamed folder. That is why the frozen copies here carry the `_mode_<mode>` names.

The 20 reports span four source-type buckets, five each (`new_rep_1-5`, `old_rep_1-5`, `ocr_1-5`,
`table_1-5`): new reports and old reports (both running text/prose, modern and decades-old),
finds-tables, and OCR'd scans, so the workflow is tested across the formats real reports take.

## Gold standard format

Each gold standard is a hand-made CSV, one row per find a correct reading should yield, with these
columns:

| Column | Meaning |
|---|---|
| `Site_name` | The find's site |
| `ID (temp)` | A row number within the gold |
| `Pot_name` | The pottery name |
| `Typology` | The typology code, if any |
| `Start_date`, `End_date` | The find's date range (years; negative = BC) |
| `Original_text` | The verbatim text the find is drawn from |
| `Page` | The page it appears on |
| `Reference_File_Name` | The source report |

The Layer 8 harness pairs each gold row to a workflow row and scores them field-by-field. See
[../evaluation.md](../evaluation.md). The gold standards are intentionally conservative; see
[../limitations.md](../limitations.md).

## Results

The measured accuracy of each mode on this set is in [../results.md](../results.md).

## Reproducing

```python
# in config.py:
DEFAULT_REPORTS_DIR = BASE_DIR / "input_files" / "reports" / "workflow_evaluation_sample"
WORKFLOW_MODE = "claude"   # or "cloud-llama" (Llama mode) / "rules-only"
```

```bash
.venv/bin/python3 run_pipeline.py            # produce the summaries
.venv/bin/python3 evaluation/evaluate.py     # score them
```

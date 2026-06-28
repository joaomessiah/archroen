# Workflow evaluation sample: validation corpus (input PDFs)

This folder holds the **20 reports** used to *measure the workflow's accuracy* in the thesis. Each
report has a matching hand-checked gold standard, so the workflow's output can be scored against it.

- **These files:** the 20 source report PDFs.
- **Gold standards:** `input_files/gold_standards/workflow_evaluation_sample/`, one `<report>.csv` per PDF.
- **Results (generated):** a run writes to `output_files/reports/workflow_evaluation_sample/`; the thesis
  renamed each mode's output folder to `…_mode_<mode>` (`claude`, `llama`, `rules_only`) afterward to keep
  the three runs apart.
- **Scores:** `output_files/evaluation/<output-folder-name>/`.
- **Full description:** see [`docs/research/datasets/validation_set.md`](../../../docs/research/datasets/validation_set.md).

## Source-type buckets

The 20 reports split evenly into **four source-type buckets, five each**, named by filename stem:

| Stem | Source type |
|------|-------------|
| `new_rep_1` to `new_rep_5` | New reports |
| `old_rep_1` to `old_rep_5` | Old reports |
| `ocr_1` to `ocr_5` | OCR reports |
| `table_1` to `table_5` | Tables |

The chart tool infers each report's source type from the filename stem (it matches the
`new_rep` / `old_rep` / `ocr` / `table` prefix), so the by-source-type charts depend on these
names. **Renaming these files would break the source-type split.**

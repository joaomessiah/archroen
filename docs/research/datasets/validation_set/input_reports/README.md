# Validation reports (frozen source PDFs)

A **frozen copy of the source report PDFs** for the validation set: the 20 reports with hand-made
gold standards used to measure the workflow's accuracy. The file names encode the four source types:
`new_rep_*` (new reports), `old_rep_*` (old reports), `ocr_*` (OCR'd scans) and `table_*`
(finds-tables), five of each, the same ids used by the per-mode [../outputs/](../outputs/) and
[../scores/](../scores/).

These PDFs are the pipeline's input: Layers 1-2 extract and clean their text, and the rest of the
workflow turns each into a per-report pottery summary, which Layer 8 scores against its gold standard.
A live copy of the same PDFs lives under
[input_files/reports/workflow_evaluation_sample/](../../../../../input_files/reports/workflow_evaluation_sample/),
and the gold standards under
[input_files/gold_standards/workflow_evaluation_sample/](../../../../../input_files/gold_standards/workflow_evaluation_sample/).

For the full picture, see the [datasets overview](../../README.md) and
[../../validation_set.md](../../validation_set.md).

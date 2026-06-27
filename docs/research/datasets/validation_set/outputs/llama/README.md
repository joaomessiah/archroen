# Llama mode — validation outputs (frozen)

The **Llama mode** pottery-summary output for each of the 20 validation reports — one CSV per
report. File names encode the source type: `new_rep_*` (new reports), `old_rep_*` (old reports),
`ocr_*` (OCR'd scans) and `table_*` (finds-tables), five of each.

Columns are defined in
[../../../../../reference/output_schema.md](../../../../../reference/output_schema.md). This is a frozen
snapshot; the matching scores are in [../../scores/llama/](../../scores/llama/). To reproduce, see
the [datasets overview](../../../README.md).

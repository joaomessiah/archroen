# Validation outputs (frozen, per mode)

The workflow's output on the 20-report validation set, kept **once per mode** so the three can be
compared:

- [claude/](claude/): Claude mode
- [llama/](llama/): Llama mode
- [rules_only/](rules_only/): Rules-only mode

Each subfolder has one pottery-summary CSV per report. The file names encode the four source types:
`new_rep_*` (new reports), `old_rep_*` (old reports), `ocr_*` (OCR'd scans) and `table_*`
(finds-tables), five of each. Column meanings are in
[../../../../reference/output_schema.md](../../../../reference/output_schema.md); these outputs are what
the [scores/](../scores/) are computed from.

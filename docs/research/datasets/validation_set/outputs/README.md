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

A fourth folder, [std_abr/](std_abr/), is a **separate capability demonstration**, not a scored mode.
It is the same Claude output with the seven **ABR standard-vocabulary** (`std_*`) columns added, which
map every find to the Dutch national standard (Archeologisch Basisregister / Archis) so the results are
directly reusable in the national heritage data ecosystem without manual re-coding. The mapping is
deterministic and standard-agnostic by design (the target is chosen by `STANDARD_VOCAB_STYLE`; only
`abr` is implemented so far). It sits outside the scored evaluation, but spot-checks confirm the codes resolve correctly.

# Validation scores (frozen, per mode)

The **evaluation scores** for each mode on the 20-report validation set — the numbers behind
[../../../results.md](../../../results.md) and the [charts](../../../charts/).

- [claude/](claude/) · [llama/](llama/) · [rules_only/](rules_only/)

Each subfolder holds two files from the granular evaluation harness: `granular_summary.csv`
(per-report verdict counts for every field) and `granular_detail.csv` (the field-by-field audit).
They are produced by `evaluation/evaluate_granular.py` — see [../../../evaluation.md](../../../evaluation.md).

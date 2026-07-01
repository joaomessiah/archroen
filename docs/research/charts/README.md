# Evaluation charts

The evaluation figures, the frozen copies referenced in
[../results.md](../results.md). They compare the three workflow modes (Rules-only, Claude, Llama)
on the 20-report validation set. Headline overall correctness: Claude 95.6%, Llama 77.3%,
Rules-only 47.9%.

| File | Shows |
|---|---|
| `1_overall_correctness_by_mode_grayscale.png` | Overall correctness, Rules-only vs Claude vs Llama. |
| `2_performance_by_source_type_claude_grayscale.png` | Claude: four verdicts per source type. |
| `3_performance_by_source_type_llama_grayscale.png` | Llama: four verdicts per source type. |
| `4_correctness_by_source_type_claude_vs_llama_grayscale.png` | Correct share per source type, Claude vs Llama. |
| `5_performance_by_field_claude_grayscale.png` | Claude: four verdicts per field. |
| `6_performance_by_field_llama_grayscale.png` | Llama: four verdicts per field. |
| `7_per_report_correctness_distribution_grayscale.png` | Per-report correctness spread, Claude vs Llama. |

**These are generated**, not edited by hand. They are produced by
[`tools/scientific_report/generate_charts/`](../../../tools/scientific_report/generate_charts/) from
the frozen scores in [../datasets/validation_set/scores/](../datasets/validation_set/scores/). See
that tool's README for how to (re)run it, and its
[discussion.md](../../../tools/scientific_report/generate_charts/discussion.md) for what each chart means.

**Regenerate:**

```bash
.venv/bin/python3 tools/scientific_report/generate_charts/generate_charts.py \
  --claude     output_files/evaluation/workflow_evaluation_sample_mode_claude/granular_summary.csv \
  --llama      output_files/evaluation/workflow_evaluation_sample_mode_llama/granular_summary.csv \
  --rules_only output_files/evaluation/workflow_evaluation_sample_mode_rules_only/granular_summary.csv
```

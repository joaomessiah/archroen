# Layer 8: Evaluation

**Modules:** `evaluation/evaluate.py` (report-level scoring), `evaluation/evaluate_granular.py`
(per-field auditing)

> **This layer is a standalone harness; it is *not* part of `run_pipeline.py`.** It is the research
> tool that measures how good the workflow's output is, by comparing and scoring it against a manually
> constructed gold standard. For the research write-up and the actual numbers, see
> [../../research/evaluation.md](../../research/evaluation.md) and
> [../../research/results.md](../../research/results.md).

## Purpose

Measure whether the workflow produces useful, accurate, chronologically meaningful output, in a way
explicit enough to be defensible as thesis methodology.

## Inputs

- **Workflow output:** the per-report pottery summaries (`output_files/reports/<folder>/<report>.csv`).
- **Gold standard:** `input_files/gold_standards/<folder>/<report>.csv`, a hand-made CSV of the finds
  a report *should* yield, one row per find, mirroring the reports folder.

## Matching policy (itself part of the methodology)

Each gold find is paired one-to-one with a workflow row, in **priority order**. The order is stated
explicitly so the scoring is defensible:

1. **Typology code** (exact, after normalization).
2. **Exact / catalog-number name.**
3. **Ware family**, granularity- and synonym-aware, because golds mix granularity and language (gold
   "Amphorae" vs workflow "Baetican olive oil amphora / Dressel 20"; gold "Belgian ware" vs workflow
   "terra rubra"/"terra nigra"). Family matches are credited as found.
4. **Alias-normalized token overlap** (Dutch→English) as a last resort.

## `evaluate.py`: report-level scores

Scores every output against its gold standard and prints, per report and in aggregate:

- **Detection:** precision / recall / F1 (matched / missed / spurious finds).
- **Per-field agreement** over matched pairs: site, pottery name, typology, start, end.
- **Dates:** both *exact-endpoint* and *overlaps-gold* accuracy (two metrics).

```bash
.venv/bin/python3 evaluation/evaluate.py                 # console report, all reports
.venv/bin/python3 evaluation/evaluate.py --csv eval.csv  # also dump per-find matched/missed/spurious rows
.venv/bin/python3 evaluation/evaluate.py --report table_5 # restrict to one report
```

## `evaluate_granular.py`: per-field audit

A finer-grained companion that classifies **each field of each finding** and shows the gold value next
to the workflow value, so results can be audited field-by-field. Each field gets a verdict:

| Verdict | Meaning |
|---|---|
| `exact` | Gold and workflow values identical (after normalization); two blanks also count as exact agreement |
| `acceptable` | Not identical but archaeologically tolerable: ware family / token overlap; site-name containment; or a date endpoint within tolerance, but **only** when the gold find has no typology. If it has one, the date must be exact, the typology being authoritative |
| `incorrect` | The pair is matched but this field disagrees (both present and different, or exactly one side blank) |

`missing` and `overclaim` are **record-level** verdicts (an unmatched gold find, or an unmatched
workflow row); they never arise inside a matched pair.

## Outputs

The granular harness writes `granular_summary.csv` (the headline per-field numbers) and
`granular_detail.csv` (every field's gold-vs-workflow verdict) into `output_files/evaluation/<stem>/`,
where `<stem>` is the name of the scored output set (e.g. `workflow_evaluation_sample_mode_claude`).

## Notes

The gold standards are intentionally conservative. See
[../../research/limitations.md](../../research/limitations.md) for what that means for interpreting the
recall and precision figures.

The trailing ABR `std_*` standard-vocabulary columns are an interoperability layer and are **not
scored** by this harness: no precision, recall, or accuracy is computed for them, and they do not
enter any reported figure.

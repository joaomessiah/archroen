# Evaluation

How the workflow's output is scored against the gold standards. This is the research-facing companion
to the [Layer 8 spec](../workflow/specs/layer_8.md); for the numbers it produces, see
[results.md](results.md).

## The two harnesses

| Script | What it produces |
|---|---|
| `evaluation/evaluate.py` | Report-level **detection** scores: precision / recall / F1, plus per-field agreement and date accuracy, printed to the console. |
| `evaluation/evaluate_granular.py` | A **per-field audit**: every field of every finding classified, written to `granular_summary.csv` (headline counts) and `granular_detail.csv` (gold-vs-workflow, row by row). |

The frozen `granular_summary.csv` / `granular_detail.csv` for each mode are under
[datasets/validation_set/scores/](datasets/validation_set/scores/).

## Matching (one-to-one)

Each gold find is paired to at most one workflow row, in priority order: **typology code** → **exact /
catalog-number name** → **ware family** (granularity- and synonym-aware) → **alias-normalized token
overlap**. The token-overlap step accepts a pair at a Jaccard overlap of **0.34** or above (or when one
token set is wholly contained in the other). Unpaired findings become `missing` (gold-only) or
`overclaim` (workflow-only).


## Field verdicts

For each matched pair, every field gets one verdict:

| Verdict | Meaning |
|---|---|
| `exact` | Identical after normalization (two blanks count as exact agreement). |
| `acceptable` | Not identical but archaeologically tolerable: ware-family/token overlap for pottery; site-name token containment; a date endpoint within tolerance **only** when the gold find has no typology (with a typology, the date must be exact). |
| `incorrect` | Matched pair, but this field disagrees (both present and different, or one side blank). |

**Typology is the exception:** it is scored exact-or-incorrect only (it never receives an `acceptable`
verdict); a typology code either matches exactly or it counts as incorrect.

`missing` and `overclaim` are record-level (a whole finding unmatched on one side).

## The headline metric used in [results.md](results.md)

**Field-level correctness** = (`exact` + `acceptable`) ÷ all field verdicts, computed over the union of
gold and workflow findings. Unmatched findings therefore count against the score through their `missing` /
`overclaim` field slots. The metric is reported both overall and per field (site, pottery, typology, start
date, end date). Five fields are scored per finding. This headline metric uses the `exact` + `acceptable`
verdicts; it is **not** the date-overlap metric described below, which is a separate diagnostic.

The output's ABR `std_*` standard-vocabulary columns are an interoperability layer and are not part of
this scoring.


## Date accuracy

Dates are scored two ways: **exact-endpoint** agreement and **overlap with the gold range**. The overlap
measure is included because a range that partially overlaps the truth is still archaeologically useful. The
granular audit treats a within-tolerance endpoint as `acceptable` only when the gold find carries no
typology.

## Running it

```bash
.venv/bin/python3 evaluation/evaluate.py                 # detection + agreement, console
.venv/bin/python3 evaluation/evaluate_granular.py        # per-field audit → output_files/evaluation/<stem>/
```

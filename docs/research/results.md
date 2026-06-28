# Results

The measured accuracy of the workflow on the **validation set** (20 reports, scored against hand-made
gold standards), for each of the three modes. The numbers below are computed from the frozen per-field
audits in [datasets/validation_set/scores/](datasets/validation_set/scores/).

**Metric:** *field-level correctness* = (`exact` + `acceptable`) ÷ all field verdicts, over the union of
gold and workflow findings, scored across five fields per finding (site, pottery, typology, start date,
end date). See [evaluation.md](evaluation.md) for the definitions.

## Overall

| Mode | Correct | Incorrect | Missing | Overclaim | Total fields | **Field-level correctness** |
|---|---:|---:|---:|---:|---:|---:|
| **Claude mode** | 1161 | 29 | 15 | 10 | 1215 | **95.6%** |
| **Llama mode** (cloud Llama-3.3-70B) | 962 | 58 | 185 | 40 | 1245 | **77.3%** |
| **Rules-only mode** | 803 | 317 | 85 | 470 | 1675 | **47.9%** |

*Claude strongest, Llama mid, Rules-only the deterministic baseline.*

The Claude figure is stable across repeated runs (within 0.6 percentage points over five identical
runs); see [claude_variance/](claude_variance/).

**Claude mode is clearly the strongest**, Llama mode is a solid mid-point, and Rules-only is the
deterministic baseline. The AI modes' main advantage is on the context-dependent judgements that rules
alone can't make.

## Per field

Field-level correctness (exact + acceptable) by field:

| Field | Claude | Llama | Rules-only |
|---|---:|---:|---:|
| Site name | 95.9% | 75.1% | 3.3% |
| Pottery name | 97.9% | 81.9% | 66.9% |
| Typology | 97.9% | 77.5% | 64.5% |
| Start date | 93.8% | 76.3% | 54.9% |
| End date | 92.2% | 75.5% | 50.1% |

## What the numbers show

- **Site resolution is where Rules-only collapses** (3.3%). Without an AI step the site name is wrong on
  almost every find, because the deterministic site normalization alone cannot pick the right place from
  messy, multi-site report text. Both AI modes recover this (Claude 95.9%).
- **Rules-only massively over-claims** (470 overclaim field-slots, vs 10 for Claude). With no AI presence
  filtering, deduplication, or consolidation, it emits many findings the gold does not contain, which
  inflates the find list. This is the single biggest driver of its low overall score.
- **Llama mode's main gap is recall** (185 missing field-slots): it omits more genuine findings than
  Claude does, while keeping over-claiming modest (40 overclaim field-slots) - so its weakness is recall,
  not precision.
- **Typology and pottery name are the strongest fields**, even for Rules-only, because they rest on the
  deterministic vocabulary/typology tables. Dates, and especially site names, benefit most from the AI.

## Reproducing these numbers

The inputs, gold standards, and frozen outputs are all in the repository. To regenerate a mode's scores,
run the workflow in that mode on the validation set and then the evaluation harness. See
[datasets/validation_set.md](datasets/validation_set.md). The frozen
[scores/](datasets/validation_set/scores/) let you compare a fresh run against these figures.

> These figures should be read together with [limitations.md](limitations.md): the gold standards are
> deliberately conservative, so the AI modes' recall is, if anything, understated.

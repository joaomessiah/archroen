# Research methodology

This page explains *how the workflow was validated* for the thesis: what was measured, against what, and
why the approach is defensible. The actual numbers are in [results.md](results.md); the scoring
mechanics are in [evaluation.md](evaluation.md).

## The research question

Can an automated workflow read archaeological excavation reports and produce an accurate, usable table
of dated pottery finds, and how much does using an AI model help, compared with rules alone?

## Two corpora, two purposes

The thesis uses two distinct sets of reports (see [datasets/](datasets/)):

- **The validation set** (20 reports, with hand-made gold standards), used to **measure accuracy**.
- **The Roman-villa set** (30 reports, no gold standards): the **real-world application**, running the
  workflow on the actual reports the thesis is about.

Keeping them separate matters: accuracy is measured on the set with ground truth, while the villa set
demonstrates the workflow doing the job it was built for.

## Comparing modes

To isolate the contribution of the AI model, the workflow was run on the validation set in three
"pure" [modes](../design/workflow_modes.md): **Rules-only mode**, **Claude mode**, and **Llama mode**.
No mixing was allowed within a run, so each result is attributable to exactly one approach:

- **Rules-only** is the deterministic baseline (what rules alone achieve).
- **Claude** and **Llama** show what frontier and open cloud models add on top.

Each mode is selected by `WORKFLOW_MODE` in `config.py`, whose literal values are `claude`,
`cloud-llama`, and `rules-only`.

## How accuracy is measured

Each workflow output is scored against its gold standard by the **Layer 8** harness
([../workflow/specs/layer_8.md](../workflow/specs/layer_8.md)), implemented in `evaluation/evaluate.py`
(report-level detection scores) and `evaluation/evaluate_granular.py` (the per-field audit). The
methodology is deliberately explicit so it is defensible:

1. **One-to-one matching.** Each gold find is paired to at most one workflow row, in a stated priority
   order (typology code → exact/catalogue name → ware family → alias-normalised token overlap). The
   last-resort token-overlap step accepts a pair when the Jaccard overlap of their tokens is at least
   **0.34** (or one token set is contained in the other). The ware-family step credits answers that are
   archaeologically equivalent even when they differ in granularity or language (e.g. gold "Amphorae" ↔
   workflow "Dressel 20").
2. **Field-by-field verdicts.** For each matched pair, every field (site, pottery, typology, start
   date, end date) is judged `exact`, `acceptable`, or `incorrect`. Findings with no match are recorded
   as `missing` (in the gold but not produced) or `overclaim` (produced but not in the gold).
3. **Two date metrics.** Dates are scored both as exact-endpoint agreement and as overlap with the
   gold range, since a partially-overlapping date range is still archaeologically informative.

This produces both **detection** quality (did it find the right finds?) and **per-field accuracy** (are
the details of each find correct?).

## Why this is defensible

- The **matching rules are stated, not hidden**: anyone can see why two finds were considered the same.
- **"Acceptable" is defined narrowly**: a date is tolerated within a margin only when the gold find has
  no typology. If it has a typology, the date must be exact, because the typology is authoritative.
- The **same gold standards score every mode**: where a find is open to interpretation (see
  [limitations.md](limitations.md)), that call affects all three modes equally, so the comparison
  between them is fair.
- The **test set spans the formats real reports take**: the 20 validation reports are drawn evenly
  from four source types (prose, finds-tables, and OCR'd scans), so the figures reflect performance
  across formats, not just the easy ones.
- Every run is **reproducible from the shipped inputs**: the reports and gold standards are in the
  repository, and the exact outputs scored are frozen under [datasets/](datasets/).

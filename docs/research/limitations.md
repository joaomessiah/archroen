# Limitations and reproducibility

How to read the results honestly, and what the workflow does and doesn't guarantee.

## The gold standards are deliberately conservative

The hand-made gold standards aim for *high-confidence* finds — they are intentionally not exhaustive.
The consequence for the numbers in [results.md](results.md):

- A workflow finding that is **not** in the gold is counted as an `overclaim`, but some of those are
  genuinely in the report and simply weren't recorded in the conservative gold.
- So reported **recall is a floor, not a ceiling** — the AI modes' true recall is, if anything,
  understated. This is why the discussion leads with recall rather than treating every overclaim as a
  true error.

## AI steps are not fully deterministic

In Claude mode and Llama mode the AI-assisted steps run at low temperature but can still vary slightly
run-to-run, so exact numbers may shift on re-run. **Rules-only mode is fully deterministic** — use it
when you need byte-for-byte reproducibility. The rule-based backbone (detection, normalization,
typology/period date tables, site normalization) is deterministic in every mode.

## Coverage is bounded by the vocabularies

Regex detection only catches typologies present in `data/vocabularies/`. Trigger-based extraction and the
AI steps widen this, but **full recall is not guaranteed** — a pottery type absent from the vocabulary
and not caught by a trigger or the AI can be missed. See
[../reference/data_files.md](../reference/data_files.md) for how to extend the vocabulary.

## OCR introduces noise

Scanned/image-only reports are read by OCR, which can mis-read characters. Cleaning (Layer 2) repairs
common artefacts, but OCR errors can still propagate into detection and dates.

## Site over-merging is possible

The deterministic site normalization can, in a multi-site report where two distinct sites share only a
city name, merge them into one. It is correct for single-site reports (the common case) and errs toward
merging; distinctive sub-names keep genuinely different sites apart. See
[../design/design_notes.md](../design/design_notes.md#6-deterministic-site-resolution).

## Sample size

Accuracy is measured on **20 reports**. They were chosen to span formats (prose, finds-tables, OCR'd
scans), but it is a modest sample — the figures are indicative of the workflow's behaviour on
South-Limburg Roman-period grey literature, not a guarantee across all archaeological reporting.

## Scope

The workflow targets the **Roman period** and filters out clearly non-Roman finds
(`POTTERY_ROMAN_ONLY`). It is not designed to summarise finds from other periods.

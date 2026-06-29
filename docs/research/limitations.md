# Limitations and reproducibility

How to read the results honestly, and what the workflow does and doesn't guarantee.

## Some finds are open to interpretation

Identifying finds in grey-literature prose involves judgment: whether a sentence reports an actual
find or only refers to one, or whether a mention repeats a find already counted, is sometimes open to
interpretation. The gold standards reflect careful, consistent decisions on these cases, but a
different annotator might draw a few borderline calls differently, which would shift the exact numbers
slightly. The figures should be read as accurate to within that small margin of judgment, not as exact
to the last find.

## AI steps are near-deterministic

In Claude mode and Llama mode the AI-assisted steps are near-deterministic: they are not bit-for-bit
reproducible, so exact numbers can shift slightly on re-run, but the drift is tiny. For Claude mode it
was measured directly: across five identical runs, field-level correctness stayed within 0.6 percentage
points, so a single run is representative (see [claude_variance/](claude_variance/)). The reported
AI-mode figures come from one run per mode. **Rules-only mode is fully deterministic**; use it when you need byte-for-byte
reproducibility. The rule-based backbone (detection, normalization, typology/period date tables, site
normalization) is deterministic in every mode.

## The application set is unscored

Accuracy is measured only on the validation set. The **Roman-villa application set has no gold
standards**, so its outputs are unscored: there is no per-finding accuracy figure for that corpus, only
the produced summaries.

## Coverage is bounded by the vocabularies

The rule-based detection is bounded by `data/vocabularies/`, but in Claude mode this is only a floor:
the model reads the full report and extracts finds the vocabulary never lists, so coverage is far
wider. Full recall is still not guaranteed (a type that neither the vocabulary, a trigger, nor the
model surfaces can be missed), but that is a residual limit, not the main behaviour. See
[../reference/data_files.md](../reference/data_files.md) for how to extend the vocabulary.

## OCR introduces noise

Scanned/image-only reports are read by OCR, which can mis-read characters. Cleaning (Layer 2) repairs
common artefacts, and the validation set includes OCR'd reports on which the workflow still scores
well, so this is largely handled in practice.

## Site over-merging is possible

Site normalization is reliable in the common case: single-site reports, and multi-site reports whose
sites carry distinctive sub-names. The narrow exception is a report with two genuinely different sites
that share only a city name and nothing more specific, where the normalization can merge them into one.
This case is uncommon, and distinctive sub-names keep different sites apart. See
[../design/design_notes.md](../design/design_notes.md#6-deterministic-site-resolution).

## Scope

In its current state, the workflow targets the **Roman period** and filters out clearly non-Roman finds
(`POTTERY_ROMAN_ONLY`).

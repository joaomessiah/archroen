# Roman-villa reports (frozen source PDFs)

A **frozen copy of the source report PDFs** for the Roman-villa application set — the South-Limburg
excavation and literature reports the workflow was run on. One PDF per report, named by its report id
(e.g. `12703.pdf`), the same ids used by the [outputs/](../outputs/) pottery summaries.

These PDFs are the pipeline's input: Layers 1–2 extract and clean their text, and the rest of the
workflow turns each into the per-report pottery summary in [../outputs/](../outputs/). A live copy of
the same PDFs lives under `input_files/reports/south_limburg_villas/`.

This set has **no gold standards** — it is the real-world application, not the accuracy measurement
(for that, see the [validation set](../../validation_set/)). For the full picture, see the
[datasets overview](../../README.md) and [../../roman_villas.md](../../roman_villas.md).

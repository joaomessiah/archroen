# Research

The thesis evidence: how the workflow was evaluated, on what data, what it scored, and how to read
those numbers honestly.

**Headline result (overall field-level correctness):** Claude 95.6%, Llama 77.3%, Rules-only 47.9%.

The two corpora are the **validation set** (20 reports, scored against gold standards) and the
**Roman-villa set** (30 reports, the real-world application).

| File | What it covers |
|---|---|
| [methodology.md](methodology.md) | The two corpora (application vs. accuracy-measurement) and how accuracy is measured. |
| [evaluation.md](evaluation.md) | The scoring definitions: the verdicts (exact / acceptable / incorrect / missing / overclaim) and field-level correctness. |
| [results.md](results.md) | The measured accuracy of each mode (Rules-only / Claude / Llama), overall and per field. |
| [limitations.md](limitations.md) | How to read the results honestly: what the figures do and don't guarantee. |

| Folder | What's inside |
|---|---|
| [charts/](charts/) | The seven evaluation figures used in the thesis (PNGs). |
| [maps/](maps/) | The Roman-villa location maps (PNGs). |
| [datasets/](datasets/) | The two corpora, with frozen copies of their outputs and scores. |
| [claude_variance/](claude_variance/) | Stability check: how much the Claude result drifts across 5 identical runs (near-deterministic). |

The charts and maps are produced by the tools under
[`tools/scientific_report/`](../../tools/scientific_report/).

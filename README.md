# ARCHROEN - Archaeology Chronology Workflow

**ARCHROEN** reads archaeological excavation reports (PDFs) and turns the pottery they describe into
structured, comparable data. For each report it produces a single tidy table — the **pottery
summary** — with one row per Roman-period pottery find the report mentions: the find's name, typology,
date range, and site, plus the exact sentence it was drawn from.

## Documentation

Everything is in **[docs/](docs/)**. Pick by what you want to do:

| I want to… | Go to |
|---|---|
| **Run it on my own reports** | [Getting started](docs/getting_started/) — from installing Python to your first run |
| **Understand how it works** | [Workflow](docs/workflow/) — the eight steps in plain language, plus a diagram |
| **See the research & results** | [Research](docs/research/) — methodology, datasets, evaluation, and the accuracy results |
| **Look something up** | [Reference](docs/reference/) — output columns, data files, glossary |
| **Know why it's built this way** | [Design](docs/design/) — the rationale and the AI/rules "modes" |

## How it works (in short)

The workflow runs as a chain of **layers**, each doing one job and passing its result to the next:

| Step | What it does |
|---|---|
| 1 · Extraction | Reads the text out of the PDF, page by page (OCR for scans). |
| 2 · Cleaning | Tidies the text and splits it into manageable sections. |
| 3 · Detection | Spots mentions of pottery, periods, and centuries. |
| 4 · Normalization | Maps each mention to one standard name. |
| 5 · Context | Decides if a find is really *present*, *absent*, a *comparison*, or *uncertain*. |
| 6 · Dating | Gives each find a date range, preferring the typology tables over guesses. |
| 7 · Summary | Removes duplicates, merges repeats, and builds the final per-report table. |
| 8 · Evaluation | *(Research only)* Scores the results against hand-checked answers. |

By default an AI model reads the whole report while the rules ground and check it; it can also run
with **no AI at all** (Rules-only). Steps 1–7 produce the summary; step 8 is a separate research tool.
Full detail: [architecture](docs/workflow/architecture.md) and the [layer specs](docs/workflow/specs/).

## Getting started

The full, step-by-step guide is in **[Getting started](docs/getting_started/)**:

1. [Prerequisites](docs/getting_started/prerequisites.md) — what you need first
2. [Installation](docs/getting_started/installation.md) — set it up
3. [Quick start](docs/getting_started/quickstart.md) — run your first report
4. [How to run](docs/getting_started/how_to_run.md) — batches, modes, and scoring

**Easiest first run:** no API key, no AI — set `WORKFLOW_MODE = "rules-only"` in [config.py](config.py)
and run the workflow. The AI modes (more accurate) are explained in
[workflow modes](docs/design/workflow_modes.md).

## Repository layout

```
.
├── src/                   # the workflow itself — one module per processing layer
├── tools/                 # offline maintenance scripts
│   └── scientific_report/ # python scripts that produce the charts and maps
├── data/                  # the controlled archaeological domain knowledge
│   ├── vocabularies/      # editable source of truth: typology, period/emperor, chronology data
│   └── patterns/          # detection regexes generated from the vocabularies (never hand-edited)
├── docs/                  # all project documentation
│   ├── getting_started/   # how to install, configure and run the workflow
│   ├── workflow/          # how the workflow works (overview and architecture)
│   │   └── specs/         # the per-layer, as-built specifications
│   ├── design/            # why it is built this way (design rationale and the three modes)
│   ├── reference/         # lookup material: output schema, data-file reference, glossary
│   └── research/          # study write-ups (methodology, evaluation, results, limitations)
│       ├── datasets/      # the corpora used, with their per-report outputs and scores
│       ├── maps/          # the map figures used in the study
│       └── charts/        # the chart figures used in the study
├── evaluation/            # evaluates the workflow output against the gold standards
├── input_files/           # everything fed into the workflow
│   ├── reports/           # the source report PDFs, grouped into batch folders
│   └── gold_standards/    # mirrored manual gold standards, one folder per batch
└── output_files/          # everything the workflow produces
    ├── reports/           # the per-report pottery-summary CSVs (the deliverable)
    └── evaluation/        # results of the evaluation scripts
```

## License

Code is released under the [MIT License](LICENSE). Note that the excavation report PDFs and the
pottery vocabularies may carry separate third-party terms.

# ARCHROEN

> **Archaeological Chronology Extraction and Normalization**: *a workflow for Roman pottery chronology.*

**ARCHROEN** reads excavation reports (PDFs) and turns the pottery finds they describe into
structured, comparable data. It is built for processing messy real-world grey literature in Dutch and
English, and is extensible to other languages. The reports may be modern or decades-old, born-digital
or scanned, with finds buried in prose, tables, and figure captions.

For each report ARCHROEN produces a single tidy table, the **pottery summary**, with one row per
Roman-period pottery find: the find's name, typology, date range, and site, plus the exact sentence
it was drawn from.

In evaluation against hand-made gold standards, its best mode (Claude) is **95.6% correct overall**
(see [Research](docs/research/)).

![Bar chart of overall correctness by mode: Rules-only 47.9%, Claude 95.6%, Llama 77.3%](docs/research/charts/1_overall_correctness_by_mode_grayscale.png)

*Overall field-level correctness on the 20 validation reports, one bar per run mode.*

## From report to structured data

ARCHROEN turns each pottery find into one structured, dated row. Here, one find from an OCR'd report
on Heerlen (the original is Dutch):

> "Uit kuil 12 kwam een randfragment van een versierde terra sigillata kom van het type **Dragendorff 37**, met een eierlijst en een fries van jachttaferelen."
>
> *(English: "From pit 12, a rim fragment of a decorated terra sigillata bowl of type Dragendorff 37, with an ovolo and a frieze of hunting scenes.")*

becomes **one row** of the pottery summary. The row has many columns, so it is split into two parts
here (it is still a single row):

| Site | Pottery | Typology | Start | End |
|---|---|---|---:|---:|
| Heerlen | Terra sigillata decorated bowl | Dragendorff 37 | 70 | 300 |

The same row also carries the Dutch national **ABR** standard-vocabulary columns (shown here one
column per row to keep it readable, still part of the same row):

| ABR column | Value |
|---|---|
| `std_vocabulary` | `ABR` |
| `std_ware_code` | `TS` |
| `std_ware_label` | `terra sigillata` |
| `std_form_code` | `KOM.KOM` |
| `std_form_label` | `kom` |
| `std_combined_code` | `TSKOM.DR37` |
| `std_combined_label` | `Terra sigillata kom - Dragendorff 37` |

The Dutch *versierde terra sigillata kom* and the form code `Dragendorff 37` are normalized to a
standard English pottery name and typology, and the date range comes from that typology; the ABR
columns map the find to the Dutch national standard. Each row further records the find context, a
confidence level, and the verbatim source text. The full column schema is in
[output_schema.md](docs/reference/output_schema.md).

## How it works

The workflow runs as a chain of **layers**, each doing one job and passing its result to the next:

| Layer | What it does |
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
with **no AI at all** (Rules-only). Layers 1-7 produce the summary; Layer 8 is a separate research tool.
Full detail: the [run modes](docs/design/workflow_modes.md), [architecture](docs/workflow/architecture.md), and the [layer specs](docs/workflow/specs/).

## Getting started

The full, step-by-step guide is in **[Getting started](docs/getting_started/)**:

1. [Prerequisites](docs/getting_started/prerequisites.md): what you need first
2. [Installation](docs/getting_started/installation.md): set it up
3. [Quick start](docs/getting_started/quickstart.md): run your first report
4. [How to run](docs/getting_started/how_to_run.md): batches, modes, and scoring

## Find what you need

Everything is in **[docs/](docs/)**. Pick by what you want to do:

| I want to… | Go to |
|---|---|
| **Run it on my own reports** | [Install and run it](docs/getting_started/): from installing Python to your first run |
| **See the full workflow** | [Workflow](docs/workflow/): architecture and the per-layer specs |
| **See the research & results** | [Research](docs/research/): methodology, datasets, evaluation, and the accuracy results |
| **Look something up** | [Reference](docs/reference/): output columns, data files, glossary |
| **Know why it's built this way** | [Design](docs/design/): the rationale and the AI/rules "modes" |

## Repository layout

```
.
├── src/                   # the workflow itself, one module per processing layer
├── tools/                 # offline maintenance scripts
│   └── scientific_report/ # python scripts that produce the charts and maps
├── data/                  # the controlled archaeological domain knowledge
│   ├── vocabularies/      # editable source of truth: typology, period/emperor, chronology data
│   └── patterns/          # detection regexes generated from the vocabularies (never hand-edited)
├── docs/                  # all project documentation
│   ├── getting_started/   # how to install, configure and run the workflow
│   ├── workflow/          # how the workflow works (overview and architecture)
│   │   └── specs/         # the per-layer, as-built specifications
│   ├── design/            # why it is built this way (design rationale and the modes)
│   ├── reference/         # lookup material: output schema, data-file reference, glossary
│   └── research/          # study write-ups (methodology, evaluation, results, limitations)
│       ├── datasets/      # the corpora used, with their per-report outputs and scores
│       ├── maps/          # the map figures used in the study
│       ├── charts/        # the chart figures used in the study
│       ├── claude_variance/       # stability check on the Claude result across repeated runs
│       └── aoristic_monte_carlo/  # case study: aoristic and Monte Carlo temporal analysis of the villa ceramics
├── evaluation/            # evaluates the workflow output against the gold standards
├── input_files/           # everything fed into the workflow
│   ├── reports/           # the source report PDFs, grouped into batch folders
│   └── gold_standards/    # mirrored manual gold standards, one folder per batch
└── output_files/          # everything the workflow produces
    ├── reports/           # the per-report pottery-summary CSVs (the deliverable)
    └── evaluation/        # results of the evaluation scripts
```

## Citation

If you use ARCHROEN in your work, please cite the associated master's thesis:

> Sousa da Silva, J. M. (2026). *Developing a Reproducible Workflow for AI-Assisted Chronological Data Extraction: A Case Study from Roman Villas in South Limburg* [Master's thesis, University of Amsterdam].

<!-- When the thesis is deposited, add its URL/DOI here and in CITATION.cff. -->

BibTeX:

```bibtex
@mastersthesis{sousadasilva2026archroen,
  author = {Sousa da Silva, João Messias},
  title  = {Developing a Reproducible Workflow for AI-Assisted Chronological Data Extraction: A Case Study from Roman Villas in South Limburg},
  school = {University of Amsterdam},
  year   = {2026}
}
```

## Support

Have a question, or something not working? Please post it on the
[**Issues page**](../../issues), a simple web form for
reporting problems or asking questions. (You'll need a free GitHub account to post.)

## License

Code is released under the [MIT License](LICENSE). The excavation report PDFs carry mixed licenses
(CC BY 4.0, open access, public domain, and some still in copyright); see each dataset's README for
per-report sources and terms. The standard vocabulary used for normalization (ABR, by the RCE) is
released under CC0.

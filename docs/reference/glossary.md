# Glossary

Terms used in this documentation — both archaeological and workflow-specific.

## Workflow terms

| Term | Meaning |
|---|---|
| **Workflow** | The whole layered process that reads a report and produces the pottery summary. |
| **Layer** | One stage of the workflow, doing one job (see [../workflow/specs/](../workflow/specs/)). |
| **Pottery summary** | The single output CSV — one row per distinct pottery find (see [output_schema.md](output_schema.md)). |
| **Candidate / mention** | A detected occurrence of a term in the text, before it is judged or deduplicated. |
| **Find** | A distinct physical object the report says was found — one row in the summary. |
| **Mode (`WORKFLOW_MODE`)** | The master switch for how much AI is used: Rules-only / Claude / Llama / local-Llama (see [../design/workflow_modes.md](../design/workflow_modes.md)). |
| **Gold standard** | A hand-made CSV of the finds a report *should* yield, used to score the workflow. |
| **Hybrid extraction** | An AI path where the model reads the whole report and returns the find list directly. |
| **Consolidation / coreference** | Collapsing several mentions that refer to the *same* physical find into one row. |
| **Context window** | The slice of surrounding text stored with each candidate, used for judging and dating. |
| **OCR** | Optical Character Recognition — reading text out of a scanned/image-only page. |

## Archaeological terms

| Term | Meaning |
|---|---|
| **Typology** | A classification of pottery by standardised type. |
| **Typology code** | A reference like `Drag. 37`, `Dressel 20`, `Stuart 201` — a named scheme + number identifying a vessel type, which usually carries a known date range. |
| **Ware** | A class/fabric of pottery (e.g. *Samian ware*, *terra nigra*, *Gallo-Belgic ware*). |
| **Roman period** | The workflow's period of interest. In the Dutch context it begins ~12 BCE; finds clearly outside the Roman window are filtered out. |
| **n.Chr. / v.Chr.** | Dutch for *AD* (n.Chr., "na Christus") and *BC* (v.Chr., "voor Christus"). |
| **ABR / ARCHIS** | Dutch archaeological period-code standards (e.g. `ROM`, `ROMV`, `ME`) that map to date ranges. |
| **CAI** | Flemish *Centrale Archeologische Inventaris* — its 6-digit inventory codes can serve as a find's site key. |
| **Vondstnummer** | Dutch for "find number" — a registration number for an excavated find. |
| **Grey literature** | Unpublished or informally published reports (like excavation reports) — the workflow's input. |

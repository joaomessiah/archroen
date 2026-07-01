# Glossary

Terms used in this documentation, both archaeological and workflow-specific.

## Workflow terms

| Term | Meaning |
|---|---|
| **Workflow** | The whole layered process that reads a report and produces the pottery summary. |
| **Layer** | One stage of the workflow, doing one job (see [../workflow/specs/](../workflow/specs/)). |
| **Pottery summary** | The single output CSV, one row per distinct pottery find (see [output_schema.md](output_schema.md)). |
| **Candidate / mention** | A detected occurrence of a term in the text, before it is judged or deduplicated. |
| **Find** | A distinct physical object the report says was found, one row in the summary. |
| **Mode (`WORKFLOW_MODE`)** | The master switch for how much AI is used: Rules-only / Claude / Llama / local-Llama (see [../design/workflow_modes.md](../design/workflow_modes.md)). |
| **Gold standard** | A hand-made CSV of the finds a report *should* yield, used to score the workflow. |
| **Hybrid extraction (rules-LLM ensemble)** | The Layer 7 path where an LLM reads the whole report and returns the find list directly, while the deterministic rules ground and check it (dates, names, sites, verbatim-quote checks). |
| **Verbatim-quote contract** | The anti-hallucination rule that every model-produced find must carry a quote that actually appears in the report; finds whose quote cannot be located are dropped. |
| **Layer 3b** | Trigger-based extraction of pottery names not in the pattern list, plus figure/catalog finds (see `src/pottery_extractor.py`). |
| **Consolidation / coreference** | Collapsing several mentions that refer to the *same* physical find into one row. |
| **Context window** | The slice of surrounding text stored with each candidate, used for judging and dating. |
| **OCR** | Optical Character Recognition: reading text out of a scanned/image-only page. |

## Archaeological terms

| Term | Meaning |
|---|---|
| **Typology** | A classification of pottery by standardized type. |
| **Typology code** | A reference like `Drag. 37`, `Dressel 20`, `Stuart 201`: a named scheme plus a number that identifies a vessel type, which usually carries a known date range. |
| **Ware** | A class/fabric of pottery (e.g. *Samian ware*, *terra nigra*, *Gallo-Belgic ware*). |
| **Roman period** | The workflow's period of interest. Finds clearly outside it are filtered out; the exact bounds are set by `ROMAN_WINDOW` (see [config_options.md](config_options.md)). |
| **n.Chr. / v.Chr.** | Dutch for *AD* (n.Chr., "na Christus") and *BC* (v.Chr., "voor Christus"). |
| **ABR / ARCHIS** | The Dutch *Archeologisch Basisregister* (RCE) and the *ARCHIS* registration system. ABR supplies both the period codes (e.g. `ROM`, `ROMV`, `ME`) that map to date ranges and the ceramic ware/form/combiterm vocabulary behind the output's `std_*` columns. |
| **Standard vocabulary (`std_*`)** | The trailing output columns that map each find to a standard controlled vocabulary (currently ABR): ware, vessel form, and combined combiterm as code + label. They make the output interoperable with Archis and national heritage data, separate from the scored evaluation. See [output_schema.md](output_schema.md). |
| **CAI** | Flemish *Centrale Archeologische Inventaris*. Its 6-digit inventory codes can serve as a find's site key. |
| **Vondstnummer** | Dutch for "find number": a registration number for an excavated find. |
| **Grey literature** | Unpublished or informally published reports (like excavation reports): the workflow's input. |

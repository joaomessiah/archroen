# Configuration

Everything that changes the workflow's behavior lives in **`config.py`** at the top of the project.
To change a setting, edit that file. No other code needs to be touched. This page covers the settings
you're most likely to change. `config.py` itself is grouped into sections and commented, if you want
the full list.

After editing `config.py`, just re-run the workflow. There's nothing to "reload".

## The settings you'll change most often

| Setting | Default | What it does |
|---|---|---|
| `WORKFLOW_MODE` | `"claude"` | The master AI switch: `"rules-only"`, `"claude"`, `"cloud-llama"`, or `"local-llama"`. See [how_to_run.md](how_to_run.md#1-choose-a-mode). |
| `DEFAULT_REPORTS_DIR` | `…/workflow_evaluation_sample` | Which folder of PDFs to process. Point it at your own folder under `input_files/reports/`. |
| `BATCH_WORKERS` | `4` | How many reports to process at the same time. `1` = one at a time, with live progress. |

## Mode is the master switch

`WORKFLOW_MODE` is the important one. It decides, for **every** AI-assisted step at once, whether the
workflow uses AI and which provider. The more detailed flags below (`POTTERY_HYBRID_LLM_USE`,
`CHRONO_LLM_USE`, and so on) only take effect in the AI modes. In `"rules-only"` `config.py` forces
every detailed `*_LLM_USE` flag off automatically, so the run is fully deterministic no matter how
those flags are set.

You normally do **not** need to touch the detailed flags; `WORKFLOW_MODE` is enough. They exist for
fine-tuning and experiments:

| Setting | Default | What it does |
|---|---|---|
| `POTTERY_HYBRID_LLM_USE` | `True` | Let the AI read the *whole* report and produce the find list directly. |
| `POTTERY_CONTEXT_LLM_USE` | `True` | Use AI to judge whether a pottery mention is actually a find (vs a comparison/citation). |
| `CHRONO_LLM_USE` | `True` | Allow AI help when assigning date ranges (Layer 6). |
| `CHRONO_DATE_LLM_USE` | `False` | Let AI read dates straight from the text (off by default, since it is more error-prone). |
| `POTTERY_ROMAN_ONLY` | `True` | Keep only finds that are undated or overlap the Roman period. |
| `OCR_ENABLED` | `True` | Use OCR to read scanned / image-only PDFs. Needs `GOOGLE_VISION_API_KEY` in **every** mode, including `"rules-only"`. |
| `STANDARD_VOCAB_USE` | `True` | Append the seven ABR standard-vocabulary `std_*` interoperability columns. Deterministic and unscored; set off to omit them. (`STANDARD_VOCAB_STYLE` picks the standard; only `"abr"` is implemented.) |

## API keys are not in here

Keys are **not** set in `config.py`. They're read from your environment. See
[api_keys.md](api_keys.md).

## Where to go deeper

- The full per-flag reference (every `config.py` option explained) → [../reference/config_options.md](../reference/config_options.md)
- Why the modes exist and how they compare → [../design/workflow_modes.md](../design/workflow_modes.md)
- What the result columns mean → [../reference/output_schema.md](../reference/output_schema.md)
- The data files the workflow reads → [../reference/data_files.md](../reference/data_files.md)

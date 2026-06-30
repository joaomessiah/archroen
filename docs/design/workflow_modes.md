# Workflow modes

The workflow has one master switch, `WORKFLOW_MODE` in `config.py`, that decides whether and how it
uses an AI model. Every AI-assisted step in the workflow is routed through the same backend; there is
**no mixing** within a run (see [design_notes.md](design_notes.md#9-pure-workflow-modes-no-mixing) for
why). This page explains the modes and their trade-offs. For the operational *how to switch and run*,
see [../getting_started/how_to_run.md](../getting_started/how_to_run.md).

## The four modes

| `WORKFLOW_MODE` | In this documentation | Backend | Key needed |
|---|---|---|---|
| `"rules-only"` | **Rules-only mode** | No AI, fully deterministic | none |
| `"claude"` | **Claude mode** | Claude (Anthropic API) | `ANTHROPIC_API_KEY` |
| `"cloud-llama"` | **Llama mode** | Cloud Llama-3.3-70B (Together, OpenAI-compatible) | `LLM_API_KEY` |
| `"local-llama"` | *(local Llama)* | A local model via [Ollama](https://ollama.com) | none (runs on your machine) |

The thesis evaluated three of them: **Rules-only mode**, **Claude mode**, and **Llama mode**. The
local-Llama option exists for offline experimentation.

## What changes between modes

In **every** mode, the deterministic backbone runs identically: regex detection, normalization, the
typology/period date tables, the string-based site resolution, and the ABR standard-vocabulary mapping
(so the `std_*` columns are the same in every mode). What the mode changes is the set of
**AI-assisted fallbacks**: context interpretation (Layer 5), date reading (Layer 6), and the
deduplication, consolidation, and hybrid full-report extraction (Layer 7). In **Rules-only mode** all of
these fallbacks are switched off automatically, and the run is fully reproducible.

## Trade-offs

| | Rules-only | Claude | Llama (cloud) | local-Llama |
|---|---|---|---|---|
| **Cost** | free | paid API | paid API | free (your hardware) |
| **Internet** | not needed | required | required | not needed |
| **Reproducibility** | fully deterministic | **near-deterministic** (≤0.6 percentage-point drift across reruns, measured) | low temperature, not measured | low temperature, not measured |
| **Accuracy** | floor (rules only): 47.9% | highest in the thesis: 95.6% | mid: 77.3% | depends on local model |
| **Setup** | none | an Anthropic key | a Together key | install Ollama + pull a model |

- **Rules-only** is the honest baseline and the only deterministic mode. Start here to try the workflow
  with no key and no cost.
- **Claude mode** gave the best results in the thesis.
- **Llama mode** is the cloud open-model comparison point.
- **local-Llama** prioritizes running entirely offline and free over accuracy.

The **measured comparison** of these modes on the validation set is in
[../research/results.md](../research/results.md).

## Choosing a model within a mode

- Claude model: `ANTHROPIC_MODEL` in `config.py` (the Claude REST API, the default path; e.g.
  `claude-sonnet-4-6`). Only when the Claude Code CLI path is enabled (`HYBRID_USE_CLAUDE_CLI = True`)
  is the model set by `CLAUDE_CLI_MODEL` instead.
- Cloud Llama host/model: `LLM_API_BASE_URL` / `LLM_API_MODEL` (Together by default; OpenRouter,
  Fireworks, Groq, and Cerebras presets are in [../reference/config_options.md](../reference/config_options.md)).
  `cloud-llama` requires choosing a serverless model (some sizes are non-serverless on a given host;
  see the host presets in [../reference/config_options.md](../reference/config_options.md)).
- Local model: `LLM_MODEL` (the Ollama model name). `local-llama` requires the Ollama model to be
  pulled first.

Every `config.py` setting is explained flag-by-flag in
[../reference/config_options.md](../reference/config_options.md).

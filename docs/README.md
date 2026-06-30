# Documentation

This is a **workflow** that reads archaeological excavation reports (PDFs) and produces, for each
report, a tidy table of the pottery it mentions: what was found, how much, where, and the date range
each find belongs to. It was built for a master's thesis and is documented here so that other
researchers (and future you) can run it, understand it, and check the results.

## Where to start

Pick the path that matches what you want to do.

| I want to… | Go to |
|---|---|
| **Run it on my own reports** (start here if you're new) | [getting_started/](getting_started/) |
| **Understand how it works** layer by layer | [workflow/](workflow/) |
| **See the thesis research** (data, method, and results) | [research/](research/) |
| **Look something up** (output columns, data files, terms) | [reference/](reference/) |
| **Understand why it's built this way** | [design/](design/) |
| **Reuse the output in the Dutch ABR/Archis standard** | [reference/output_schema.md](reference/output_schema.md) (the `std_*` columns) |

## New here? Read these in order

1. [getting_started/prerequisites.md](getting_started/prerequisites.md): what you need on your computer first (no prior programming assumed)
2. [getting_started/installation.md](getting_started/installation.md): download the project and set it up
3. [getting_started/api_keys.md](getting_started/api_keys.md): the AI keys (optional, it also runs with no key at all)
4. [getting_started/quickstart.md](getting_started/quickstart.md): run it on one report and read the result
5. [getting_started/how_to_run.md](getting_started/how_to_run.md): the full guide on batches, modes, and evaluation

## A note on the AI models

The workflow can run in different **modes**. **Rules-only mode** uses no AI at all and is completely
free, a good way to try it first. **Claude mode** and **Llama mode** call a cloud AI
model to improve the results and need an API key, while **local-Llama mode** (`local-llama`, not
evaluated in the thesis) runs a model locally through Ollama and needs no key. See
[getting_started/api_keys.md](getting_started/api_keys.md),
[getting_started/configuration.md](getting_started/configuration.md), and
[design/workflow_modes.md](design/workflow_modes.md).

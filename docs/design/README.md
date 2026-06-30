# Design

Why the workflow is built the way it is: the decisions and trade-offs behind the layers, and the
different ways it can be run.

| File | What it covers |
|---|---|
| [design_notes.md](design_notes.md) | The key design decisions and trade-offs: anti-hallucination by verbatim quote, conservative consolidation, deterministic site resolution, graceful degradation, standards-vocabulary interoperability, and more. |
| [workflow_modes.md](workflow_modes.md) | The run modes (Rules-only / Claude / Llama / local-Llama): what each is, how they differ, and when to use which. |

See [../workflow/](../workflow/) for *how* each layer works, and [../research/results.md](../research/results.md) for how the modes compare in practice.

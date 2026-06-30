# Design notes

Why the workflow is built the way it is. These are the design decisions behind the layers; for *what*
each layer does, see [../workflow/specs/](../workflow/specs/).

## 1. LLM-led, with deterministic grounding

The workflow is **LLM-led**. An early rules-first build did not generalize to the variety of real grey
literature, so a frontier model reading the whole report became the primary approach (the **hybrid**
extractor; see §8). The deterministic rules remain essential, but in a **supporting** role.

**Why:** real excavation reports describe finds in prose, tables, captions, and appendices, with
cross-references that a per-chunk, rule-by-rule reader cannot resolve. A model reading the whole report
handles this far better. But a bare model is neither reproducible nor trustworthy enough for research,
so the rules **ground and constrain** it: dates come from the typology/period tables (never the model's
numbers), names from the vocabulary, sites from string-based resolution, and every find must carry a
verbatim quote (anti-hallucination). Run with no model at all (**Rules-only mode**), the same rule
pipeline becomes a fully deterministic, free baseline. This is also the comparison point in
[../research/results.md](../research/results.md).

## 2. A layered pipeline

Each layer does one well-defined job and hands a clear intermediate result to the next. **Why:** each
step is independently understandable and testable, problems are easy to localise, and the same chain
supports very different runs (deterministic vs AI-assisted) just by toggling per-layer behavior.

## 3. Vocabularies are the source of truth; patterns are generated

Canonical names and dates live in the CSVs under `data/vocabularies/`; the regex pattern files in
`data/patterns/` are **generated** from them (see [../reference/data_files.md](../reference/data_files.md)).
**Why:** one place to edit, no risk of patterns and vocabularies drifting apart, and regeneration is
idempotent.

## 4. One source of truth for periods and emperors

Every period/emperor → year-range mapping derives from a single table in `src/periods.py`. **Why:** the
same period word is used by the rule pipeline, the date parser, and the AI prompt, so deriving all of
them from one table guarantees they can never disagree. Emperor reigns deliberately win over broad
period-codes (so "Augustan" maps to 27 BC to 14 AD).

## 5. Conservative deduplication and consolidation

A report names the same find many times: in a finds table, in the conclusions, in an Archis appendix,
and in prose. Layer 7 collapses these, but **errs toward keeping finds separate when unsure**
(under-merging). **Why:** losing a real find is a worse error than leaving a duplicate. So numbered
finds-table rows are never dropped, typed finds never merge, and only groups anchored by a table cell
are consolidated.

## 6. Deterministic site resolution

The same place comes back spelled several ways across chunks. `src/site_norm.py` collapses variants to
one canonical site using a purely **string-based, reproducible** method (token-set union-find + a small
explicit Roman/modern alias map), with **no AI**. **Why:** site grouping should be stable and
auditable, not a model guess. (`src/site_norm.py` also ships an optional LLM canonicalizer,
`_canonicalize_sites_llm`, reachable via `apply_site_canonicalization(..., use_llm=True)`, but it is
**off by default**, so "no AI" describes the default path.)

## 7. Roman-period scope

The workflow targets the Roman period, so a scope filter (`POTTERY_ROMAN_ONLY`) keeps only finds that
are undated or overlap the Roman window. **Why:** it matches the thesis's research scope and removes
clearly-irrelevant later/earlier material, while keeping undated finds rather than silently dropping
them.

## 8. The hybrid full-report extractor

This is the **primary path in the AI modes**: rather than relying on the rule-based
detect→interpret→date→summarize chain alone, a frontier model reads the **whole report** and returns the
find list directly (`src/hybrid_extractor.py`, gated by `POTTERY_HYBRID_LLM_USE`). The rule pipeline
still runs underneath, grounding and cross-checking the model's output.

**Why a whole-report read:** a model seeing the entire report at once can resolve cross-references
(table to prose to appendix) that per-chunk rules judge in isolation. Two guardrails make it defensible
for research:

1. **Anti-hallucination by verbatim quote.** Every find must carry a quote that actually appears in the
   report; finds whose quote can't be located in the text are dropped.
2. **Deterministic date grounding.** When the model returns a typology code, the date comes from the
   canonical typology table (never the model's own number), so dates stay consistent with the rule
   pipeline.

It is **model-agnostic** (Claude when an Anthropic key is set, else the configured cloud model) so the
architecture runs without any one provider, and it **degrades gracefully**: if the hybrid step fails
(e.g. a rate-limit storm on a very large report), the pipeline falls back to the rule-based summary so
the report still completes.

## 9. "Pure" workflow modes, no mixing

`WORKFLOW_MODE` routes **every** AI-assisted step through the same provider, with no mixing within a
run. **Why:** a thesis comparing approaches needs each run to be attributable to exactly one backend.
A "claude" run never quietly calls a Llama model, and "rules-only" calls no model at all. This makes the
mode comparison ([../research/results.md](../research/results.md)) clean and defensible. The trade-offs
of each mode are in [workflow_modes.md](workflow_modes.md).

## 10. Standard-vocabulary interoperability (ABR)

A deterministic tail step (`src/standard_vocab.py`) maps each find to a national standard, currently the
Dutch **ABR** (Archeologisch Basisregister / Archis), appending the seven `std_*` columns. **Why:** a
summary in the project's own English vocabulary is hard to reuse, whereas emitting the national codes
lets the output drop into the Dutch heritage ecosystem without manual re-coding. The step is
deterministic and mode-independent (no model), so the codes are identical in every run mode, and it is
**unscored** (an interoperability layer, separate from the accuracy figures). The maps are built offline
from a frozen ABR snapshot by `tools/build_abr_maps.py` (the only place rdflib is used); the runtime
reads plain CSVs. The design is standard-agnostic (`STANDARD_VOCAB_STYLE`), with ABR the first standard
implemented, and finds too generic to place are left blank rather than guessed. See
[../workflow/specs/layer_7.md](../workflow/specs/layer_7.md) and
[../reference/data_files.md](../reference/data_files.md).

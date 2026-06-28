# Layer 7: Output assembly, validation, deduplication, and consolidation

**Modules:** `src/output_builder.py`, `src/validator.py`, `src/pottery_summary.py`, `src/site_norm.py`,
`src/consolidation.py`, `src/hybrid_extractor.py`

## Purpose

Build the per-find records, check them, and collapse repeated mentions of the same physical find into
the workflow's single deliverable: the **report-level pottery summary**. This is one row per distinct
find, a single `<report>.csv` per report. Getting from many raw mentions to one row per find is most of
this layer's work.

## The steps

### Record assembly + structural validation

- `output_builder.py` assembles each flat record into a structured record (grouping term / context /
  chronology / confidence / evidence / metadata), derives a **composite confidence**, and flags whether
  any AI step was used.
- `validator.py` checks each record is **structurally** well-formed (required fields present, values
  well-typed, an assigned chronology carries a numeric range). This is a structural sanity check only.
  It does **not** check correctness against a gold standard (that's [Layer 8](layer_8.md)), and runs as
  a console summary count.

### Build the pottery summary (`pottery_summary.py`)

The core cascade producing one row per distinct find:

- **Deduplicate** prose-vs-table re-mentions of the same find (deterministic markers first; an AI
  fallback for ambiguous cases, gated by `POTTERY_DEDUP_LLM_USE`).
- **Enrich** each find with canonical names and dates from the pottery vocabulary.
- **Resolve the find's site** (`site_norm.py`): the same place can be spelled several ways across
  chunks ("Tempsplein", "Heerlen, Tempsplein", "Heerlen (Coriovallum)"). This step collapses those
  variants to one canonical label. It uses a purely string-based, reproducible method, plus a small
  Roman↔modern alias map (e.g. *Coriovallum* = *Heerlen*).
- **Scope-filter** to the Roman period (`POTTERY_ROMAN_ONLY`): keep finds that are undated or overlap
  the Roman window. The window itself is `ROMAN_WINDOW` (default `(-52, 450)`), and
  `POTTERY_DROP_NONROMAN_LABELS` (default `True`) additionally drops fully-undated finds whose label
  names a sole non-Roman period; both operate alongside `POTTERY_ROMAN_ONLY`.
- Optional **AI context classification / date improvement** (`POTTERY_CONTEXT_LLM_USE`,
  `POTTERY_DATE_LLM_USE`).

### Find consolidation / coreference (`consolidation.py`)

The earlier steps judge each mention in isolation, so they can't tell that a finds table, a conclusion,
an Archis appendix, and a paragraph all describe the **same** physical find, and counting each one would
inflate the list. This pass groups mentions of the same ware per site, then asks the AI, which sees the
whole group at once, which mentions are distinct finds and which are recaps. It is **deliberately
conservative** (keep-when-unsure, so a duplicate survives rather than a real find being lost):

- Only groups containing a finds-**table** cell consolidate; pure-prose groups are left alone.
- **Typed** finds (a specific code) never consolidate: repeats are distinct.
- **Generic** wares ("Pottery" / "aardewerk") consolidate on AI judgement.
- **Named** wares consolidate only when their own text carries an explicit recap marker (e.g. a
  "vondstnummer N" citation, "fig.", "zie", "dit type"); an AI-judged recap alone is not enough to drop
  a named ware.
- Numbered finds-table rows are deterministic anchors and are never dropped.

Gated by `POTTERY_CONSOLIDATE_LLM_USE`.

### Hybrid full-report extraction (`hybrid_extractor.py`): the primary path in the AI modes

The workflow is LLM-led. In the AI modes, rather than relying on the rule-based
detect→interpret→date→summarise chain alone, an AI model reads the **whole report** and returns the find
list directly. The rule pipeline still runs underneath to ground and cross-check it. (In Rules-only
mode this step is off, and the rule-based summary is the output.) Two guardrails make it usable for
research:

1. **Anti-hallucination:** every find must carry a **verbatim quote** that actually appears in the
   report; finds whose quote can't be located are dropped.
2. **Deterministic date grounding:** when the model returns a typology code, the date comes from the
   canonical typology table, not the model's number, so dates stay consistent with the rule pipeline.

It is model-agnostic (Claude when an Anthropic key is set, otherwise the configured cloud model) and is
gated by `POTTERY_HYBRID_LLM_USE`. If the hybrid step fails (e.g. a rate-limit storm on a huge report),
the pipeline falls back to the rule-based summary so the report still completes.

## Output

A single `output_files/reports/<folder>/<report>.csv`, the pottery summary, the one deliverable. Its
columns (pottery name, typology, quantity, site, `start_date`/`end_date`, `date_method`, the per-aspect
certainty levels, the AI reasoning fields, and the original text) are documented in
[../../reference/output_schema.md](../../reference/output_schema.md).

## Reading the output

- **One row = one distinct physical find** that the report reports as present (after dedup,
  consolidation, and the Roman-period filter).
- **Dates** come from the typology table and/or the find's context; `date_method` says which.
- **Certainty columns** record how confident each aspect is (name, presence, dates, overall), and the
  `*_llm_reasoning` columns explain the AI's judgement where one was used.
- A blank date range usually means the find is genuine but **undated** in the report. It is kept under
  the Roman scope filter as undated.

## Configuration (`config.py`)

| Setting | Default | Role |
|---|---|---|
| `POTTERY_HYBRID_LLM_USE` | `True`* | Use the whole-report hybrid extractor |
| `POTTERY_CONTEXT_LLM_USE` | `True`* | AI context classification + date improvement |
| `POTTERY_DATE_LLM_USE` | `False` | AI typological date fallback |
| `POTTERY_DEDUP_LLM_USE` | `True`* | AI fallback for ambiguous dedup |
| `POTTERY_CONSOLIDATE_LLM_USE` | `True`* | Find consolidation (coreference) |
| `POTTERY_ROMAN_ONLY` | `True` | Keep only Roman-window / undated finds |
| `POTTERY_CAI_SITE_CODES` | `True` | Use the 6-digit CAI inventory code as the site key for Flemish CAI extracts |

\* AI-gated settings are forced off in **Rules-only mode**.

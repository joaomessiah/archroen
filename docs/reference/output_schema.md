# Output schema: the pottery summary CSV

The workflow's one deliverable is a CSV per report at `output_files/reports/<folder>/<report>.csv`.
**Each row is one distinct pottery find** that the report reports as present, after deduplication,
consolidation, and the Roman-period scope filter. Open it in any spreadsheet program.

The columns, in order:

| Column | Meaning |
|---|---|
| `report_id` | The report's identifier (its PDF filename stem). |
| `site_name` | The find's site, after site-name normalization (variants of one place collapsed to one label). |
| `page` | The page the find was reported on. |
| `pottery` | The pottery find's name (descriptive/canonical). |
| `typology` | The typology code if one applies (e.g. `Drag. 37`, `Dressel 20`); blank otherwise. |
| `term_found` | The term as it was actually detected in the report text. |
| `term_found_normalized_en` | That term normalized to its canonical English label. |
| `quantity` | How many were reported, when a count is stated. |
| `start_date` | Start of the date range, as a year (negative = BC). Blank if undated. |
| `end_date` | End of the date range, as a year (negative = BC). Blank if undated. |
| `date_method` | How the date was derived (a finite set of tags; see below). Blank when the find is undated. |
| `context_label` | How the report referred to the find (`present`, `comparison`, …); see [../workflow/specs/layer_5.md](../workflow/specs/layer_5.md). |
| `pot_name_certainty_level` | Confidence in the pottery name (`high` / `medium` / `low` / `uncertain`). |
| `pot_name_llm_reasoning` | The AI's explanation for the name, when the AI was involved. |
| `pot_presence_certainty_level` | Confidence that the pot was actually found (vs compared/cited). |
| `pot_presence_llm_reasoning` | The AI's explanation for the presence judgement, when involved. |
| `dates_certainty_level` | Confidence in the assigned date range. |
| `date_llm_reasoning` | The AI's explanation for the date, when the AI was involved. |
| `overall_certainty_level` | A combined confidence for the whole row. |
| `original_text` | The verbatim text the find was drawn from: the evidence trail. |

## `date_method` values

`date_method` is one of a finite set of tags. The rule pipeline emits:

- `typology`: from the canonical typology table (the most reliable).
- `text_explicit`: from explicit dates stated in the text.
- `period_term`: from a period/century term in the find's own quote.
- `section_phase`: from a dated phase in the section.
- `llm_context`: from dates the LLM read out of the context.
- `llm`: from the LLM's own date judgement.
- `context_clamp`: a missing endpoint filled from the Roman period context.

In the AI modes the hybrid extractor tags the backend it used (e.g. `claude`, `claude_text`,
`claude+typology`, `rules+claude`, `rules+claude_confirmed`; the prefix is the active backend). A
`+typology` suffix means the date was re-grounded against the typology table; a `_text` suffix means it
came from explicit text dates.

## Example row

A real row from `output_files/reports/south_limburg_villas/12703.csv` (Claude mode):

| Column | Value |
|---|---|
| `report_id` | `12703` |
| `site_name` | `198000` |
| `page` | `141` |
| `pottery` | `Argonnian terra sigillata bowl` |
| `typology` | `Chenet 320` |
| `term_found` | `Late Roman bowl Chenet 320 with roller-stamped decoration` |
| `term_found_normalized_en` | `Argonnian terra sigillata bowl` |
| `quantity` | `1` |
| `start_date` | `300` |
| `end_date` | `420` |
| `date_method` | `claude+typology` |
| `context_label` | `present` |
| `pot_name_certainty_level` | `10` |
| `pot_presence_certainty_level` | `10` |
| `dates_certainty_level` | `10` |
| `overall_certainty_level` | `10` |
| `original_text` | `Fragment of a Late Roman bowl Chenet 320 with roller-stamped decoration` |

(The `*_llm_reasoning` columns are omitted here for width; in this row they carry the model's short
justifications.)

## Reading tips

- **A blank `start_date`/`end_date`** usually means the find is genuine but **undated** in the report.
  It is still kept, because the Roman scope filter keeps undated finds.
- **`date_method`** tells you *how much to trust* a date: a typology-table date is the most reliable,
  and an AI-derived date is the least.
- The **`*_llm_reasoning`** columns are only populated when an AI mode was used and the AI made that
  particular judgement. In **Rules-only mode** they are blank.
- The **certainty levels** are recorded separately for the name, the presence, the dates, and overall,
  so you can filter to the rows you trust most (see the note below on the scale).

The **certainty levels** are a qualitative scale (`high` / `medium` / `low` / `uncertain`).

For how these rows are produced, see [../workflow/specs/layer_7.md](../workflow/specs/layer_7.md).

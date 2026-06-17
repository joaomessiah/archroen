# Output schema — the pottery summary CSV

The workflow's one deliverable is a CSV per report at `output_files/reports/<folder>/<report>.csv`.
**Each row is one distinct pottery find** the report reports as present, after deduplication,
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
| `date_method` | How the date was derived — e.g. from the typology table, from explicit text dates, from period/century terms, or by the AI. |
| `context_label` | How the report referred to the find (`present`, `comparison`, …); see [../workflow/specs/layer_5.md](../workflow/specs/layer_5.md). |
| `pot_name_certainty_level` | Confidence in the pottery name (`high` / `medium` / `low` / `uncertain`). |
| `pot_name_llm_reasoning` | The AI's explanation for the name, when the AI was involved. |
| `pot_presence_certainty_level` | Confidence that the pot was actually found (vs compared/cited). |
| `pot_presence_llm_reasoning` | The AI's explanation for the presence judgement, when involved. |
| `dates_certainty_level` | Confidence in the assigned date range. |
| `date_llm_reasoning` | The AI's explanation for the date, when the AI was involved. |
| `overall_certainty_level` | A combined confidence for the whole row. |
| `original_text` | The verbatim text the find was drawn from — the evidence trail. |

## Reading tips

- **A blank `start_date`/`end_date`** usually means the find is genuine but **undated** in the report;
  it is kept (the Roman scope filter keeps undated finds).
- **`date_method`** tells you *how much to trust* a date: a typology-table date is the most reliable;
  an AI-derived date is the least.
- The **`*_llm_reasoning`** columns are only populated when an AI mode was used and the AI made that
  particular judgement. In **Rules-only mode** they are blank.
- The **certainty levels** are a qualitative scale (`high` / `medium` / `low` / `uncertain`), recorded
  separately for the name, the presence, the dates, and overall — so you can filter to the rows you
  trust most.

For how these rows are produced, see [../workflow/specs/layer_7.md](../workflow/specs/layer_7.md).

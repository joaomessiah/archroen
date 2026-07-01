# Layer 6: Chronology assignment

**Modules:** `src/chronology.py` (orchestration), `src/date_parser.py` (date extraction),
`src/periods.py` (period/emperor date tables)

## Purpose

Attach a **date range** (`start_date` / `end_date`) to each eligible find, following a strict priority
order, and detect and reconcile conflicts between the date signals.

## The priority order

1. **Eligibility gate.** Decide whether a record gets a dating attempt, by its [Layer 5](layer_5.md)
   label: `present`/`comparison` are eligible; `absent`/`irrelevant` are skipped; `uncertain` qualifies
   only when `CHRONO_PROCESS_UNCERTAIN` is on and its confidence clears `CHRONO_UNCERTAIN_THRESHOLD`.
2. **Typology date first.** If the find has a known typology code, take its canonical date range from
   the typology table (built from `pottery_vocab_master.csv`).
3. **Then explicit text dates.** `date_parser.py` extracts explicit year ranges and century references
   from the surrounding context (English and Dutch ordinals, `n.Chr.`/`v.Chr.`).
4. **Then period / century terms.** Broad period and emperor names map to year ranges via
   `periods.py`. Patterns are applied in priority order (compound before single, explicit before
   century before broad), with span tracking so the same text isn't counted twice.
5. *(Optional)* **AI date fallback.** When `CHRONO_DATE_LLM_USE` is on, an AI step reads dates from
   context as a last resort. Off by default, as it is more error-prone.
6. **Conflict detection and reconciliation.** When the typology date and the context date disagree, the
   conflict is detected and reconciled into a single range, with the method recorded.

## Periods as a single source of truth (`periods.py`)

All period/emperor → year-range mappings derive from one table, so they can't drift apart. ABR/ARCHIS
period codes and their EN/NL synonyms come from `data/vocabularies/period_vocab.json`, emperor reigns
from `data/vocabularies/emperor_vocab.json`, and the named pre-Roman periods are literals in
`periods.py`. **Emperor reigns win** over period-code terms, so "Augustan"
maps to 27 BCE to 14 CE rather than the broader Roman-period code.

## Input and output

- **In:** interpreted candidates from [Layer 5](layer_5.md).
- **Out:** the same candidates, each with `start_date`, `end_date`, the `date_method` used, and a
  chronology confidence.

## Configuration (`config.py`)

| Setting | Default | Role |
|---|---|---|
| `CHRONO_PROCESS_UNCERTAIN` | `True` | Whether `uncertain` finds are dated |
| `CHRONO_UNCERTAIN_THRESHOLD` | `0.6` | Confidence an `uncertain` find must clear |
| `CHRONO_LLM_USE` | `True`* | Allow AI help in chronology |
| `CHRONO_DATE_LLM_USE` | `False` | Allow AI to read dates straight from context |

\* All AI-gated settings are forced off in **Rules-only mode**. The typology/period date lookups are
deterministic and run in every mode.

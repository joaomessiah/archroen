# Data files

The workflow reads two kinds of data from `data/`: **generated detection patterns** (`data/patterns/`)
and **source vocabularies + reference maps** (`data/vocabularies/`). All paths are wired through
`config.py`.

## How they relate

The vocabularies are the editable **source of truth**; the pattern files are **generated** from them by
the scripts in `tools/`. You never edit the patterns by hand.

```
data/vocabularies/*.csv  ──(tools/*.py generators)──▶  data/patterns/*.json  ──(runtime)──▶  detection
        │                                                                                       ▲
        └── pottery_vocab_normalized.csv, period_vocab.json, emperor_vocab.json ────────────────┘
            (these are read directly at runtime, too)
```

## `data/patterns/` — generated, loaded at runtime

| File | Used by | What it is |
|---|---|---|
| `pottery_patterns.json` | Layer 3 detection | Pottery detection regex, generated from `pottery_vocab_normalized.csv`. |
| `pottery_triggers.json` | Layer 3 detection | Trigger words (EN/NL/LA) that flag sentences likely to mention pottery. |
| `chronology_patterns.json` | Layer 6 dating | Chronological period patterns. |
| `century_patterns.json` | Layer 6 dating | Century-reference patterns. |

## `data/vocabularies/` — source of truth + reference maps

**Read directly at runtime:**

| File | Used by | What it is |
|---|---|---|
| `pottery_vocab_normalized.csv` | Layer 7 (and pattern generation) | Canonical pottery typologies with dates — the runtime reference list. |
| `period_vocab.json` | `src/periods.py` (Layer 6) | ABR/ARCHIS period codes + EN/NL synonyms with their date ranges. |
| `emperor_vocab.json` | `src/periods.py` (Layer 6) | Emperor reigns and named dynasties (canonical). |

**Build-time sources (inputs to the `tools/` generators, not loaded by the pipeline):**

| File | Feeds | What it is |
|---|---|---|
| `pottery_vocab_master.csv` | `normalize_vocab.py`, the code→date lookup | The enriched master pottery dataset the normalized list is built from. |
| `pottery_vocab_en.csv`, `pottery_vocab_nl.csv` | `build_pottery_dataset.py` | English/Dutch language sources for the master. |
| `century_vocab.csv` | `generate_century_patterns.py` | Source for `century_patterns.json`. |
| `chronology_vocab.csv` | `generate_chronology_patterns.py` | Source for `chronology_patterns.json`. |

## Updating the vocabularies

To add or correct pottery types, edit the source CSVs (or the master), then re-run the relevant
generator and the pipeline. The pottery patterns are regenerated with:

```bash
.venv/bin/python3 tools/csv_to_patterns.py \
    data/vocabularies/pottery_vocab_normalized.csv \
    data/patterns/pottery_patterns.json
```

Re-running the generators is safe and idempotent. To add a **trigger word**, add an entry to
`data/patterns/pottery_triggers.json` with a `language` (`en`/`nl`/`la`) and a `strength` (`strong` for
unambiguous pottery words, `weak` for words that need nearby context).

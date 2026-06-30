# Data files

The workflow reads two kinds of data from `data/`: **generated detection patterns** (`data/patterns/`)
and **source vocabularies plus reference maps** (`data/vocabularies/`). All paths are wired through
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

## `data/patterns/`: generated, loaded at runtime

| File | Used by | What it is |
|---|---|---|
| `pottery_patterns.json` | Layer 3 detection | Pottery detection regex, generated from `pottery_vocab_normalized.csv`. |
| `pottery_triggers.json` | Layer 3 detection | Trigger words (EN/NL/LA) that flag sentences likely to mention pottery. |
| `chronology_patterns.json` | Layer 6 dating | Chronological period patterns. |
| `century_patterns.json` | Layer 6 dating | Century-reference patterns. |

## `data/vocabularies/`: source of truth plus reference maps

**Read directly at runtime:**

| File | Used by | What it is |
|---|---|---|
| `pottery_vocab_normalized.csv` | Layer 7 (and pattern generation) | Canonical pottery typologies with dates: the runtime reference list. |
| `period_vocab.json` | `src/periods.py` (Layer 6) | ABR/ARCHIS period codes + EN/NL synonyms with their date ranges. |
| `emperor_vocab.json` | `src/periods.py` (Layer 6) | Emperor reigns and named dynasties (canonical). |

**Build-time sources (inputs to the `tools/` generators, not loaded by the pipeline):**

| File | Feeds | What it is |
|---|---|---|
| `pottery_vocab_master.csv` | `normalize_vocab.py`, the code→date lookup | The enriched master pottery dataset the normalized list is built from. |
| `pottery_vocab_en.csv`, `pottery_vocab_nl.csv` | `build_pottery_dataset.py` | English/Dutch language sources for the master. |
| `century_vocab.csv` | `generate_century_patterns.py` | Source for `century_patterns.json`. |
| `chronology_vocab.csv` | `generate_chronology_patterns.py` | Source for `chronology_patterns.json`. |

## `data/vocabularies/standards/`: standard-vocabulary maps

Maps the pipeline's finds to an external standard controlled vocabulary, producing the `std_*`
output columns (see [output_schema.md](output_schema.md)). One subfolder per standard style; only
`abr/` (Dutch Archeologisch Basisregister) is implemented.

**Read directly at runtime (`src/standard_vocab.py`, when `STANDARD_VOCAB_USE` is on):**

| File | What it is |
|---|---|
| `abr/ware_map.csv` | ABR ceramic-category (ware/fabric) code + Dutch label + URI + English aliases + `needs_review`. |
| `abr/form_map.csv` | ABR vessel-form code + Dutch label + URI + English aliases + `needs_review`. |
| `abr/combined_map.csv` | ABR combiterms (ware+form, optionally with a typology): code, label, and the ware/form/typology it decomposes into. |

**Build-time sources (not loaded by the pipeline):**

| File | What it is |
|---|---|
| `abr/source/abr_dump_*.trig.gz` | Frozen ABR Linked-Open-Data snapshot (CC0, RCE). The single source the maps are generated from. |
| `abr/source/README.md` | Provenance: source URL, snapshot/download date, triple count, regenerate command. |
| `abr/*_generated.csv` | Pure extract from the dump (overwritten on regenerate). |
| `abr/*_overrides.csv` | Hand-curated English aliases + corrections, merged on top of the generated rows. |

Regenerate with `.venv/bin/python3 tools/build_abr_maps.py` (needs `rdflib`, a build-time-only
dependency). Editing an `*_overrides.csv` and re-running never destroys it; the generated extract is
rebuilt from the frozen dump. The `needs_review` flag marks alias mappings that warrant an expert eye.

## Updating the vocabularies

To add or correct pottery types, edit the source CSVs (or the master), then re-run the relevant
generator and the pipeline. The pottery patterns are regenerated with this command:

```bash
.venv/bin/python3 tools/csv_to_patterns.py \
    data/vocabularies/pottery_vocab_normalized.csv \
    data/patterns/pottery_patterns.json
```

Re-running the generators is safe and idempotent. To add a **trigger word**, add an entry to
`data/patterns/pottery_triggers.json` with a `language` (`en`/`nl`/`la`) and a `strength`. Use
`strong` for unambiguous pottery words and `weak` for words that need nearby context.

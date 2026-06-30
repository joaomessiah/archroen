# tools/

Offline **maintenance and build scripts**. They are run by hand to regenerate the project's
*generated* artifacts (the detection patterns under `data/patterns/`, the normalized vocabularies, and
the ABR standard-vocabulary maps) from the editable source data. The pipeline itself
(`run_pipeline.py`) never imports or runs anything here; a normal run only reads the already-generated
files. You only need these scripts when you change a source vocabulary or the ABR snapshot and want to
rebuild.

Run each with the project venv, e.g. `.venv/bin/python3 tools/<script>.py`.

Typical full rebuild order: `build_pottery_dataset.py` -> `normalize_vocab.py` -> `csv_to_patterns.py`;
`generate_century_patterns.py`, `generate_chronology_patterns.py`, and `build_abr_maps.py` are
independent of that chain.

## Vocabulary build

The canonical pottery reference is built in two steps from the hand-maintained `pottery_vocab_en.csv`
and `pottery_vocab_nl.csv` under `data/vocabularies/`.

- **`build_pottery_dataset.py`** builds `data/vocabularies/pottery_vocab_master.csv`, the canonical
  pottery dataset. It reads the EN and NL vocabularies and enriches each typology code with its
  abbreviations, German/French names, ware type, vessel form, production region, and date range (plus a
  date source and confidence), and resolves cross-system synonym relationships. Run it after editing the
  EN/NL pottery vocabularies.
- **`normalize_vocab.py`** reads `pottery_vocab_master.csv` and writes
  `data/vocabularies/pottery_vocab_normalized.csv`. It groups synonymous typology codes (from the
  master's `synonyms` column) into a single canonical entry, so every variant (individual codes,
  abbreviations, and combinations) resolves to one code and one date range. Run it after rebuilding the
  master.

## Detection patterns (Layer 3)

`data/patterns/` holds the regex detection patterns the pipeline reads in Layer 3. It is a **generated
directory, never hand-edited**; these scripts regenerate it from the vocabularies.

- **`csv_to_patterns.py <input.csv> <output.json>`** converts a pottery vocabulary CSV into
  `data/patterns/pottery_patterns.json` (the pottery-name and typology-code detection patterns). Current
  build: `tools/csv_to_patterns.py data/vocabularies/pottery_vocab_normalized.csv data/patterns/pottery_patterns.json`.
- **`generate_century_patterns.py [century_vocab.csv]`** generates
  `data/patterns/century_patterns.json` from `data/vocabularies/century_vocab.csv`. Single-century
  entries come from the CSV; adjacent-pair ranges (e.g. "2nd and 3rd centuries AD") are generated
  automatically, because the first ordinal in such a phrase is not followed by "centur" and would
  otherwise go undetected.
- **`generate_chronology_patterns.py [chronology_vocab.csv]`** generates
  `data/patterns/chronology_patterns.json` (the named period / phase patterns) from
  `data/vocabularies/chronology_vocab.csv`.
- **`patterns_to_csv.py [input.json] [output.csv]`** is the reverse direction, for review only: it dumps
  `data/patterns/chronology_patterns.json` back to a human-readable CSV
  (`chronology_patterns_review.csv`) so the generated patterns can be eyeballed. It does not feed the
  pipeline.

## Standard-vocabulary maps (ABR)

- **`build_abr_maps.py`** rebuilds the ABR (Archeologisch Basisregister) map CSVs under
  `data/vocabularies/standards/abr/` from the frozen RDF snapshot at `.../abr/source/abr_dump_*.trig.gz`.
  It emits the three `*_generated.csv` extracts and then the three runtime maps (`ware_map.csv`,
  `form_map.csv`, `combined_map.csv`), which are the generated rows merged with the hand-curated
  `*_overrides.csv`. This is the only script that uses `rdflib` (a build-time dependency); the pipeline
  runtime reads the plain CSVs and never imports rdflib. The build is deterministic (byte-reproducible
  across runs). Run it after updating the ABR snapshot or the override files. See
  `data/vocabularies/standards/abr/README.md` for the map files and the ABR data model.

## Validation

- **`validate_gold_typology.py <gold.csv> ...`** quality-checks a gold-standard CSV's `Typology` column
  against the pottery master. Each value is resolved and sorted into `resolved_code` (matched cleanly to
  a canonical master code), `master_gap` (looks like a real typology but missing from the master, so a
  candidate to add rather than blank in the gold), or `not_typology`. It writes an annotated copy
  (`<gold-stem>.csv`, with those columns) to `outputs/gold_standard_validations/` and prints a summary;
  `--master` and `--out-dir` override the defaults. Used when curating gold standards, not as part of any
  build.

## Figure generation

- **`scientific_report/`** holds the scripts that produce the thesis charts and maps. Each subfolder
  (`generate_charts/`, `generate_maps_roman_villas/`) has its own README with usage and outputs.

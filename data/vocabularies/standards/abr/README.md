# ABR standard-vocabulary maps

Maps each pottery find to the Dutch **ABR** (Archeologisch Basisregister) standard, producing the
`std_*` columns of the pottery summary (see
[../../../../docs/reference/output_schema.md](../../../../docs/reference/output_schema.md)). Read at
runtime by `src/standard_vocab.py` when `STANDARD_VOCAB_USE` is on. Only this `abr/` style exists; a
new standard would be a sibling folder under `data/vocabularies/standards/`.

## The three-file pattern

Each map (`ware`, `form`, `combined`) is built from two inputs and a merge:

| File | Role |
|---|---|
| `*_generated.csv` | **Pure extract** from the frozen ABR dump (overwritten on every regenerate). Do not edit by hand. |
| `*_overrides.csv` | **Hand curation**: English aliases for the pipeline's terms, the SIKB ware codes, and corrections. Merged on top of the generated rows. Edit this. |
| `*_map.csv` (e.g. `ware_map.csv`) | **Final, runtime-read** map = generated + overrides. Regenerated, not edited. |

- `ware_map`: ABR ceramic-category (ware/fabric) code + Dutch label + URI + English aliases.
- `form_map`: ABR vessel-form code + Dutch label + URI + English aliases.
- `combined_map`: ABR combiterms (ware+form, optionally with a typology): code, label, and the ware/form/typology
  each decomposes into. (Fully generated; no overrides file.)

The `needs_review` column on the ware/form maps flags alias mappings that warrant an expert eye.

## Regenerate

```bash
.venv/bin/python3 tools/build_abr_maps.py
```

Reads `source/abr_dump_*.trig.gz` (see [source/README.md](source/README.md)) and rewrites the
`*_generated.csv` and final `*_map.csv` files, merging your `*_overrides.csv` on top, so editing an
overrides file and re-running never loses your curation. Needs `rdflib` (a build-time-only
dependency; the pipeline itself does not import it).

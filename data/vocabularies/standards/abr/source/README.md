# ABR source snapshot

Frozen source data for the ABR (Archeologisch Basisregister) standard-vocabulary mapping.
The map CSVs in the parent folder are **generated from this snapshot** (see the regenerate
command below). This file is committed so the maps are reproducible offline, without re-fetching.

## Provenance

| | |
|---|---|
| Dataset | Archeologisch Basisregister (ABR) |
| Publisher | Rijksdienst voor het Cultureel Erfgoed (RCE) |
| License | **CC0 1.0** (public domain dedication) |
| Snapshot file | `abr_dump_20260629.trig.gz` (322,658 triples) |
| Download date | 2026-06-29 |
| Source (full RDF dump) | https://linkeddata.cultureelerfgoed.nl/thesauri/archeologischbasisregister/download.trig.gz |
| SPARQL endpoint | https://api.linkeddata.cultureelerfgoed.nl/datasets/thesauri/archeologischbasisregister/services/archeologischbasisregister-jena/sparql |
| Concept-scheme URI | https://data.cultureelerfgoed.nl/term/id/abr/b402446a-0a00-4fee-a9cd-1a7f307d651e |

Ware terms are also cross-checked against the SIKB **KNA Leidraad 4** Roman-pottery concordance
(`Bijlage concordantielijst leidraad Romeins aardewerk artefactype`, v1.1, 2020).

## Regenerate the maps

```bash
.venv/bin/python3 tools/build_abr_maps.py
```

The parser reads this frozen dump and writes `*_generated.csv` in the parent folder. Manual
curation lives in the per-map `*_overrides.csv` files (e.g. `ware_map_overrides.csv`) and is merged
on top of the generated rows (so regenerating never destroys hand corrections).

## Notes

- `rdflib` is required by the parser only (a build-time tool); the pipeline runtime reads the
  generated CSVs and never imports `rdflib`.
- CC0 imposes no attribution requirement; RCE is credited here as a courtesy.

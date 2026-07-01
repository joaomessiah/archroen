# Roman-villa set (application corpus)

The **30 Roman-villa excavation reports** that are the subject of the thesis. This is the *application*
corpus: the reports the workflow was actually built to read and summarize. There are **no gold
standards** for this set; it is the real-world task, not the accuracy-measurement set (for that, see
[validation_set.md](validation_set.md)).

## Files

| Item | Location |
|---|---|
| Report PDFs (27 of 30; 3 link-only for copyright) | [roman_villas/input_reports/](roman_villas/input_reports/) |
| Live report PDFs | [input_files/reports/south_limburg_villas/](../../../input_files/reports/south_limburg_villas/) |
| Outputs (frozen snapshot) | [roman_villas/outputs/](roman_villas/outputs/) |
| Live outputs (regenerated) | `output_files/reports/south_limburg_villas/` |

Each output is one `<report_id>.csv` pottery summary; the columns are documented in
[../../reference/output_schema.md](../../reference/output_schema.md).

Each output also carries the seven **ABR standard-vocabulary** columns (`std_*`): every find in this
application corpus is mapped to the Dutch national standard (Archeologisch Basisregister / Archis), so
the South Limburg villa data comes out ready to feed into the national heritage infrastructure without
manual re-coding. Most finds (about 86%) resolve to a standard code; the mapping is deterministic, and
spot-checks consistently confirm the codes resolve correctly.

> The frozen `outputs/` here are a **snapshot** of the thesis run. Re-running the workflow regenerates
> the live versions under `output_files/`.

Because there are no gold standards, **this set has no scores or evaluation**: the artifacts here are
outputs only. The site locations of this corpus are shown on the villa maps at [../maps/](../maps/).

## Reproducing

```python
# in config.py:
DEFAULT_REPORTS_DIR = BASE_DIR / "input_files" / "reports" / "south_limburg_villas"
WORKFLOW_MODE = "claude"   # the mode used for the application run
```

```bash
.venv/bin/python3 run_pipeline.py
```

See [../../getting_started/how_to_run.md](../../getting_started/how_to_run.md) for details.

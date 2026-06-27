# Roman-villa set (application corpus)

The **30 Roman-villa excavation reports** that are the subject of the thesis. This is the *application*
corpus: the reports the workflow was actually built to read and summarise. There are **no gold
standards** for this set — it is the real-world task, not the accuracy-measurement set (for that, see
[validation_set.md](validation_set.md)).

## Files

| Item | Location |
|---|---|
| Report PDFs (30, frozen snapshot) | [roman_villas/input_reports/](roman_villas/input_reports/) |
| Live report PDFs | [input_files/reports/south_limburg_villas/](../../../input_files/reports/south_limburg_villas/) |
| Outputs (frozen snapshot) | [roman_villas/outputs/](roman_villas/outputs/) |
| Live outputs (regenerated) | `output_files/reports/south_limburg_villas/` |

Each output is one `<report>.csv` pottery summary; the columns are documented in
[../../reference/output_schema.md](../../reference/output_schema.md).

> The frozen `outputs/` here are a **snapshot** of the thesis run. Re-running the workflow regenerates
> the live versions under `output_files/`.

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

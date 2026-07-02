# Datasets

The thesis uses two corpora of reports. This page is the map: what each is, and **where the files live**.
The inputs and gold standards stay in the workflow's normal locations (so they remain runnable), and a
**frozen copy of the outputs** is kept here so the exact results behind the thesis are preserved even
after the live outputs are regenerated.

| Corpus | Reports | Gold standards | Purpose |
|---|---|---|---|
| [Roman-villa set](roman_villas.md) | 30 | (none) | The real-world **application** |
| [Validation set](validation_set.md) | 20 | 20 | **Accuracy measurement** |

## Where everything lives

| Item | Location |
|---|---|
| Roman-villa report PDFs (frozen) | [roman_villas/input_reports/](roman_villas/input_reports/) |
| Roman-villa report PDFs (live) | [input_files/reports/south_limburg_villas/](../../../input_files/reports/south_limburg_villas/) |
| Roman-villa outputs (frozen) | [roman_villas/outputs/](roman_villas/outputs/) (30 CSVs) |
| Validation report PDFs (frozen) | [validation_set/input_reports/](validation_set/input_reports/) |
| Validation report PDFs (live) | [input_files/reports/workflow_evaluation_sample/](../../../input_files/reports/workflow_evaluation_sample/) |
| Validation gold standards | [input_files/gold_standards/workflow_evaluation_sample/](../../../input_files/gold_standards/workflow_evaluation_sample/) |
| Validation outputs (frozen, per mode) | [validation_set/outputs/](validation_set/outputs/) (`<mode>/`, 20 CSVs each) |
| Validation ABR demonstration (frozen) | [validation_set/outputs/std_abr/](validation_set/outputs/std_abr/) (20 CSVs: Claude output with the ABR `std_*` columns; a separate capability demo, not a scored mode) |
| Validation scores (frozen, per mode) | [validation_set/scores/](validation_set/scores/) (`<mode>/`) |

Scores exist **only for the validation set**; the Roman-villa set has no gold standards and therefore no
scores (outputs only).

`<mode>` is one of `claude`, `llama`, `rules_only`. The copies here are a **snapshot** of the results
reported in the thesis. A live run writes to `output_files/reports/workflow_evaluation_sample/` (the
three modes share one input folder); each mode's output folder was renamed to `…_mode_<mode>` after its
run to keep the three apart, which is why the frozen copies carry those names.

## Reproducing

To regenerate any of these, set `WORKFLOW_MODE` in `config.py`, run the workflow on the batch folder,
then the evaluation. See [../../getting_started/how_to_run.md](../../getting_started/how_to_run.md).
Each run overwrites `output_files/reports/workflow_evaluation_sample/`, so to keep all three modes (as
the thesis did) rename that folder to `…_mode_<mode>` between runs and point the evaluation at it. The
frozen copies here let you compare your fresh run against the thesis results.

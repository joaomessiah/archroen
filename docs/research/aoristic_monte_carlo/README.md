# Aoristic and Monte Carlo analysis (case study)

A downstream case study that applies **aoristic analysis** and **Monte Carlo simulation** to the dated
Roman-villa ceramics extracted by ARCHROEN, benchmarking the result against an independent reference
dataset (labeled SGRE). The question it tests: does automated
extraction reproduce the chronological signal of independently curated records for the same 16 South
Limburg villa sites?

## What it shows

- Each dataset is reduced to per-site, per-period **proportional** chronological profiles (Early /
  Middle / Late Roman), with Monte Carlo uncertainty bands, so the two can be compared regardless of
  sample size.
- The profiles agree closely: **dominant-period agreement is 15/16 sites (94%)**, even though the
  ARCHROEN extraction has ~5.5x more finds than the reference (**1,066 analyzed records vs 194**).
- Full per-site metrics (Spearman, Pearson, dominant-period match, MAD) are in
  [outputs/eval_metrics_per_site.csv](outputs/eval_metrics_per_site.csv).

## Method and data notes

**Roman periods.** Early Roman (−12 to 70), Middle Roman (71-275), Late Roman (276-450); negative years
are BCE, and year 0 is treated as 1 BCE. The periods are unequal in length, so results are reported both
as absolute aoristic weight and as duration-normalized intensity (weight per year).

**Aoristic weighting.** Each ceramic record is a date range, not a point. It is treated as a uniform
mass of 1 (unweighted) and distributed across the three periods in proportion to temporal overlap, and
the per-record weights are summed per site. Monte Carlo simulation (1,000 iterations, seed 42, 25-year
bins, uniform sampling within each range) provides the 5th-95th percentile uncertainty band. The
formulas and parameters live in `aoristic_analysis.py` and `evaluation_comparison.py`.

**Why the comparison is at the site-period level.** SGRE finds are linked to a SiteID only, not to a
specific report, and each villa site is covered by several reports, so there is no shared key to join
individual ARCHROEN and SGRE records. The comparison therefore uses each site's proportional profile
across the three periods. Because absolute weight scales with record count (ARCHROEN is ~5.5x larger),
raw totals are not compared; both datasets are row-normalized first.

**SGRE reference provenance.** `ori_4zl_aori.csv` was built exclusively by filtering the RCE
`04-Finds_ZL` export (not included in this repo): restricted to the 16 villa sites, keeping every object
in the ceramic category (not narrowed to vessels or forms), and retaining the existing start/end date
ranges. No external records, dates, or attributes were added. Result: 194 records.

**Cleaning.** ARCHROEN: 1,636 report rows, minus 569 with empty dates = 1,067, minus 1 zero-duration
record = **1,066 analyzed** across 16 sites. Six reports lost all their rows to date-filtering; three
sites (11947, 12143, 12233) have no dated pottery and drop out entirely. SGRE: all 194 records survive
cleaning.

## Contents

| Path | What |
|---|---|
| [aoristic_analysis.py](aoristic_analysis.py) | Aoristic weights + Monte Carlo on the ARCHROEN dataset; writes the figures plus `aoristic_weights.csv` and `monte_carlo_results.csv`. |
| [evaluation_comparison.py](evaluation_comparison.py) | Compares ARCHROEN against the SGRE reference; writes the `eval_*` figures plus `eval_metrics_per_site.csv`. |
| [build_dataset.py](build_dataset.py) | Rebuilds `data/aoristic_dataset.csv` from the frozen villa outputs + `sites.csv` (verified to reproduce the committed dataset). |
| [data/](data/) | Inputs: `aoristic_dataset.csv` (ARCHROEN-derived), `ori_4zl_aori.csv` (SGRE reference). Provenance only (not read at run time): `sites.csv`, `literature_zl.csv`. |
| [outputs/](outputs/) | Frozen figures and result tables, the study's deliverables. |

## Run

```bash
pip install -r ../../../requirements.txt   # needs pandas, numpy, matplotlib, seaborn
python build_dataset.py          # optional: regenerate data/aoristic_dataset.csv from ../datasets/roman_villas/outputs/
python aoristic_analysis.py
python evaluation_comparison.py
```

The two analysis scripts (`aoristic_analysis.py`, `evaluation_comparison.py`) write to `outputs/` and
use a non-interactive plotting backend, so they run headless. The
Monte Carlo is seeded, so results are reproducible.

## Data sources and licensing

- `aoristic_dataset.csv` is derived from ARCHROEN's own extracted output for the villa corpus (built
  upstream from the frozen outputs at `../datasets/roman_villas/outputs/`).
- The reference records in `ori_4zl_aori.csv` come from **Archis (RCE)** and are reused under
  **CC BY 4.0**.
- Coordinates are retained only for known, published, excavated villa sites; the raw region-wide find
  export is deliberately not included.

#!/usr/bin/env python3
"""Build variance_summary_raw.csv (the AS-MEASURED consolidated table) from the five frozen
granular_summary.csv files. The headline metric is FIELD-LEVEL CORRECTNESS = (exact + acceptable)
/ all field verdicts, across 5 fields per finding — the same metric the thesis reports (95.6%,
see docs/research/results.md). Self-contained: reads scores/run_N/."""
import csv
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = [1, 2, 3, 4, 5]


def total_row(n):
    p = HERE / "scores" / f"run_{n}" / "granular_summary.csv"
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["report"].upper() == "TOTAL":
                return r
    raise RuntimeError(f"no TOTAL row in run {n}")


tots = {n: total_row(n) for n in RUNS}


def series(fn):
    return [fn(tots[n]) for n in RUNS]


correct = series(lambda t: int(t["total_correct_values"]))
total = series(lambda t: int(t["total_values"]))

metrics = [("field_correctness_pct", [round(c / v * 100, 2) for c, v in zip(correct, total)]),
           ("correct_values", correct),
           ("incorrect_values", series(lambda t: int(t["total_incorrect_values"]))),
           ("missing_values", series(lambda t: int(t["total_missing_values"]))),
           ("overclaim_values", series(lambda t: int(t["total_overclaim_values"]))),
           ("total_values", total)]
# per-field correct counts (exact + acceptable) — to locate the softest field
for field in ("site_name", "pottery", "typology", "start_date", "end_date"):
    metrics.append((f"{field}_correct",
                    series(lambda t, fld=field: int(t[f"{fld}_exact"]) + int(t[f"{fld}_acceptable"]))))
    metrics.append((f"{field}_incorrect", series(lambda t, fld=field: int(t[f"{fld}_incorrect"]))))

out = HERE / "variance_summary_raw.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["metric", "run_1", "run_2", "run_3", "run_4", "run_5",
                "mean", "sd_sample", "min", "max", "range", "cv_pct"])
    for name, vals in metrics:
        mean = st.mean(vals)
        sd = st.stdev(vals) if len(set(vals)) > 1 else 0.0
        lo, hi = min(vals), max(vals)
        cv = (sd / mean * 100) if mean else 0.0
        w.writerow([name] + [f"{v:g}" for v in vals]
                   + [f"{mean:.4g}", f"{sd:.4g}", f"{lo:g}", f"{hi:g}", f"{hi - lo:g}", f"{cv:.2g}"])

print(f"Wrote {out}")
with open(out, encoding="utf-8") as f:
    print(f.read())

#!/usr/bin/env python3
"""Apply the manual adjudication (variance_adjudication_worksheet.csv) to the raw per-run field
verdicts and derive variance_summary_corrected.csv — FIELD-LEVEL CORRECTNESS, raw vs corrected.

Field-level correctness = (exact + acceptable) / all field verdicts (the thesis metric, 95.6%).
A MISSING + an OVERCLAIM both marked `match` are the same find mis-scored as two problems; in each
run where both occur they reconcile into one matched record. The matched record's 5 field verdicts
are scored with the harness's OWN functions (evaluate_granular.pair_cells), so the corrected number
uses the model's actual output (e.g. generic 'Pottery' vs gold 'Roman ware' scores as it really is),
not an inflated match. Pairing is per run and per report (each missing greedily paired to its
best-scoring overclaim), honouring run-specific pairings (e.g. old_rep_3)."""
import sys
import csv
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evaluation"))
import evaluate as ev            # noqa: E402
import evaluate_granular as eg   # noqa: E402

HERE = Path(__file__).resolve().parent
GOLD_DIR = ROOT / "input_files" / "gold_standards" / "workflow_evaluation_sample"
RUNS = [1, 2, 3, 4, 5]


def total_row(n):
    p = HERE / "scores" / f"run_{n}" / "granular_summary.csv"
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["report"].upper() == "TOTAL":
                return r
    raise RuntimeError(n)


ws = []
with open(HERE / "variance_adjudication_worksheet.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        r["_runs"] = {int(x) for x in r["runs_present"].split(",") if x.strip()}
        ws.append(r)
assert {r["verdict_TODO"].strip() for r in ws} <= {"match", "real_miss", "real_extra"}, "bad verdicts"
reports = sorted({r["report"] for r in ws if r["verdict_TODO"].strip() == "match"})


def find(rows, pot, s, e):
    k = (ev.keyname(pot), ev.to_int(s), ev.to_int(e))
    for row in rows:
        if (ev.keyname(row["pot"]), row["s"], row["e"]) == k:
            return row
    for row in rows:                       # relax dates if the exact key is absent
        if ev.keyname(row["pot"]) == k[0]:
            return row
    return None


pairs, raw_c, raw_t, cor_c, cor_t = {}, {}, {}, {}, {}
cor_field_inc = {}   # run -> {field: corrected incorrect-value count}
for n in RUNS:
    tot = total_row(n)
    rc, rt = int(tot["total_correct_values"]), int(tot["total_values"])
    field_inc = {fld: int(tot[f"{fld}_incorrect"]) for fld in eg.FIELDS}  # raw; pairs add to it
    sumK = P = 0
    for rep in reports:
        opath = HERE / "reports" / f"run_{n}" / f"{rep}.csv"
        if not opath.exists():
            continue
        grows = eg.gload(GOLD_DIR / f"{rep}.csv", *eg.GOLD_COLS)
        orows = eg.gload(opath, *eg.OUT_COLS)
        miss = [find(grows, r["pottery"], r["start"], r["end"]) for r in ws
                if r["report"] == rep and r["type"] == "MISSING"
                and r["verdict_TODO"].strip() == "match" and n in r["_runs"]]
        over = [find(orows, r["pottery"], r["start"], r["end"]) for r in ws
                if r["report"] == rep and r["type"] == "OVERCLAIM"
                and r["verdict_TODO"].strip() == "match" and n in r["_runs"]]
        miss, over = [g for g in miss if g], [p for p in over if p]
        used = set()
        for g in miss:
            bestK, bestj, bestcells = -1, None, None
            for j, p in enumerate(over):
                if j in used:
                    continue
                cells = eg.pair_cells(g, p)
                K = sum(1 for fld in eg.FIELDS if cells[fld][0] in ("exact", "acceptable"))
                if K > bestK:
                    bestK, bestj, bestcells = K, j, cells
            if bestj is not None:
                used.add(bestj)
                sumK += bestK
                P += 1
                for fld in eg.FIELDS:   # the new matched record's wrong fields become incorrect
                    if bestcells[fld][0] not in ("exact", "acceptable"):
                        field_inc[fld] += 1
    pairs[n], raw_c[n], raw_t[n] = P, rc, rt
    cor_c[n], cor_t[n] = rc + sumK, rt - 5 * P
    cor_field_inc[n] = field_inc


def stat_row(name, vals, pct=False):
    mean = st.mean(vals)
    sd = st.stdev(vals) if len(set(vals)) > 1 else 0.0
    lo, hi = min(vals), max(vals)
    cv = (sd / mean * 100) if mean else 0.0
    fmt = (lambda v: f"{v:.2f}") if pct else (lambda v: f"{v:g}")
    return [name] + [fmt(v) for v in vals] + [f"{mean:.4g}", f"{sd:.4g}",
                                              fmt(lo), fmt(hi), fmt(hi - lo), f"{cv:.2g}"]


raw_pct = [round(raw_c[n] / raw_t[n] * 100, 2) for n in RUNS]
cor_pct = [round(cor_c[n] / cor_t[n] * 100, 2) for n in RUNS]

out = HERE / "variance_summary_corrected.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["metric", "run_1", "run_2", "run_3", "run_4", "run_5",
                "mean", "sd_sample", "min", "max", "range", "cv_pct"])
    w.writerow(stat_row("pairs_reconciled", [pairs[n] for n in RUNS]))
    w.writerow(stat_row("field_correctness_pct_raw", raw_pct, pct=True))
    w.writerow(stat_row("field_correctness_pct_corrected", cor_pct, pct=True))
    w.writerow(stat_row("correct_values_corrected", [cor_c[n] for n in RUNS]))
    w.writerow(stat_row("total_values_corrected", [cor_t[n] for n in RUNS]))
    for fld in eg.FIELDS:   # corrected incorrect-value count per field (raw + reconciled-pair misses)
        w.writerow(stat_row(f"{fld}_incorrect_corrected", [cor_field_inc[n][fld] for n in RUNS]))

print(f"{'run':>4}{'pairs':>6}{'raw%':>8}{'corrected%':>11}")
for n in RUNS:
    print(f"{n:>4}{pairs[n]:>6}{raw_pct[n-1]:>8.2f}{cor_pct[n-1]:>11.2f}")
print(f"\nRaw field-correctness      : mean {st.mean(raw_pct):.2f}%  range {min(raw_pct):.2f}-{max(raw_pct):.2f}")
print(f"Corrected field-correctness: mean {st.mean(cor_pct):.2f}%  SD {st.stdev(cor_pct):.2f}  "
      f"range {min(cor_pct):.2f}-{max(cor_pct):.2f}")
print(f"Thesis (mode_claude): 95.56%")
print(f"\nWrote {out}")

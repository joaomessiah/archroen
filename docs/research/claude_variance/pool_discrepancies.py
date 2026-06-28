#!/usr/bin/env python3
"""Pool MISSING + OVERCLAIM rows across the 5 Claude runs into a single
review-once adjudication worksheet. Each unique discrepancy is keyed by
(report, type, pottery, start, end) and tagged with which runs it appears in,
so a pair-mismatch (a MISSING + an OVERCLAIM that are really the same find)
can be reconciled once and applied to every run.
"""
import csv
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent   # self-contained: reads the frozen scores/ alongside
RUNS = [1, 2, 3, 4, 5]

# key -> {info, runs:set}
miss = defaultdict(lambda: {"runs": set()})
over = defaultdict(lambda: {"runs": set()})

for n in RUNS:
    path = HERE / "scores" / f"run_{n}" / "granular_detail.csv"
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = r["pottery_verdict"]
            rep = r["report"]
            if v == "missing":
                pot = r["pottery_gold"]
                typ = r["typology_gold"]
                s, e = r["start_date_gold"], r["end_date_gold"]
                k = (rep, pot, typ, s, e)
                miss[k]["info"] = (rep, pot, typ, s, e)
                miss[k]["runs"].add(n)
            elif v == "overclaim":
                pot = r["pottery_workflow"]
                typ = r["typology_workflow"]
                s, e = r["start_date_workflow"], r["end_date_workflow"]
                k = (rep, pot, typ, s, e)
                over[k]["info"] = (rep, pot, typ, s, e)
                over[k]["runs"].add(n)

# Console: per-report, missing vs overclaim side by side
reports = sorted({k[0] for k in list(miss) + list(over)})
print(f"\n{'='*92}\nPOOLED DISCREPANCIES across 5 runs  (review each ONCE, apply to all runs it appears in)\n{'='*92}")
for rep in reports:
    ms = sorted([d for k, d in miss.items() if k[0] == rep], key=lambda d: d["info"][1])
    os_ = sorted([d for k, d in over.items() if k[0] == rep], key=lambda d: d["info"][1])
    if not ms and not os_:
        continue
    print(f"\n### {rep}")
    if ms:
        print("  MISSING (gold find not produced):")
        for d in ms:
            _, pot, typ, s, e = d["info"]
            runs = ",".join(str(x) for x in sorted(d["runs"]))
            print(f"    [{len(d['runs'])}/5 runs: {runs}]  pot='{pot}' typ='{typ}' dates={s}..{e}")
    if os_:
        print("  OVERCLAIM (produced, not in gold):")
        for d in os_:
            _, pot, typ, s, e = d["info"]
            runs = ",".join(str(x) for x in sorted(d["runs"]))
            print(f"    [{len(d['runs'])}/5 runs: {runs}]  pot='{pot}' typ='{typ}' dates={s}..{e}")

# CSV worksheet. Guard: never overwrite the authoritative worksheet (it carries the manual
# verdicts). On a fresh checkout this writes the blank template; if it already exists, the
# regenerated template goes to a side file so the filled verdicts are preserved.
out = HERE / "variance_adjudication_worksheet.csv"
if out.exists():
    out = HERE / "variance_adjudication_worksheet.regenerated.csv"
    print(f"NOTE: filled worksheet exists; writing blank template to {out.name} instead.")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["report", "type", "pottery", "typology", "start", "end",
                "n_runs", "runs_present", "verdict_TODO", "paired_with_TODO"])
    rows = []
    for k, d in miss.items():
        rep, pot, typ, s, e = d["info"]
        rows.append((rep, "MISSING", pot, typ, s, e, len(d["runs"]),
                     ",".join(map(str, sorted(d["runs"])))))
    for k, d in over.items():
        rep, pot, typ, s, e = d["info"]
        rows.append((rep, "OVERCLAIM", pot, typ, s, e, len(d["runs"]),
                     ",".join(map(str, sorted(d["runs"])))))
    for row in sorted(rows, key=lambda r: (r[0], r[1], r[2])):
        w.writerow(list(row) + ["", ""])

print(f"\n{'='*92}")
print(f"Unique MISSING items : {len(miss)}   (raw rows across runs: {sum(len(d['runs']) for d in miss.values())})")
print(f"Unique OVERCLAIM items: {len(over)}   (raw rows across runs: {sum(len(d['runs']) for d in over.values())})")
print(f"Worksheet -> {out}")

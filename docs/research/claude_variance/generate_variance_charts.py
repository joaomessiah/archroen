#!/usr/bin/env python3
"""Generate the figure for the variance study (grayscale, print-safe, 300 DPI) into
chart_outputs/correctness_per_run.png — field-level correctness per run, full 0-100% axis
(the thesis metric, 95.6%). Numbers read from variance_summary_corrected.csv."""
import csv
import statistics as st
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = HERE / "chart_outputs"
OUT.mkdir(exist_ok=True)
RUNS = [1, 2, 3, 4, 5]
DPI = 300
BG = "#ffffff"
DARK, MID, LIGHT = "#303030", "#9a9a9a", "#cfcfcf"
plt.rcParams.update({"font.size": 11, "axes.titlesize": 13, "font.family": "DejaVu Sans"})


def read_metric(path, metric):
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["metric"] == metric:
                return r
    raise KeyError(metric)


# ---------- Field-level correctness figures use the CORRECTED per-run values only ----------
# Field-level correctness = (exact + acceptable) / all field verdicts — the thesis headline metric.
cor = read_metric(HERE / "variance_summary_corrected.csv", "field_correctness_pct_corrected")
cor_v = [float(cor[f"run_{n}"]) for n in RUNS]
cor_mean = st.mean(cor_v)
x = list(range(len(RUNS)))

# ---------- Figure A: corrected field-level correctness per run, full 0-100% axis ----------
# Five level bar-tops on a full axis = "every run lands at the same correctness" (near-deterministic),
# with no truncated-baseline exaggeration. Exact per-run values are labelled; dashed line = mean.
fig, ax = plt.subplots(figsize=(6.6, 4.7), facecolor=BG)
ax.set_facecolor(BG)
ax.bar(x, cor_v, width=0.62, color=DARK, edgecolor="#222", linewidth=1, zorder=2)
ax.axhline(cor_mean, ls="--", lw=1.1, color="#888", zorder=3)
lbl_y = max(cor_v) + 1.2   # just above the tallest bar, below the 100% line
for xi, v in zip(x, cor_v):
    ax.text(xi, lbl_y, f"{v:.2f}%", ha="center", va="bottom", fontsize=10,
            fontweight="bold", color="#111")
ax.set_xlim(-0.6, 4.6)
ax.set_xticks(x)
ax.set_xticklabels([f"Run {n}" for n in RUNS], fontsize=10)
ax.set_ylim(0, 100)
ax.set_yticks([0, 20, 40, 60, 80, 100])
ax.set_ylabel("Field-level correctness (%)")
ax.set_title("Field-level correctness per execution — Claude mode", pad=16)
ax.grid(axis="y", ls="--", lw=0.7, color="#8a8a8a", alpha=0.4)
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.5, 0.01,
         f"Bars = field-level correctness per run; dashed line = 5-run mean ({cor_mean:.2f}%).",
         ha="center", fontsize=8.0, color="#555")
fig.tight_layout(rect=[0, 0.05, 1, 1])
fig.savefig(OUT / "correctness_per_run.png", dpi=DPI, bbox_inches="tight", facecolor=BG)
plt.close(fig)

print(f"Wrote {OUT}/correctness_per_run.png")

"""
Aoristic Analysis - Roman Villa Sites, South Limburg

Two metrics computed throughout:
  Option A - Absolute aoristic weight  : w = overlap / record_duration
  Option B - Duration-normalized intensity: w / period_duration (weight per year)

Outputs
-------
1.  aoristic_weights.csv          - weights + intensity per site per period
2.  stacked_bar.png               - side-by-side: absolute vs intensity
3.  heatmap.png                   - side-by-side: proportion heatmaps
4.  regional_curve.png            - stacked panels: absolute + intensity curves
5.  maps_per_period.png           - 2-row maps: absolute (top) + intensity (bottom)
6.  gantt_timeline.png            - Gantt (opacity = intensity-normalized weight)
7.  monte_carlo_comparison.png    - MC vs aoristic + intensity + phases
    monte_carlo_results.csv       - raw MC output table
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════

DATA_PATH  = Path(__file__).resolve().parent / "data" / "aoristic_dataset.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

PERIODS = {
    "Early Roman":  (-12,  70),
    "Middle Roman": ( 71, 275),
    "Late Roman":   (276, 450),
}
PERIOD_LIST = list(PERIODS.keys())

PERIOD_DUR = {p: pe - ps for p, (ps, pe) in PERIODS.items()}

PERIOD_GRAY = {
    "Early Roman":  "#1a1a1a",
    "Middle Roman": "#6b6b6b",
    "Late Roman":   "#b8b8b8",
}
HATCH = {"Early Roman": "", "Middle Roman": "//", "Late Roman": ".."}

N_SIM           = 1000
PHASE_THRESHOLD = 0.10
BIN_SIZE        = 25
RANDOM_SEED     = 42
DPI             = 300
T_START, T_END  = -12, 450
PANEL_BG        = "#ebebeb"

plt.rcParams.update({
    "font.family":     "serif",
    "font.size":       13,
    "axes.labelsize":  14,
    "axes.titlesize":  14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
})

def gg_style(ax):
    ax.set_facecolor(PANEL_BG)
    ax.grid(True, color="white", linewidth=0.8, linestyle="-", zorder=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

def clean_style(ax):
    ax.set_facecolor("white")
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")

# ══════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════

df = pd.read_csv(DATA_PATH)
df["start_date"]        = pd.to_numeric(df["start_date"],        errors="coerce")
df["end_date"]          = pd.to_numeric(df["end_date"],          errors="coerce")
df["site_x_coordinate"] = pd.to_numeric(df["site_x_coordinate"], errors="coerce")
df["site_y_coordinate"] = pd.to_numeric(df["site_y_coordinate"], errors="coerce")
df["site_id"]           = df["site_id"].astype(str)
df = df.dropna(subset=["start_date", "end_date"]).copy()
df = df[df["end_date"] > df["start_date"]].copy()

print(f"Records loaded : {len(df)}")
print(f"Sites          : {df['site_id'].nunique()}")

# ══════════════════════════════════════════════════════════
# AORISTIC COMPUTATION  (Option A)
# ══════════════════════════════════════════════════════════

def overlap(s, e, ps, pe):
    return max(0.0, min(e, pe) - max(s, ps))

rows_w = []
for _, r in df.iterrows():
    dur = r["end_date"] - r["start_date"]
    rec = {"site_id": r["site_id"]}
    for p, (ps, pe) in PERIODS.items():
        rec[p] = overlap(r["start_date"], r["end_date"], ps, pe) / dur
    rows_w.append(rec)

rec_df = pd.DataFrame(rows_w)

site_aor = (
    rec_df.groupby("site_id")[PERIOD_LIST]
    .sum().reset_index()
    .sort_values("site_id").reset_index(drop=True)
)

coord_lu = (
    df.groupby("site_id")[["site_x_coordinate", "site_y_coordinate"]]
    .first()
    .rename(columns={"site_x_coordinate": "X", "site_y_coordinate": "Y"})
    .reset_index()
)
site_aor = site_aor.merge(coord_lu, on="site_id", how="left")

totals_aor    = site_aor[PERIOD_LIST].sum(axis=1)
site_aor_norm = site_aor.copy()
site_aor_norm[PERIOD_LIST] = site_aor[PERIOD_LIST].div(totals_aor, axis=0)

# ══════════════════════════════════════════════════════════
# INTENSITY COMPUTATION  (Option B: weight per year)
# ══════════════════════════════════════════════════════════

site_int = site_aor.copy()
for p in PERIOD_LIST:
    site_int[p] = site_aor[p] / PERIOD_DUR[p]

totals_int    = site_int[PERIOD_LIST].sum(axis=1)
site_int_norm = site_int.copy()
site_int_norm[PERIOD_LIST] = site_int[PERIOD_LIST].div(totals_int, axis=0)

ids = site_aor["site_id"].tolist()

# Site label: "Name-Toponym" (used in Gantt y-axis)
_name_lu = (
    df.groupby("site_id")[["site_name", "site_toponym"]]
    .first().reset_index()
)
site_label = {
    row["site_id"]: f"{row['site_name']}-{row['site_toponym']}"
    for _, row in _name_lu.iterrows()
}

print(f"\nPeriod durations (years): " +
      " | ".join(f"{p}: {d}" for p, d in PERIOD_DUR.items()))

# ══════════════════════════════════════════════════════════
# OUTPUT 1 - CSV
# ══════════════════════════════════════════════════════════

out_csv = site_aor[["site_id", "X", "Y"] + PERIOD_LIST].copy()
out_csv["total_weight"] = out_csv[PERIOD_LIST].sum(axis=1)
for p in PERIOD_LIST:
    out_csv[f"{p}_pct"]      = (out_csv[p] / out_csv["total_weight"] * 100).round(2)
    out_csv[f"{p}_intensity"] = (out_csv[p] / PERIOD_DUR[p]).round(4)
out_csv.to_csv(OUTPUT_DIR / "aoristic_weights.csv", index=False)
print("\n[1/7] aoristic_weights.csv saved")

# ══════════════════════════════════════════════════════════
# OUTPUT 2 - Stacked bar: A (left) | B (right)
# ══════════════════════════════════════════════════════════

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7), sharey=False)
fig.patch.set_facecolor("white")

for ax, data, ylabel, title_suffix in [
    (ax1, site_aor, "Aoristic Weight",          "Option A - Absolute Aoristic Weight"),
    (ax2, site_int, "Intensity (weight / year)", "Option B - Duration-Normalized Intensity"),
]:
    bottoms = np.zeros(len(data))
    for p in PERIOD_LIST:
        vals = data[p].values
        ax.bar(ids, vals, bottom=bottoms,
               color=PERIOD_GRAY[p], label=p,
               edgecolor="white", linewidth=0.5)
        bottoms += vals
    ax.set_xlabel("Site ID")
    ax.set_ylabel(ylabel)
    ax.set_title(title_suffix)
    ax.set_xticks(range(len(ids)))
    ax.set_xticklabels(ids, rotation=45, ha="right", fontsize=11)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3,
              frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=12)
    clean_style(ax)

fig.suptitle("Aoristic Analysis - Roman Villa Sites, South Limburg", fontsize=15)
plt.tight_layout()
plt.subplots_adjust(bottom=0.22)
plt.savefig(OUTPUT_DIR / "stacked_bar.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[2/7] stacked_bar.png saved")

# ══════════════════════════════════════════════════════════
# OUTPUT 3 - Heatmap: proportion A | proportion B
# ══════════════════════════════════════════════════════════

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 20))
fig.patch.set_facecolor("white")

for ax, data, subtitle, show_xlabels in [
    (ax1, site_aor_norm, "Option A - Proportion of aoristic weight",    False),
    (ax2, site_int_norm, "Option B - Proportion of intensity (per year)", True),
]:
    heat = data.set_index("site_id")[PERIOD_LIST]
    heat.index = [site_label.get(sid, sid) for sid in heat.index]
    sns.heatmap(
        heat, annot=True, fmt=".2f",
        annot_kws={"size": 12},
        cmap="Greys", linewidths=0.5, linecolor="white",
        vmin=0, vmax=1, ax=ax,
        cbar_kws={"label": "Proportion", "shrink": 0.4,
                  "orientation": "horizontal", "pad": 0.03},
        xticklabels=show_xlabels,
    )
    ax.set_title(subtitle, fontsize=13, pad=12)
    ax.set_xlabel("")
    ax.set_ylabel("Site")
    ax.tick_params(axis="y", labelsize=12)
    if show_xlabels:
        ax.tick_params(axis="x", labelsize=12)

fig.suptitle(
    "Chronological Activity per Period - Roman Villa Sites, South Limburg",
    fontsize=14, y=1.01,
)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "heatmap.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[3/7] heatmap.png saved")

# ══════════════════════════════════════════════════════════
# REGIONAL MC  (used in Output 4)
# ══════════════════════════════════════════════════════════

print("\nRunning regional Monte Carlo...", end=" ", flush=True)
np.random.seed(RANDOM_SEED)

bins   = np.arange(T_START, T_END + BIN_SIZE, BIN_SIZE)
bin_c  = (bins[:-1] + bins[1:]) / 2
n_bins = len(bins) - 1

aor_curve = np.zeros(n_bins)
for _, r in df.iterrows():
    dur = r["end_date"] - r["start_date"]
    if dur <= 0:
        continue
    for i in range(n_bins):
        ov = overlap(r["start_date"], r["end_date"], bins[i], bins[i + 1])
        aor_curve[i] += ov / dur

int_curve = aor_curve / BIN_SIZE

src = df[["start_date", "end_date"]].values
mc_curves = np.zeros((N_SIM, n_bins))
for sim in range(N_SIM):
    samples = np.random.uniform(src[:, 0], src[:, 1])
    for i in range(n_bins):
        mc_curves[sim, i] = np.sum((samples >= bins[i]) & (samples < bins[i + 1]))

mc_mean = mc_curves.mean(axis=0)
mc_p5   = np.percentile(mc_curves, 5,  axis=0)
mc_p95  = np.percentile(mc_curves, 95, axis=0)

mc_mean_int = mc_mean / BIN_SIZE
mc_p5_int   = mc_p5   / BIN_SIZE
mc_p95_int  = mc_p95  / BIN_SIZE

site_bin_w = np.zeros((len(ids), n_bins))
for si, sid in enumerate(ids):
    sub = df[df["site_id"] == sid]
    for _, r in sub.iterrows():
        dur = r["end_date"] - r["start_date"]
        if dur <= 0:
            continue
        for i in range(n_bins):
            ov = overlap(r["start_date"], r["end_date"], bins[i], bins[i + 1])
            site_bin_w[si, i] += ov / dur

n_active = np.sum(site_bin_w > 0.05, axis=0).astype(float)

def scale_to(arr, target_max):
    return arr / arr.max() * target_max if arr.max() > 0 else arr

print("done.")

# ══════════════════════════════════════════════════════════
# OUTPUT 4 - Regional curves: absolute (top) + intensity (bottom)
# Figure sized for half A4 width (~5.5 in): fonts scaled up so text
# prints at ~12pt after reduction.
# ══════════════════════════════════════════════════════════

_RC4 = {
    "font.size":       16,
    "axes.labelsize":  16,
    "axes.titlesize":  16,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
}
with plt.rc_context(_RC4):
    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(5.5, 8), sharex=True)
    fig.patch.set_facecolor("white")

    for ax, curve, mc_m, p5, p95, ylabel, title in [
        (ax_a, aor_curve, mc_mean,     mc_p5,     mc_p95,
         f"Aoristic Weight\n({BIN_SIZE}-yr bins)",
         "Option A - Absolute Aoristic Weight"),
        (ax_b, int_curve, mc_mean_int, mc_p5_int, mc_p95_int,
         "Intensity\n(weight / year)",
         "Option B - Duration-Normalized Intensity"),
    ]:
        gg_style(ax)
        ax.fill_between(bin_c, p5, p95, color="#aaaaaa", alpha=0.5,
                        label="MC 5th-95th percentile", zorder=1)
        ax.step(bin_c, curve, where="mid", color="black",
                linewidth=1.8, linestyle="-",  label="Aoristic weight", zorder=3)
        ax.step(bin_c, mc_m,  where="mid", color="#444444",
                linewidth=1.4, linestyle=":",  label="MC expected",     zorder=3)
        n_scaled = scale_to(n_active, curve.max())
        ax.step(bin_c, n_scaled, where="mid", color="#222222",
                linewidth=1.4, linestyle="--", label="Active sites (scaled)", zorder=3)

        for p, (ps, pe) in PERIODS.items():
            ax.axvline(ps, color="white", linewidth=1.0, zorder=2)
        ax.axvline(0, color="#888888", linewidth=0.9, linestyle="--", zorder=2)

        ylim_top = ax.get_ylim()[1]
        short = {"Early Roman": "Early", "Middle Roman": "Middle", "Late Roman": "Late"}
        for p, (ps, pe) in PERIODS.items():
            ax.text((ps + pe) / 2, ylim_top * 0.96, short[p],
                    ha="center", va="top", fontsize=12,
                    color="#333333", fontstyle="italic")

        ax.set_ylabel(ylabel, labelpad=6)
        ax.set_title(title, loc="left", fontsize=14)

    ax_b.set_xlim(T_START, T_END)
    ax_b.set_xlabel("Year (CE; negative = BCE)")
    fig.suptitle(
        "Regional Chronological Activity\nSouth Limburg Roman Villa Landscape",
        fontsize=15, y=0.99,
    )

    handles, labels = ax_a.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.0),
               ncol=2, frameon=True, facecolor=PANEL_BG, edgecolor="white",
               fontsize=12)

    plt.tight_layout(rect=[0, 0.13, 1, 0.95])
    plt.subplots_adjust(hspace=0.25)
    plt.savefig(OUTPUT_DIR / "regional_curve.png", dpi=DPI, bbox_inches="tight")
    plt.close()
print("[4/7] regional_curve.png saved")

# ══════════════════════════════════════════════════════════
# OUTPUT 5 - Maps: absolute (row 1) + intensity (row 2)
# ══════════════════════════════════════════════════════════

site_map     = site_aor.dropna(subset=["X", "Y"]).copy()
site_map_int = site_int.dropna(subset=["X", "Y"]).copy()

fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.patch.set_facecolor("white")

for row_idx, (data, cbar_label) in enumerate([
    (site_map,     "Aoristic Weight"),
    (site_map_int, "Intensity (wt/yr)"),
]):
    global_max = data[PERIOD_LIST].values.max()
    for col_idx, period in enumerate(PERIOD_LIST):
        ax = axes[row_idx, col_idx]
        w      = data[period].values
        w_norm = w / w.max() if w.max() > 0 else w
        sc = ax.scatter(data["X"], data["Y"],
                        s=w_norm * 500 + 25,
                        c=w, cmap="Greys", vmin=0, vmax=global_max,
                        edgecolors="black", linewidths=0.7, alpha=0.9, zorder=3)
        for _, r in data.iterrows():
            if r[period] > 0:
                ax.annotate(r["site_id"], (r["X"], r["Y"]),
                            xytext=(5, 5), textcoords="offset points",
                            fontsize=9, color="#222222")
        cb = plt.colorbar(sc, ax=ax, shrink=0.7)
        cb.set_label(cbar_label, fontsize=11)
        cb.ax.tick_params(labelsize=10)
        ax.set_title(period, fontweight="bold", fontsize=13)
        ax.set_xlabel("X (RD New, m)", fontsize=11)
        ax.set_ylabel("Y (RD New, m)", fontsize=11)
        ax.set_aspect("equal")
        ax.ticklabel_format(style="sci", axis="both", scilimits=(0, 0))
        ax.tick_params(labelsize=10)
        clean_style(ax)

# Row labels as figure text on the left margin
fig.text(0.01, 0.74, "Option A\nAbsolute Aoristic Weight",
         va="center", ha="left", fontsize=12, rotation=90,
         color="#333333")
fig.text(0.01, 0.27, "Option B\nDuration-Normalized Intensity",
         va="center", ha="left", fontsize=12, rotation=90,
         color="#333333")

fig.suptitle("Spatial Distribution of Villa Activity per Period - South Limburg",
             fontsize=15, y=1.01)
plt.tight_layout(rect=[0.04, 0, 1, 1])
plt.savefig(OUTPUT_DIR / "maps_per_period.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[5/7] maps_per_period.png saved")

# ══════════════════════════════════════════════════════════
# OUTPUT 6 - Gantt (opacity = intensity-normalized weight)
# ══════════════════════════════════════════════════════════

site_ranges = (
    df.groupby("site_id")
    .agg(min_start=("start_date", "min"), max_end=("end_date", "max"))
    .reset_index().sort_values("site_id").reset_index(drop=True)
)

int_norm_lu = site_int_norm.set_index("site_id")

fig, ax = plt.subplots(figsize=(13, 9))
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

for p, (ps, pe) in PERIODS.items():
    ax.axvline(ps, color="#cccccc", linewidth=1.0, zorder=1)
ax.axvline(T_END, color="#cccccc", linewidth=1.0, zorder=1)
ax.axvline(0, color="#999999", linewidth=1.0, linestyle="--", zorder=1)

for i, (_, row) in enumerate(site_ranges.iterrows()):
    sid = row["site_id"]
    if sid not in int_norm_lu.index:
        continue
    for p in PERIOD_LIST:
        ps, pe = PERIODS[p]
        w = float(int_norm_lu.loc[sid, p])
        if w > 0.01:
            ax.barh(i, pe - ps, left=ps, height=0.65,
                    color=PERIOD_GRAY[p], alpha=max(0.15, w),
                    edgecolor="white", linewidth=0.3, zorder=2)

ax.set_yticks(range(len(site_ranges)))
gantt_labels = [
    site_label.get(sid, sid)
    for sid in site_ranges["site_id"].tolist()
]
ax.set_yticklabels(gantt_labels, fontsize=12)
ax.set_xlabel("Year (CE; negative = BCE)")
ax.set_title(
    "Chronological Timeline of Roman Villa Sites - South Limburg\n"
    "(bar opacity = intensity-normalized weight per period)"
)
ax.set_xlim(T_START, T_END)
ax.invert_yaxis()

for p, (ps, pe) in PERIODS.items():
    ax.text((ps + pe) / 2, -0.8, p, ha="center", va="top",
            fontsize=12, color="#333333", fontstyle="italic")

patches = [mpatches.Patch(color=PERIOD_GRAY[p], label=p) for p in PERIOD_LIST]
ax.legend(handles=patches, loc="upper center",
          bbox_to_anchor=(0.5, -0.08), ncol=3,
          frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=12)
clean_style(ax)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "gantt_timeline.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[6/7] gantt_timeline.png saved")

# ══════════════════════════════════════════════════════════
# MONTE CARLO - PER SITE
# ══════════════════════════════════════════════════════════

print("Running per-site Monte Carlo...", end=" ", flush=True)
np.random.seed(RANDOM_SEED)

site_data = {sid: df[df["site_id"] == sid][["start_date", "end_date"]].values
             for sid in ids}
mc_store  = {sid: {p: np.zeros(N_SIM) for p in PERIOD_LIST} for sid in ids}

for sim in range(N_SIM):
    for sid in ids:
        data    = site_data[sid]
        samples = np.random.uniform(data[:, 0], data[:, 1])
        for p, (ps, pe) in PERIODS.items():
            mc_store[sid][p][sim] = np.sum((samples >= ps) & (samples <= pe))

mc_rows = []
for sid in ids:
    row   = {"site_id": sid}
    means = {p: mc_store[sid][p].mean() for p in PERIOD_LIST}
    stds  = {p: mc_store[sid][p].std()  for p in PERIOD_LIST}
    total = sum(means.values())
    n_ph  = sum(1 for p in PERIOD_LIST
                if total > 0 and means[p] / total > PHASE_THRESHOLD)
    for p in PERIOD_LIST:
        row[f"{p}_mc_mean"]     = round(means[p], 3)
        row[f"{p}_mc_std"]      = round(stds[p],  3)
        row[f"{p}_mc_mean_int"] = round(means[p] / PERIOD_DUR[p], 4)
        row[f"{p}_mc_std_int"]  = round(stds[p]  / PERIOD_DUR[p], 4)
    row["n_phases"] = n_ph
    mc_rows.append(row)

mc_df = pd.DataFrame(mc_rows)
mc_df.to_csv(OUTPUT_DIR / "monte_carlo_results.csv", index=False)
print("done.")

# ══════════════════════════════════════════════════════════
# OUTPUT 7 - MC comparison: A (absolute) | B (intensity)
# ══════════════════════════════════════════════════════════

aor_lu = site_aor.set_index("site_id")
int_lu = site_int.set_index("site_id")
mc_lu  = mc_df.set_index("site_id")

fig = plt.figure(figsize=(20, 10))
fig.patch.set_facecolor("white")
gs  = gridspec.GridSpec(1, 7, figure=fig,
                        width_ratios=[1.2, 1.1, 1.1, 0.25, 1.1, 1.1, 1.2],
                        wspace=0.08)

y        = np.arange(len(ids))
ph_grays = {1: "#aaaaaa", 2: "#555555", 3: "#111111"}

# ── Option A panels (cols 0-2) ───────────────────────────
for col, period in enumerate(PERIOD_LIST):
    ax = fig.add_subplot(gs[col])
    gg_style(ax)
    mc_means = np.array([mc_lu.loc[s, f"{period}_mc_mean"] for s in ids])
    mc_stds  = np.array([mc_lu.loc[s, f"{period}_mc_std"]  for s in ids])
    aor_vals = np.array([aor_lu.loc[s, period]             for s in ids])

    ax.barh(y, mc_means, xerr=mc_stds,
            color=PERIOD_GRAY[period], alpha=0.7, hatch=HATCH[period],
            error_kw=dict(elinewidth=1.2, capsize=3, ecolor="black"),
            label="MC mean ±1σ")
    ax.plot(aor_vals, y, "D", color="black", markersize=6, zorder=4, label="Aoristic")
    ax.set_yticks(y)
    ax.set_yticklabels(ids if col == 0 else [""] * len(ids), fontsize=11)
    ax.set_xlabel("Weight", fontsize=12)
    ax.set_title(f"{period}\n(A)", fontweight="bold", fontsize=12)
    ax.invert_yaxis()
    if col == 0:
        ax.legend(loc="lower right", fontsize=10,
                  facecolor=PANEL_BG, edgecolor="white")

# ── Divider (col 3) ─────────────────────────────────────
ax_div = fig.add_subplot(gs[3])
ax_div.axis("off")
ax_div.plot([0.5, 0.5], [0, 1], color="#cccccc", linewidth=1.5,
            transform=ax_div.transAxes, clip_on=False)
ax_div.text(0.5, 0.5, "vs", ha="center", va="center",
            fontsize=13, color="#888888", transform=ax_div.transAxes)

# ── Option B panels (cols 4-6) ───────────────────────────
for col_offset, period in enumerate(PERIOD_LIST):
    ax = fig.add_subplot(gs[4 + col_offset])
    gg_style(ax)
    mc_means_i = np.array([mc_lu.loc[s, f"{period}_mc_mean_int"] for s in ids])
    mc_stds_i  = np.array([mc_lu.loc[s, f"{period}_mc_std_int"]  for s in ids])
    int_vals   = np.array([int_lu.loc[s, period]                 for s in ids])

    ax.barh(y, mc_means_i, xerr=mc_stds_i,
            color=PERIOD_GRAY[period], alpha=0.7, hatch=HATCH[period],
            error_kw=dict(elinewidth=1.2, capsize=3, ecolor="black"),
            label="MC mean ±1σ")
    ax.plot(int_vals, y, "D", color="black", markersize=6, zorder=4, label="Intensity")
    ax.set_yticks(y)
    ax.set_yticklabels([""] * len(ids))
    ax.set_xlabel("Intensity (wt/yr)", fontsize=12)
    ax.set_title(f"{period}\n(B)", fontweight="bold", fontsize=12)
    ax.invert_yaxis()

    # n_phases annotations on the last B panel only
    if col_offset == 2:
        xlim_right = ax.get_xlim()[1]
        for yi, (ph, sid) in enumerate(zip(
                [int(mc_lu.loc[s, "n_phases"]) for s in ids], ids)):
            ax.text(xlim_right * 1.08, yi,
                    f"{ph}ph", va="center", ha="left",
                    fontsize=10, color=ph_grays.get(ph, "#888"),
                    clip_on=False)
        ax.text(xlim_right * 1.08, -0.8, "phases",
                va="center", ha="left", fontsize=10,
                color="#555555", clip_on=False)

fig.suptitle(
    "Monte Carlo vs Aoristic  |  Option A (absolute) vs Option B (intensity/yr)"
    "\nRoman Villa Sites, South Limburg",
    fontsize=14, y=1.02,
)

ph_patches = [mpatches.Patch(color=ph_grays[k],
                              label=f"{k} phase{'s' if k > 1 else ''}")
              for k in [1, 2, 3]]
fig.legend(handles=ph_patches, loc="lower center",
           ncol=3, fontsize=11, frameon=True,
           facecolor="white", edgecolor="#cccccc",
           bbox_to_anchor=(0.5, -0.04))

plt.savefig(OUTPUT_DIR / "monte_carlo_comparison.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[7/7] monte_carlo_comparison.png saved")

# ══════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════

print(f"\n{'=' * 60}")
print(f"  All outputs saved to: {OUTPUT_DIR}")
print(f"{'=' * 60}")

print("\nOption A - Absolute aoristic weights:")
print(site_aor[["site_id"] + PERIOD_LIST].to_string(index=False))

print("\nOption B - Duration-normalized intensity (weight per year):")
print(site_int[["site_id"] + PERIOD_LIST].round(4).to_string(index=False))

print("\nMonte Carlo - occupation phases:")
print(mc_df[["site_id", "n_phases"]].to_string(index=False))

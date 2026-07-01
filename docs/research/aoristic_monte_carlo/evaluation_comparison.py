"""
Evaluation Comparison: Original Dataset (SGRE) vs ARCHROEN Extraction

Compares aoristic chronological profiles at site-period level (Option A - unweighted).
Produces 5 figures + evaluation metrics printed to console.

Outputs (saved to outputs/)
---------------------------------------------
1. eval_gantt_original.png   - Gantt: SGRE original dataset
2. eval_gantt_archroen.png   - Gantt: ARCHROEN extracted dataset
3. eval_gantt_combined.png   - Gantt: both datasets overlaid per site
4. eval_heatmap.png          - Heatmap: proportional weights, Original (top) + ARCHROEN (bottom)
5. eval_regional_curve.png   - Regional activity curves overlaid, with MC bands (half-A4 sizing)
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════

BASE       = Path(__file__).resolve().parent
ORIG_PATH  = BASE / "data" / "ori_4zl_aori.csv"
ARCH_PATH  = BASE / "data" / "aoristic_dataset.csv"
OUTPUT_DIR = BASE / "outputs"

PERIODS = {
    "Early Roman":  (-12,  70),
    "Middle Roman": ( 71, 275),
    "Late Roman":   (276, 450),
}
PERIOD_LIST = list(PERIODS.keys())
PERIOD_GRAY = {
    "Early Roman":  "#1a1a1a",
    "Middle Roman": "#6b6b6b",
    "Late Roman":   "#b8b8b8",
}
PERIOD_SHORT = {"Early Roman": "Early", "Middle Roman": "Middle", "Late Roman": "Late"}

N_SIM, BIN_SIZE, RANDOM_SEED = 1000, 25, 42
DPI, T_START, T_END          = 300, -12, 450
PANEL_BG                     = "#ebebeb"

plt.rcParams.update({
    "font.family":     "serif",
    "font.size":       13,
    "axes.labelsize":  14,
    "axes.titlesize":  14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
})

def overlap(s, e, ps, pe):
    return max(0.0, min(e, pe) - max(s, ps))

def gg_style(ax):
    ax.set_facecolor(PANEL_BG)
    ax.grid(True, color="white", linewidth=0.8, zorder=0)
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
# AORISTIC FUNCTIONS
# ══════════════════════════════════════════════════════════

def compute_site_aoristic(df):
    """Option A - unweighted: each record contributes weight 1."""
    rows = []
    for _, r in df.iterrows():
        dur = float(r["end_date"]) - float(r["start_date"])
        if dur <= 0:
            continue
        rec = {"site_id": str(r["site_id"])}
        for p, (ps, pe) in PERIODS.items():
            rec[p] = overlap(float(r["start_date"]), float(r["end_date"]), ps, pe) / dur
        rows.append(rec)
    rec_df   = pd.DataFrame(rows)
    site_aor = (rec_df.groupby("site_id")[PERIOD_LIST]
                .sum().reset_index()
                .sort_values("site_id").reset_index(drop=True))
    return site_aor

def normalize_rows(df):
    """Row-normalize so each site's weights sum to 1 (proportional distribution)."""
    result         = df.copy()
    totals         = df[PERIOD_LIST].sum(axis=1)
    result[PERIOD_LIST] = df[PERIOD_LIST].div(totals, axis=0)
    return result

def regional_curve(df):
    curve = np.zeros(n_bins)
    for _, r in df.iterrows():
        dur = float(r["end_date"]) - float(r["start_date"])
        if dur <= 0:
            continue
        for i in range(n_bins):
            ov = overlap(float(r["start_date"]), float(r["end_date"]), bins[i], bins[i + 1])
            curve[i] += ov / dur
    return curve

def mc_regional(df):
    np.random.seed(RANDOM_SEED)
    src       = df[["start_date", "end_date"]].values.astype(float)
    mc_curves = np.zeros((N_SIM, n_bins))
    for sim in range(N_SIM):
        samples = np.random.uniform(src[:, 0], src[:, 1])
        for i in range(n_bins):
            mc_curves[sim, i] = np.sum((samples >= bins[i]) & (samples < bins[i + 1]))
    return (mc_curves.mean(0),
            np.percentile(mc_curves, 5,  0),
            np.percentile(mc_curves, 95, 0))

# ══════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════

orig_df = pd.read_csv(ORIG_PATH)
orig_df["start_date"] = pd.to_numeric(orig_df["start_date"], errors="coerce")
orig_df["end_date"]   = pd.to_numeric(orig_df["end_date"],   errors="coerce")
orig_df["site_id"]    = orig_df["site_id"].astype(str)
orig_df = orig_df.dropna(subset=["start_date", "end_date"]).copy()
orig_df = orig_df[orig_df["end_date"] > orig_df["start_date"]].copy()

arch_df = pd.read_csv(ARCH_PATH)
arch_df["start_date"] = pd.to_numeric(arch_df["start_date"], errors="coerce")
arch_df["end_date"]   = pd.to_numeric(arch_df["end_date"],   errors="coerce")
arch_df["site_id"]    = arch_df["site_id"].astype(str)
arch_df = arch_df.dropna(subset=["start_date", "end_date"]).copy()
arch_df = arch_df[arch_df["end_date"] > arch_df["start_date"]].copy()

print(f"Original : {len(orig_df)} records | {orig_df['site_id'].nunique()} sites")
print(f"ARCHROEN : {len(arch_df)} records | {arch_df['site_id'].nunique()} sites")

# Site labels (Name-Toponym) from original dataset
_lu = orig_df.groupby("site_id")[["site_name", "toponym"]].first().reset_index()
site_label = {r["site_id"]: f"{r['site_name']}-{r['toponym']}" for _, r in _lu.iterrows()}

# ══════════════════════════════════════════════════════════
# AORISTIC COMPUTATION
# ══════════════════════════════════════════════════════════

orig_aor   = compute_site_aoristic(orig_df)
arch_aor   = compute_site_aoristic(arch_df)

common_ids = sorted(set(orig_aor["site_id"]) & set(arch_aor["site_id"]))
orig_aor   = orig_aor[orig_aor["site_id"].isin(common_ids)].sort_values("site_id").reset_index(drop=True)
arch_aor   = arch_aor[arch_aor["site_id"].isin(common_ids)].sort_values("site_id").reset_index(drop=True)

orig_norm  = normalize_rows(orig_aor)
arch_norm  = normalize_rows(arch_aor)

labels = [site_label.get(sid, sid) for sid in common_ids]
n      = len(common_ids)

print(f"Common sites     : {n}")

# ══════════════════════════════════════════════════════════
# EVALUATION METRICS
# ══════════════════════════════════════════════════════════

orig_flat = orig_norm[PERIOD_LIST].values.flatten()
arch_flat = arch_norm[PERIOD_LIST].values.flatten()

def spearman_r(x, y):
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    n  = len(x)
    return 1 - 6 * ((rx - ry) ** 2).sum() / (n * (n ** 2 - 1))

sp        = spearman_r(orig_flat, arch_flat)
pe        = float(np.corrcoef(orig_flat, arch_flat)[0, 1])
orig_dom  = orig_norm[PERIOD_LIST].idxmax(axis=1)
arch_dom  = arch_norm[PERIOD_LIST].idxmax(axis=1)
dom_agree = float((orig_dom.values == arch_dom.values).mean())
mad       = float(np.abs(orig_norm[PERIOD_LIST].values - arch_norm[PERIOD_LIST].values).mean())

print(f"\n{'=' * 55}")
print(f"  Evaluation Metrics (site-period proportions)")
print(f"{'=' * 55}")
print(f"  Spearman r               : {sp:.3f}")
print(f"  Pearson  r               : {pe:.3f}")
print(f"  Dominant period agreement: {dom_agree * 100:.1f}%  ({int(dom_agree*n)}/{n} sites)")
print(f"  Mean absolute difference : {mad:.3f}")
print(f"{'=' * 55}")

per_site = []
for sid, lbl in zip(common_ids, labels):
    o = orig_norm[orig_norm["site_id"] == sid][PERIOD_LIST].iloc[0]
    a = arch_norm[arch_norm["site_id"] == sid][PERIOD_LIST].iloc[0]
    per_site.append({
        "site_id": sid, "site": lbl,
        "orig_dominant": o.idxmax(), "arch_dominant": a.idxmax(),
        "dominant_match": o.idxmax() == a.idxmax(),
        **{f"orig_{p}": round(float(o[p]), 3) for p in PERIOD_LIST},
        **{f"arch_{p}": round(float(a[p]), 3) for p in PERIOD_LIST},
        **{f"diff_{p}": round(float(a[p] - o[p]), 3) for p in PERIOD_LIST},
    })
pd.DataFrame(per_site).to_csv(OUTPUT_DIR / "eval_metrics_per_site.csv", index=False)
print("\neval_metrics_per_site.csv saved")

# ══════════════════════════════════════════════════════════
# REGIONAL CURVES + MC
# ══════════════════════════════════════════════════════════

bins   = np.arange(T_START, T_END + BIN_SIZE, BIN_SIZE)
bin_c  = (bins[:-1] + bins[1:]) / 2
n_bins = len(bins) - 1

print("\nComputing regional curves + MC...", end=" ", flush=True)
orig_curve            = regional_curve(orig_df)
arch_curve            = regional_curve(arch_df)
orig_mc_m, orig_p5, orig_p95 = mc_regional(orig_df)
arch_mc_m, arch_p5, arch_p95 = mc_regional(arch_df)
print("done.")

# Normalize to proportion-of-total for fair cross-dataset comparison
ot = orig_curve.sum()
at = arch_curve.sum()
orig_cn, orig_mc_mn, orig_p5n, orig_p95n = [a / ot for a in (orig_curve, orig_mc_m, orig_p5, orig_p95)]
arch_cn, arch_mc_mn, arch_p5n, arch_p95n = [a / at for a in (arch_curve, arch_mc_m, arch_p5, arch_p95)]

# ══════════════════════════════════════════════════════════
# GANTT HELPER
# ══════════════════════════════════════════════════════════

orig_norm_lu = orig_norm.set_index("site_id")
arch_norm_lu = arch_norm.set_index("site_id")

def draw_gantt(norm_lu, ids, ylabels, title, ax, hatch=""):
    for p, (ps, pe) in PERIODS.items():
        ax.axvline(ps, color="#cccccc", linewidth=1.0, zorder=1)
    ax.axvline(T_END, color="#cccccc", linewidth=1.0, zorder=1)
    ax.axvline(0, color="#999999", linewidth=1.0, linestyle="--", zorder=1)

    for i, sid in enumerate(ids):
        if sid not in norm_lu.index:
            continue
        for p in PERIOD_LIST:
            ps, pe = PERIODS[p]
            w = float(norm_lu.loc[sid, p])
            if w > 0.01:
                ax.barh(i, pe - ps, left=ps, height=0.65,
                        color=PERIOD_GRAY[p], alpha=max(0.18, w),
                        hatch=hatch, edgecolor="white", linewidth=0.3, zorder=2)

    ax.set_yticks(range(len(ids)))
    ax.set_yticklabels(ylabels, fontsize=11)
    ax.set_xlim(T_START, T_END)
    ax.invert_yaxis()
    ax.set_xlabel("Year (CE; negative = BCE)")
    ax.set_title(title)

    for p, (ps, pe) in PERIODS.items():
        ax.text((ps + pe) / 2, -0.8, PERIOD_SHORT[p],
                ha="center", va="top", fontsize=11,
                color="#333333", fontstyle="italic")
    clean_style(ax)

period_patches = [mpatches.Patch(color=PERIOD_GRAY[p], label=p) for p in PERIOD_LIST]

# ══════════════════════════════════════════════════════════
# FIGURE 1 - Gantt: Original
# ══════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(13, 9))
fig.patch.set_facecolor("white")
draw_gantt(orig_norm_lu, common_ids, labels,
           "Chronological Timeline - Original Dataset (SGRE)", ax)
ax.legend(handles=period_patches, loc="upper center",
          bbox_to_anchor=(0.5, -0.08), ncol=3,
          frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=12)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "eval_gantt_original.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("\n[1/5] eval_gantt_original.png saved")

# ══════════════════════════════════════════════════════════
# FIGURE 2 - Gantt: ARCHROEN
# ══════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(13, 9))
fig.patch.set_facecolor("white")
draw_gantt(arch_norm_lu, common_ids, labels,
           "Chronological Timeline - ARCHROEN Extraction", ax)
ax.legend(handles=period_patches, loc="upper center",
          bbox_to_anchor=(0.5, -0.08), ncol=3,
          frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=12)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "eval_gantt_archroen.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[2/5] eval_gantt_archroen.png saved")

# ══════════════════════════════════════════════════════════
# FIGURE 3 - Gantt: Combined
# ══════════════════════════════════════════════════════════

ROW_H = 0.38
GAP   = 0.08
STEP  = 1.8

fig, ax = plt.subplots(figsize=(13, 13))
fig.patch.set_facecolor("white")

for p, (ps, pe) in PERIODS.items():
    ax.axvline(ps, color="#cccccc", linewidth=1.0, zorder=1)
ax.axvline(T_END, color="#cccccc", linewidth=1.0, zorder=1)
ax.axvline(0,     color="#999999", linewidth=1.0, linestyle="--", zorder=1)

y_ticks, y_labels = [], []
for i, (sid, lbl) in enumerate(zip(common_ids, labels)):
    y_o = i * STEP
    y_a = i * STEP + ROW_H + GAP

    for p in PERIOD_LIST:
        ps, pe = PERIODS[p]
        w_o = float(orig_norm_lu.loc[sid, p]) if sid in orig_norm_lu.index else 0
        if w_o > 0.01:
            ax.barh(y_o, pe - ps, left=ps, height=ROW_H,
                    color=PERIOD_GRAY[p], alpha=max(0.18, w_o),
                    edgecolor="white", linewidth=0.3, zorder=2)
        w_a = float(arch_norm_lu.loc[sid, p]) if sid in arch_norm_lu.index else 0
        if w_a > 0.01:
            ax.barh(y_a, pe - ps, left=ps, height=ROW_H,
                    color=PERIOD_GRAY[p], alpha=max(0.18, w_a),
                    hatch="//", edgecolor="white", linewidth=0.3, zorder=2)

    # Separator line between site groups
    if i < n - 1:
        ax.axhline(i * STEP + ROW_H * 2 + GAP + 0.2,
                   color="#eeeeee", linewidth=0.6, zorder=0)

    y_ticks.append(i * STEP + ROW_H + GAP / 2)
    y_labels.append(lbl)

ax.set_yticks(y_ticks)
ax.set_yticklabels(y_labels, fontsize=11)
ax.set_xlim(T_START, T_END)
ax.invert_yaxis()
ax.set_xlabel("Year (CE; negative = BCE)")
ax.set_title("Chronological Timeline - SGRE vs ARCHROEN\n"
             "(upper bar = SGRE original  |  lower bar = ARCHROEN  |  opacity = proportional weight)")

for p, (ps, pe) in PERIODS.items():
    ax.text((ps + pe) / 2, -0.6, PERIOD_SHORT[p],
            ha="center", va="top", fontsize=11,
            color="#333333", fontstyle="italic")

clean_style(ax)

orig_patch = mpatches.Patch(facecolor="#888888", edgecolor="white",
                             label="SGRE (original) - solid")
arch_patch = mpatches.Patch(facecolor="#888888", hatch="//", edgecolor="white",
                             label="ARCHROEN - hatched")
ax.legend(handles=period_patches + [orig_patch, arch_patch],
          loc="upper center", bbox_to_anchor=(0.5, -0.05),
          ncol=5, frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=11)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "eval_gantt_combined.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[3/5] eval_gantt_combined.png saved")

# ══════════════════════════════════════════════════════════
# FIGURE 4 - Heatmap: Original (top) + ARCHROEN (bottom)
# ══════════════════════════════════════════════════════════

fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(10, 20))
fig.patch.set_facecolor("white")

for ax, norm_df, subtitle, show_x in [
    (ax_top, orig_norm, "SGRE - Original Dataset",    False),
    (ax_bot, arch_norm, "ARCHROEN - Extracted Dataset",  True),
]:
    heat = norm_df.set_index("site_id")[PERIOD_LIST].copy()
    heat.index = [site_label.get(sid, sid) for sid in heat.index]
    sns.heatmap(
        heat, annot=True, fmt=".2f",
        annot_kws={"size": 12},
        cmap="Greys", linewidths=0.5, linecolor="white",
        vmin=0, vmax=1, ax=ax,
        cbar_kws={"label": "Proportion", "shrink": 0.4,
                  "orientation": "horizontal", "pad": 0.03},
        xticklabels=show_x,
    )
    ax.set_title(subtitle, fontsize=13, pad=12)
    ax.set_xlabel("")
    ax.set_ylabel("Site")
    ax.tick_params(axis="y", labelsize=12)
    if show_x:
        ax.tick_params(axis="x", labelsize=12)

fig.suptitle(
    "Proportional Aoristic Weights per Period\nSGRE vs ARCHROEN - South Limburg",
    fontsize=14, y=1.01,
)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "eval_heatmap.png", dpi=DPI, bbox_inches="tight")
plt.close()
print("[4/5] eval_heatmap.png saved")

# ══════════════════════════════════════════════════════════
# FIGURE 5 - Regional curve: both overlaid (half-A4 sizing)
# ══════════════════════════════════════════════════════════

_RC = {
    "font.size": 16, "axes.labelsize": 16, "axes.titlesize": 14,
    "xtick.labelsize": 14, "ytick.labelsize": 14,
}
with plt.rc_context(_RC):
    fig, ax = plt.subplots(figsize=(5.5, 5))
    fig.patch.set_facecolor("white")
    gg_style(ax)

    ax.fill_between(bin_c, orig_p5n, orig_p95n,
                    color="#333333", alpha=0.18,
                    label="SGRE MC 5-95th pct", zorder=1)
    ax.step(bin_c, orig_cn, where="mid", color="black",
            linewidth=2.0, linestyle="-", label="SGRE (original)", zorder=3)

    ax.fill_between(bin_c, arch_p5n, arch_p95n,
                    color="#999999", alpha=0.30,
                    label="ARCHROEN MC 5-95th pct", zorder=1)
    ax.step(bin_c, arch_cn, where="mid", color="#555555",
            linewidth=2.0, linestyle="--", label="ARCHROEN", zorder=3)

    for p, (ps, pe) in PERIODS.items():
        ax.axvline(ps, color="white", linewidth=1.0, zorder=2)
    ax.axvline(0, color="#888888", linewidth=0.9, linestyle=":", zorder=2)

    ylim_top = ax.get_ylim()[1]
    for p, (ps, pe) in PERIODS.items():
        ax.text((ps + pe) / 2, ylim_top * 0.96, PERIOD_SHORT[p],
                ha="center", va="top", fontsize=12,
                color="#333333", fontstyle="italic")

    ax.set_xlim(T_START, T_END)
    ax.set_xlabel("Year (CE; negative = BCE)")
    ax.set_ylabel("Proportion of total activity\n(normalized, 25-yr bins)")
    ax.set_title("Regional Activity - SGRE vs ARCHROEN", loc="left", fontsize=13)

    handles, leg_labels = ax.get_legend_handles_labels()
    fig.legend(handles, leg_labels, loc="lower center", bbox_to_anchor=(0.5, 0.0),
               ncol=2, frameon=True, facecolor=PANEL_BG, edgecolor="white", fontsize=11)

    plt.tight_layout(rect=[0, 0.20, 1, 0.97])
    plt.savefig(OUTPUT_DIR / "eval_regional_curve.png", dpi=DPI, bbox_inches="tight")
    plt.close()
print("[5/5] eval_regional_curve.png saved")

print(f"\nAll evaluation outputs saved to: {OUTPUT_DIR}")
print(f"\nPer-site summary:")
for r in per_site:
    match = "OK" if r["dominant_match"] else "!!"
    print(f"  [{match}] {r['site']:<35}  Orig={r['orig_dominant']:<15}  ARCH={r['arch_dominant']}")

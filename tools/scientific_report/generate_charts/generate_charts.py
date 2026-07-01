#!/usr/bin/env python3
"""Generate the evaluation figures from granular evaluation summaries.

This script is intentionally SELF-CONTAINED: it copies the small set of helpers it needs
(font setup, palette, summary loading, statistics, figure helpers) so it has no dependency on
any other chart script. It NEVER regenerates the granular_detail.csv / granular_summary.csv
files — it only reads existing summaries.

It reads three granular_summary.csv files (one each for Rules-only, Claude and Llama — all
required, passed via --rules_only / --claude / --llama) and writes the charts into a
"charts_output" folder (default: <script_dir>/charts_output/; override with --output-dir):

  1. Overall Correctness by Workflow Mode            (Rules-only vs Claude vs Llama)
  2. Extraction Performance by Source Type - Claude  (4 verdicts per source type)
  3. Extraction Performance by Source Type - Llama    (4 verdicts per source type)
  4. Correctness by Source Type - Claude vs Llama
  5. Extraction Performance by Field - Claude         (4 verdicts per field)
  6. Extraction Performance by Field - Llama          (4 verdicts per field)
  7. Per-Report Correctness Distribution - Claude vs Llama

Every text element uses Times New Roman. Verdicts = Correct / Incorrect / Missing / Overclaim
(Correct = Exact + Acceptable). Source types = New / Old / OCR / Table reports.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.transforms import offset_copy
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Fonts and style
# ---------------------------------------------------------------------------

FONT_SIZE = 12
BACKGROUND_COLOR = "#ffffff"

# --- True on-page typography ----------------------------------------------------------------
# The charts are placed at a fixed image width (the A4 text column:
# 1-inch margins -> ~15.9 cm -> 6.3 in). Page font (pt) = matplotlib font (pt) x (display / figwidth).
# By setting every figure's WIDTH equal to the display width, that ratio is exactly 1, so the
# matplotlib FONT_SIZE (12) renders as a true 12 pt on the page. Heights vary per chart; only the
# width is pinned. Export at 300 DPI. (This requires saving WITHOUT bbox_inches="tight", which would
# trim the width and break the 1:1 ratio — see save_figure.)
DISPLAY_WIDTH_IN = 6.3   # 16 cm text column = the width each PNG is placed at in Docs
EXPORT_DPI = 300
TITLE_PT = FONT_SIZE + 2         # 14 pt title (proportional to the 12 pt body)
BAR_LABEL_PT = FONT_SIZE         # 12 pt for the simple charts (1, 4, 7)
GROUPED_BAR_LABEL_PT = 8         # smaller + rotated for the dense 4-verdict grouped charts (2/3/5/6)

# Fonts are resolved gracefully so the script always runs (no setup required). It prefers a real
# "Times New Roman" if the operating system has one, then the bundled Liberation Serif (a freely
# licensed, metrically identical Times look-alike shipped in ./fonts/), then any other Times-like
# serif, and finally Matplotlib's built-in DejaVu Serif. It never errors over fonts.
FONT_DIR = Path(__file__).resolve().parent / "fonts"
# In preference order; the first one Matplotlib can see is used.
FONT_PREFERENCE = ["Times New Roman", "Liberation Serif", "Tinos", "Nimbus Roman", "DejaVu Serif"]


def resolve_serif_font() -> str:
    """Register the bundled fonts and return the best available serif family (never raises)."""
    # Register every bundled .ttf so Liberation Serif works even if it is not OS-installed.
    if FONT_DIR.is_dir():
        for ttf in FONT_DIR.glob("*.ttf"):
            try:
                font_manager.fontManager.addfont(str(ttf))
            except Exception:
                pass
    installed = {fe.name.casefold(): fe.name for fe in font_manager.fontManager.ttflist}
    for family in FONT_PREFERENCE:
        if family.casefold() in installed:
            chosen = installed[family.casefold()]
            if family == "Times New Roman" or family == "Liberation Serif":
                print(f"[fonts] using {chosen}.")
            else:
                print(f"[fonts] note: Times New Roman / Liberation Serif not found; "
                      f"using the serif fallback '{chosen}'. Charts still render fine.")
            return chosen
    # Should be unreachable (DejaVu Serif ships with Matplotlib), but degrade gracefully.
    print("[fonts] warning: no preferred serif font found; using Matplotlib's default.")
    return "serif"


SELECTED_FONT_FAMILY = resolve_serif_font()
plt.rcParams.update(
    {
        "font.family": SELECTED_FONT_FAMILY,
        "font.size": FONT_SIZE,
        "axes.titlesize": FONT_SIZE,
        "axes.labelsize": FONT_SIZE,
        "xtick.labelsize": FONT_SIZE,
        "ytick.labelsize": FONT_SIZE,
        "legend.fontsize": FONT_SIZE,
    }
)
STYLE_SUFFIX = "grayscale"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Column prefixes in granular_summary.csv, in chart order.
FIELD_ORDER = ["site_name", "pottery", "typology", "start_date", "end_date"]

# X-axis labels for the field charts — exactly the gold-CSV column names (user request).
FIELD_LABELS = {
    "site_name": "site_name",
    "pottery": "pot_name",
    "typology": "typology",
    "start_date": "start_date",
    "end_date": "end_date",
}

REPORT_TYPE_ORDER = ["New reports", "Old reports", "OCR reports", "Tables"]

SUFFIX_TO_VERDICT = {
    "exact": "Exact match",
    "acceptable": "Acceptable match",
    "incorrect": "Incorrect value",
    "missing": "Missing value",
    "overclaim": "Overclaim",
}
VERDICT_ORDER = [
    "Exact match",
    "Acceptable match",
    "Incorrect value",
    "Missing value",
    "Overclaim",
]
# Grouped four-verdict categories (Correct = Exact + Acceptable).
GROUP_ORDER = ["Correct", "Incorrect", "Missing", "Overclaim"]

# Grayscale styles: (facecolor, hatch). Hatches add print-safe separation between shades.
VERDICT_STYLE = {
    "Correct": ("#303030", ""),
    "Incorrect": ("#7a7a7a", "///"),
    "Missing": ("#aeaeae", "..."),
    "Overclaim": ("#d8d8d8", "xxx"),
}
MODE_STYLE = {
    "Rules-only": ("#c4c4c4", "..."),
    "Claude": ("#303030", ""),
    "Llama": ("#9a9a9a", "///"),
}


# ---------------------------------------------------------------------------
# Loading and statistics
# ---------------------------------------------------------------------------

def load_granular_summary(path: Path) -> pd.DataFrame:
    """Load one granular_summary.csv into a (Field, Verdict) count table; drop the TOTAL row."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    raw = pd.read_csv(path)
    if "report" not in raw.columns:
        raise ValueError(f"{path.name} is missing the 'report' column.")
    raw = raw[raw["report"].astype(str).str.upper().str.strip() != "TOTAL"].copy()
    raw["report"] = raw["report"].astype(str).str.strip()
    raw = raw.set_index("report")

    data: dict[tuple[str, str], pd.Series] = {}
    for field in FIELD_ORDER:
        for suffix, verdict in SUFFIX_TO_VERDICT.items():
            column = f"{field}_{suffix}"
            if column not in raw.columns:
                raise ValueError(f"{path.name} is missing required column: {column}")
            values = pd.to_numeric(raw[column], errors="coerce").fillna(0)
            data[(field, verdict)] = values.round().astype(int)

    counts = pd.DataFrame(data)
    counts.columns = pd.MultiIndex.from_tuples(counts.columns, names=["Field", "Verdict"])
    counts.index = raw.index
    return counts


def infer_report_type(report_name: str) -> str:
    """Infer the source-type category from a report identifier."""
    name = report_name.upper().strip()
    if name.startswith("NEW"):
        return "New reports"
    if name.startswith("OLD"):
        return "Old reports"
    if name.startswith("OCR"):
        return "OCR reports"
    if name.startswith("TABLE"):
        return "Tables"
    return "Other"


def empty_verdict_table(index: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame(0, index=list(index), columns=VERDICT_ORDER, dtype=int)


def to_group_counts(counts: pd.DataFrame) -> pd.DataFrame:
    """Collapse the five verdicts into the four grouped categories."""
    grouped = pd.DataFrame(index=counts.index)
    grouped["Correct"] = counts["Exact match"] + counts["Acceptable match"]
    grouped["Incorrect"] = counts["Incorrect value"]
    grouped["Missing"] = counts["Missing value"]
    grouped["Overclaim"] = counts["Overclaim"]
    return grouped


def calculate_statistics(df: pd.DataFrame) -> dict:
    """Return overall (Series), by_report_type and by_field verdict tables for one mode."""
    fields = [f for f in FIELD_ORDER if f in df.columns.get_level_values("Field")]

    overall = pd.Series(0, index=VERDICT_ORDER, dtype=int)
    for verdict in VERDICT_ORDER:
        overall[verdict] = int(sum(df[(f, verdict)].sum() for f in fields))

    report_types = pd.Series([infer_report_type(n) for n in df.index], index=df.index)
    by_report_type = empty_verdict_table(REPORT_TYPE_ORDER)
    for rtype in REPORT_TYPE_ORDER:
        rows = df.loc[report_types == rtype]
        if rows.empty:
            continue
        for verdict in VERDICT_ORDER:
            by_report_type.loc[rtype, verdict] = int(sum(rows[(f, verdict)].sum() for f in fields))
    by_report_type = by_report_type.loc[by_report_type.sum(axis=1) > 0]

    by_field = empty_verdict_table([FIELD_LABELS[f] for f in fields])
    for field in fields:
        for verdict in VERDICT_ORDER:
            by_field.loc[FIELD_LABELS[field], verdict] = int(df[(field, verdict)].sum())

    return {"overall": overall, "by_report_type": by_report_type, "by_field": by_field}


def accepted_performance(counts: pd.DataFrame) -> pd.Series:
    """Row-wise accepted performance (Exact + Acceptable) as a percentage of the row total."""
    totals = counts[VERDICT_ORDER].sum(axis=1)
    correct = counts["Exact match"] + counts["Acceptable match"]
    return (correct / totals.replace(0, np.nan) * 100).fillna(0)


def report_level_accepted(df: pd.DataFrame) -> np.ndarray:
    """Per-report accepted performance (Exact + Acceptable) across all fields."""
    fields = [f for f in FIELD_ORDER if f in df.columns.get_level_values("Field")]
    per_report = empty_verdict_table(df.index)
    for name in df.index:
        for verdict in VERDICT_ORDER:
            per_report.loc[name, verdict] = int(sum(df.loc[name, (f, verdict)] for f in fields))
    rates = accepted_performance(per_report)
    totals = per_report[VERDICT_ORDER].sum(axis=1)
    return rates.loc[totals > 0].to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------

def make_figure(title: str, height: float):
    # Width is pinned to the display width so matplotlib pt == on-page pt (see DISPLAY_WIDTH_IN).
    fig, ax = plt.subplots(figsize=(DISPLAY_WIDTH_IN, height), facecolor=BACKGROUND_COLOR)
    ax.set_facecolor(BACKGROUND_COLOR)
    fig.suptitle(title, fontsize=TITLE_PT, fontweight="bold", y=0.985, color="#111111")
    # No subtitle (removed); generous bottom room so the x-axis label clears the canvas-pinned
    # horizontal legend below it. Margins are set manually (not bbox_inches="tight") so the saved
    # width stays exactly 6.3 in.
    fig.subplots_adjust(top=0.88, bottom=0.27, left=0.135, right=0.975)
    return fig, ax


def style_axis(ax) -> None:
    ax.grid(axis="y", linestyle="--", linewidth=0.7, color="#8a8a8a", alpha=0.45)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#555555")
    ax.tick_params(colors="#222222")


def label_bars(ax, bars, fontsize: int = BAR_LABEL_PT, label_zeros: bool = False,
               rotation: float = 0.0, y_offset=0.0, ha: str = "center",
               x_shift_pts: float = 0.0) -> None:
    # y_offset may be a scalar (same lift for every bar) or one value per bar (for staggering).
    offsets = y_offset if np.ndim(y_offset) else [y_offset] * len(bars)
    # x_shift_pts nudges labels horizontally by a fixed amount in points (dpi-independent), used to
    # re-centre the left-anchored tilted labels over their bars. 1 pt ≈ 4.17 px at 300 DPI.
    text_transform = ax.transData
    if x_shift_pts:
        text_transform = offset_copy(ax.transData, fig=ax.figure, x=x_shift_pts, y=0, units="points")
    for bar, off in zip(bars, offsets):
        height = float(bar.get_height())
        if not np.isfinite(height):
            continue
        if height < 0.05 and not label_zeros:   # skip near-zero unless we explicitly label 0.0%
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + 1.2 + float(off),
            f"{height:.1f}%",
            ha=ha, va="bottom", fontsize=fontsize, fontweight="bold", color="#222222",
            rotation=rotation, rotation_mode="anchor", transform=text_transform,
        )


def color_legend(ax, items, legend_title: str, ncol: int = None) -> None:
    """Horizontal colored-square legend centered along the BOTTOM of the figure canvas.

    Anchored in figure coordinates (not axes coordinates) so it is always pinned just above the
    canvas bottom and never clipped — important now that we save without bbox_inches="tight".
    """
    handles = [
        Patch(facecolor=color, edgecolor="#333333", hatch=hatch, label=label)
        for label, color, hatch in items
    ]
    ax.legend(handles=handles, title=legend_title, frameon=False, loc="lower center",
              bbox_to_anchor=(0.5, 0.012), bbox_transform=ax.figure.transFigure,
              ncol=ncol or len(items))


def save_figure(fig, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # No bbox_inches="tight": it would trim the canvas and change the saved width, breaking the
    # figwidth == display-width identity that makes the on-page font a true 12 pt. Margins are
    # handled in make_figure instead. Export at 300 DPI.
    fig.savefig(output_path, dpi=EXPORT_DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(output_path.resolve())


# ---------------------------------------------------------------------------
# The evaluation charts
# ---------------------------------------------------------------------------

def chart_overall_by_mode(all_stats: dict, modes: list[str], output_path: Path) -> None:
    """1. Overall Correctness by Workflow Mode (Rules-only vs Claude vs Llama)."""
    values = []
    for mode in modes:
        overall = all_stats[mode]["overall"]
        total = float(overall.sum())
        correct = float(overall["Exact match"] + overall["Acceptable match"])
        values.append(correct / total * 100 if total else 0.0)

    fig, ax = make_figure("Overall Correctness by Workflow Mode", height=4.3)
    fig.subplots_adjust(bottom=0.10)   # no legend: the x-axis already names each mode
    x = np.arange(len(modes), dtype=float)
    bars = []
    for i, mode in enumerate(modes):
        color, hatch = MODE_STYLE[mode]
        bars.extend(
            ax.bar(x[i], values[i], 0.55, color=color, edgecolor="#333333",
                   linewidth=0.6, hatch=hatch)
        )
    label_bars(ax, bars)
    ax.set_xticks(x)
    ax.set_xticklabels(modes)
    ax.set_ylabel("Correct performance (Exact + Acceptable)")
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100))
    style_axis(ax)
    save_figure(fig, output_path)


def chart_verdicts_grouped(by_table: pd.DataFrame, x_order: list[str],
                           title: str, output_path: Path) -> None:
    """2/3/5/6. Four verdicts (Correct/Incorrect/Missing/Overclaim) per category (single mode)."""
    grouped = to_group_counts(by_table).reindex(x_order).fillna(0)
    grouped = grouped.loc[grouped.sum(axis=1) > 0]
    x_order = list(grouped.index)
    totals = grouped.sum(axis=1)
    pct = grouped.div(totals.replace(0, np.nan), axis=0).fillna(0) * 100

    fig, ax = make_figure(title, height=4.8)
    x = np.arange(len(x_order), dtype=float)
    width = 0.20

    for i, verdict in enumerate(GROUP_ORDER):
        color, hatch = VERDICT_STYLE[verdict]
        bars = ax.bar(
            x + (i - 1.5) * width, pct[verdict].to_numpy(dtype=float), width,
            color=color, edgecolor="#333333", linewidth=0.5, hatch=hatch,
        )
        # Label every bar, INCLUDING 0.0% — a flat zero has no visible bar, so the label is the
        # only thing that distinguishes "0%" from a missing value. At a true 12 pt the four bars
        # per group sit closer than a horizontal label is wide, so labels are tilted 45° (anchored
        # at the bar, fanning up-right) to keep adjacent ones from overlapping.
        label_bars(ax, bars, fontsize=GROUPED_BAR_LABEL_PT, label_zeros=True,
                   rotation=45, ha="left", x_shift_pts=-3.6)   # ~15 px left, to re-centre
    ax.set_xticks(x)
    ax.set_xticklabels(x_order)
    ax.set_ylabel("Share of evaluated values")
    ax.set_ylim(0, 116)   # headroom for the tilted labels above the tall "Correct" bars
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100))
    color_legend(ax, [(v, *VERDICT_STYLE[v]) for v in GROUP_ORDER], "Verdict")
    style_axis(ax)
    save_figure(fig, output_path)


def chart_correct_by_source(all_stats: dict, modes: list[str], output_path: Path) -> None:
    """4. Correctness (Exact + Acceptable) per source type, Claude vs Llama."""
    present = [
        t for t in REPORT_TYPE_ORDER
        if any(t in all_stats[m]["by_report_type"].index for m in modes)
    ]
    fig, ax = make_figure("Correctness by Source Type - Claude vs Llama", height=4.5)
    x = np.arange(len(present), dtype=float)
    width = 0.38
    for i, mode in enumerate(modes):
        frame = all_stats[mode]["by_report_type"]
        rates = accepted_performance(frame).reindex(present).fillna(0)
        color, hatch = MODE_STYLE[mode]
        bars = ax.bar(
            x + (i - 0.5) * width, rates.to_numpy(dtype=float), width,
            color=color, edgecolor="#333333", linewidth=0.5, hatch=hatch,
        )
        label_bars(ax, bars)
    ax.set_xticks(x)
    ax.set_xticklabels(present)
    ax.set_ylabel("Correct performance (Exact + Acceptable)")  # source type is named in the title
    ax.set_ylim(0, 108)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100))
    color_legend(ax, [(m, *MODE_STYLE[m]) for m in modes], "Workflow mode")
    style_axis(ax)
    save_figure(fig, output_path)


def chart_report_distribution(raw_dfs: dict, modes: list[str], output_path: Path) -> None:
    """7. Per-report correctness distribution, Claude vs Llama (box + jittered points)."""
    distributions = [report_level_accepted(raw_dfs[m]) for m in modes]

    fig, ax = make_figure("Per-Report Correctness Distribution - Claude vs Llama", height=4.6)
    # Reserve canvas on the right for the "Median xx.x%" labels that sit beside the boxes; no legend
    # (the x-axis already names each mode), so the bottom band can be tightened to the x-axis label.
    fig.subplots_adjust(right=0.80, bottom=0.12)
    positions = np.arange(1, len(modes) + 1, dtype=float)
    box = ax.boxplot(
        distributions, positions=positions, widths=0.45, patch_artist=True, showfliers=False,
        medianprops={"color": "#111111", "linewidth": 2.0},
        whiskerprops={"color": "#333333"}, capprops={"color": "#333333"},
        boxprops={"edgecolor": "#333333", "linewidth": 0.8},
    )
    for i, patch in enumerate(box["boxes"]):
        color, hatch = MODE_STYLE[modes[i]]
        patch.set_facecolor(color)
        patch.set_hatch(hatch)
        patch.set_alpha(0.72)

    rng = np.random.default_rng(42)
    for i, values in enumerate(distributions):
        jitter = rng.uniform(-0.10, 0.10, size=len(values))
        color, _ = MODE_STYLE[modes[i]]
        ax.scatter(
            np.full(len(values), positions[i]) + jitter, values,
            s=38, color=color, edgecolor="#222222", linewidth=0.45, alpha=0.85, zorder=3,
            clip_on=False,   # draw markers fully even when a point sits right at 0%
        )
        if len(values):
            median = float(np.median(values))
            ax.text(positions[i] + 0.30, median, f"Median {median:.1f}%", ha="left",
                    va="center", fontsize=FONT_SIZE, fontweight="bold", color="#222222")

    ax.set_xlim(0.5, len(modes) + 0.5)   # keep boxes centered; median labels spill into the margin
    ax.set_xticks(positions)
    ax.set_xticklabels(modes)
    ax.set_xlabel("Workflow mode")
    ax.set_ylabel("Correct performance per report")
    ax.set_ylim(-4, 105)   # a touch below 0 so a marker sitting at 0% shows its full circle
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100))
    style_axis(ax)
    save_figure(fig, output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Generate the evaluation figures from granular summaries.")
    p.add_argument("--claude", type=Path, required=True,
                   help="Path to the Claude granular_summary.csv (required).")
    p.add_argument("--llama", type=Path, required=True,
                   help="Path to the Llama granular_summary.csv (required).")
    p.add_argument("--rules_only", type=Path, required=True,
                   help="Path to the Rules-only granular_summary.csv (required; used by chart 1).")
    p.add_argument("--output-dir", type=Path, default=script_dir / "charts_output",
                   help="Folder for the generated chart PNGs (default: <script_dir>/charts_output/).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rules_df = load_granular_summary(args.rules_only)
        claude_df = load_granular_summary(args.claude)
        llama_df = load_granular_summary(args.llama)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    all_stats = {
        "Rules-only": calculate_statistics(rules_df),
        "Claude": calculate_statistics(claude_df),
        "Llama": calculate_statistics(llama_df),
    }
    raw_dfs = {"Claude": claude_df, "Llama": llama_df}

    out = args.output_dir
    print("Writing charts to:", out.resolve())

    chart_overall_by_mode(all_stats, ["Rules-only", "Claude", "Llama"],
                          out / f"1_overall_correctness_by_mode_{STYLE_SUFFIX}.png")
    chart_verdicts_grouped(all_stats["Claude"]["by_report_type"], REPORT_TYPE_ORDER,
                           "Extraction Performance by Source Type - Claude",
                           out / f"2_performance_by_source_type_claude_{STYLE_SUFFIX}.png")
    chart_verdicts_grouped(all_stats["Llama"]["by_report_type"], REPORT_TYPE_ORDER,
                           "Extraction Performance by Source Type - Llama",
                           out / f"3_performance_by_source_type_llama_{STYLE_SUFFIX}.png")
    chart_correct_by_source(all_stats, ["Claude", "Llama"],
                            out / f"4_correctness_by_source_type_claude_vs_llama_{STYLE_SUFFIX}.png")
    field_order = [FIELD_LABELS[f] for f in FIELD_ORDER]
    chart_verdicts_grouped(all_stats["Claude"]["by_field"], field_order,
                           "Extraction Performance by Field - Claude",
                           out / f"5_performance_by_field_claude_{STYLE_SUFFIX}.png")
    chart_verdicts_grouped(all_stats["Llama"]["by_field"], field_order,
                           "Extraction Performance by Field - Llama",
                           out / f"6_performance_by_field_llama_{STYLE_SUFFIX}.png")
    chart_report_distribution(raw_dfs, ["Claude", "Llama"],
                              out / f"7_per_report_correctness_distribution_{STYLE_SUFFIX}.png")
    print("\nDone: charts generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

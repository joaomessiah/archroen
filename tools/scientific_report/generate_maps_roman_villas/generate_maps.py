#!/usr/bin/env python3
"""Generate the two Roman-villa maps for the scientific report, from one script.

Merges the former map_thesis_roman_villas/map.py and map_all_roman_villas/map_all_roman_villas_final.py
into a single, self-contained tool that reads the two villa CSVs and produces BOTH maps:

  1. "roman_villa_locations_map"          — South Limburg detail of the TARGET villas (numbered
                                            markers + locality list + Netherlands inset).
  2. "roman_villa_sites_in_south_limburg" — all Roman villas (grey) with the target villas
                                            highlighted (numbered black) over the same area.

Each map is written as a PNG into the output folder (default: <script_dir>/maps_output/).

Province boundaries come from a local cache (data/provinces_boundaries.geojson, the Dutch PDOK
provinces) so the tool runs fully offline; if that file is missing it falls back to the live PDOK
WFS (needs internet). Fonts resolve gracefully (Times New Roman if present, else the bundled
Liberation Serif look-alike) and never error. Coordinates are RD New (EPSG:28992), metres.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

# ---------------------------------------------------------------------------
# Fonts (graceful: never errors; prefers Times New Roman, else bundled Liberation Serif)
# ---------------------------------------------------------------------------

FONT_SIZE = 22
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_PREFERENCE = ["Times New Roman", "Liberation Serif", "Tinos", "Nimbus Roman", "DejaVu Serif"]


def resolve_serif_font() -> str:
    """Register bundled fonts and return the best available serif family (never raises)."""
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
            if family in ("Times New Roman", "Liberation Serif"):
                print(f"[fonts] using {chosen}.")
            else:
                print(f"[fonts] note: Times New Roman / Liberation Serif not found; using the "
                      f"serif fallback '{chosen}'. Maps still render fine.")
            return chosen
    print("[fonts] warning: no preferred serif font found; using Matplotlib's default.")
    return "serif"


SELECTED_FONT_FAMILY = resolve_serif_font()
plt.rcParams.update({
    "font.family": SELECTED_FONT_FAMILY,
    "font.size": FONT_SIZE,
    "axes.titlesize": FONT_SIZE,
    "axes.labelsize": FONT_SIZE,
    "xtick.labelsize": FONT_SIZE,
    "ytick.labelsize": FONT_SIZE,
    "legend.fontsize": FONT_SIZE,
    "figure.titlesize": FONT_SIZE,
})

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

TARGET_CRS = "EPSG:28992"   # Amersfoort / RD New (metres)
MAP_TITLE = "Roman Villa Sites in South Limburg, the Netherlands"
PDOK_PROVINCES_WFS = (
    "https://service.pdok.nl/kadaster/bestuurlijkegebieden/wfs/v1_0"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=bestuurlijkegebieden:provinciegebied"
    "&srsName=EPSG:28992&outputFormat=application/json"
)

# Label offsets (display points) for the numbered target villas, keyed by RD New coordinate.
LABEL_OFFSETS_BY_COORDINATE = {
    (180500, 317600): (-20, 13), (181840, 316700): (20, -10),
    (178140, 310040): (-22, -9), (179450, 310680): (20, 18),
    (198320, 313510): (-24, 15), (199640, 313760): (24, -10),
    (195650, 317270): (-20, -6), (198520, 318294): (-23, -12),
    (199060, 319550): (-23, 19), (200020, 321270): (-5, 25),
    (200541, 318897): (13, -25), (201080, 319390): (24, 14),
    (203550, 320130): (26, 2), (197848, 322902): (-23, 12),
    (200400, 323750): (21, 15), (202100, 325400): (23, 14),
}

# ---------------------------------------------------------------------------
# Shared data + boundary loading
# ---------------------------------------------------------------------------


def find_column(columns, aliases):
    lookup = {str(col).casefold().strip(): col for col in columns}
    for alias in aliases:
        if alias.casefold().strip() in lookup:
            return lookup[alias.casefold().strip()]
    return None


def load_villa_csv(csv_path: Path) -> pd.DataFrame:
    """Load a villa CSV into columns: site_id, villa_name, x_raw, y_raw, x, y (km)."""
    df = pd.read_csv(csv_path)
    aliases = {
        "site_id": ["SiteID", "Site_Id", "site_id", "id", "ID"],
        "villa_name": ["Name", "Villa", "Villa_name", "Site_name"],
        "x_raw": ["X-coordinate", "X_coordinate", "X", "RD_X"],
        "y_raw": ["Y-coordinate", "Y_coordinate", "Y", "RD_Y"],
    }
    cols = {}
    for canon, al in aliases.items():
        col = find_column(df.columns, al)
        if not col and canon == "site_id":      # site_id is optional (e.g. legacy target file)
            continue
        if not col:
            raise ValueError(f"Could not find the column for {canon!r} in {csv_path.name}.")
        cols[canon] = col
    out = pd.DataFrame()
    out["site_id"] = (df[cols["site_id"]].astype(str).str.strip()
                      if "site_id" in cols else range(len(df)))
    out["villa_name"] = df[cols["villa_name"]].astype(str).str.strip()
    out["x_raw"] = pd.to_numeric(df[cols["x_raw"]], errors="coerce")
    out["y_raw"] = pd.to_numeric(df[cols["y_raw"]], errors="coerce")
    out = out.dropna(subset=["x_raw", "y_raw"]).reset_index(drop=True)
    if out.empty:
        raise ValueError(f"No valid villa coordinates in {csv_path.name}.")
    out["x"] = out["x_raw"] / 1000.0   # metres -> km (readable axes, simple 5 km scale bar)
    out["y"] = out["y_raw"] / 1000.0
    return out


def get_province_name_column(gdf: gpd.GeoDataFrame) -> Optional[str]:
    return find_column(gdf.columns, ["naam", "name", "provincienaam", "provincie_naam", "statnaam", "label"])


def normalize_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        raise ValueError("The boundary dataset is empty.")
    gdf = gdf.set_crs(TARGET_CRS, allow_override=True) if gdf.crs is None else gdf.to_crs(TARGET_CRS)
    name_column = get_province_name_column(gdf)
    if not name_column:
        raise ValueError("Could not find a province-name field in the boundary dataset.")
    gdf = gdf.copy()
    gdf["province_name_normalized"] = gdf[name_column].astype(str).str.strip()
    return gdf


def load_boundaries(boundaries_file: Optional[Path]) -> gpd.GeoDataFrame:
    """Load province boundaries from the local cache if present, else the live PDOK WFS."""
    if boundaries_file and Path(boundaries_file).exists():
        print(f"[boundaries] using local cache: {boundaries_file}")
        return normalize_boundaries(gpd.read_file(boundaries_file))
    print("[boundaries] local cache not found; fetching from the live PDOK WFS (needs internet)...")
    resp = requests.get(PDOK_PROVINCES_WFS, timeout=120)
    resp.raise_for_status()
    return normalize_boundaries(gpd.GeoDataFrame.from_features(resp.json()["features"]))


def scale_geometries_to_km(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    scaled = gdf.copy()
    scaled["geometry"] = scaled.geometry.scale(xfact=1 / 1000.0, yfact=1 / 1000.0, origin=(0, 0))
    return scaled


def add_north_arrow(axis, x: float, text_y: float) -> None:
    axis.annotate("", xy=(x, 0.90), xytext=(x, 0.82), xycoords="axes fraction",
                  arrowprops={"arrowstyle": "simple", "color": "black", "shrinkA": 0, "shrinkB": 0},
                  zorder=20)
    axis.text(x, text_y, "N", transform=axis.transAxes, ha="center", va="top", zorder=20)


def draw_external_scale_bar(axis, y0: float, height: float, length_km: float = 5.0) -> None:
    axis.set_xlim(0, length_km)
    axis.set_ylim(0, 1)
    axis.axis("off")
    half = length_km / 2.0
    axis.add_patch(Rectangle((0, y0), half, height, facecolor="black", edgecolor="black", linewidth=1.0))
    axis.add_patch(Rectangle((half, y0), half, height, facecolor="white", edgecolor="black", linewidth=1.0))
    axis.text(0, 0.12, "0", ha="center", va="top")
    axis.text(half, 0.12, "2.5", ha="center", va="top")
    axis.text(length_km, 0.12, "5 km", ha="center", va="top")


def save_map(figure, output_dir: Path, basename: str) -> Path:
    """Save a figure as PNG (no bbox_inches: the fixed axes positions must stay fixed)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    png = output_dir / f"{basename}.png"
    figure.savefig(png, dpi=300, facecolor=figure.get_facecolor())
    plt.close(figure)
    print(f"  wrote {png.name}")
    return png


# ===========================================================================
# MAP 1 — Target villas, South Limburg detail ("roman_villa_locations_map")
# ===========================================================================

THESIS_COLOR_PALETTE = {
    "figure_background": "white", "map_background": "#f7f4ef", "province_fill": "#dce8d6",
    "province_edge": "#48684d", "marker_fill": "#981b33", "marker_text": "white",
    "exact_point": "#4b0c18", "grid": "#ddd6ce", "country_fill": "#f3f1ec",
    "country_edge": "#888888", "internal_boundary": "#b4b4b4", "country_label": "#666666",
    "legend_edge": "#aaaaaa",
}
THESIS_GRAYSCALE_PALETTE = {
    "figure_background": "white", "map_background": "#f7f7f7", "province_fill": "#e3e3e3",
    "province_edge": "#222222", "marker_fill": "#111111", "marker_text": "white",
    "exact_point": "#111111", "grid": "#d5d5d5", "country_fill": "#f3f3f3",
    "country_edge": "#777777", "internal_boundary": "#b5b5b5", "country_label": "#555555",
    "legend_edge": "#aaaaaa",
}
THESIS_RIGHT_PANEL_TITLE = "Villa locations"


def _thesis_study_extent(villas: pd.DataFrame) -> tuple[float, float, float, float]:
    return (float(villas["x"].min()) - 7.2, float(villas["x"].max()) + 3.3,
            float(villas["y"].min()) - 4.2, float(villas["y"].max()) + 9.5)


def _thesis_plot_markers(axis, villas: pd.DataFrame, colors: dict) -> None:
    for _, row in villas.iterrows():
        number = int(row["map_number"])
        key = (int(round(row["x_raw"])), int(round(row["y_raw"])))
        dx, dy = LABEL_OFFSETS_BY_COORDINATE.get(key, (0, 0))
        leader_line = None
        if dx != 0 or dy != 0:
            axis.scatter([row["x"]], [row["y"]], s=13, color=colors["exact_point"],
                         edgecolors="white", linewidths=0.35, zorder=8)
            leader_line = {"arrowstyle": "-", "color": "#555555", "linewidth": 0.8,
                           "shrinkA": 17, "shrinkB": 2, "connectionstyle": "arc3,rad=0"}
        axis.annotate(str(number), xy=(row["x"], row["y"]), xytext=(dx, dy),
                      textcoords="offset points", ha="center", va="center",
                      color=colors["marker_text"], fontsize=FONT_SIZE, fontweight="bold",
                      bbox={"boxstyle": "circle,pad=0.22", "facecolor": colors["marker_fill"],
                            "edgecolor": "white", "linewidth": 1.0},
                      arrowprops=leader_line, zorder=10)


def _thesis_draw_list(axis, villas: pd.DataFrame) -> None:
    axis.axis("off")
    axis.text(0.00, 1.085, THESIS_RIGHT_PANEL_TITLE, ha="left", va="top", fontweight="bold")
    axis.text(0.00, 1, "Locality", ha="left", va="top", fontweight="bold")
    axis.text(0.985, 1, "No.", ha="right", va="top", fontweight="bold")
    grouped = (villas.groupby("villa_name", sort=True)["map_number"]
               .apply(lambda v: ", ".join(str(int(n)) for n in v)).reset_index())
    current_y, row_step = 0.890, 0.072
    for _, row in grouped.iterrows():
        axis.text(0.00, current_y, str(row["villa_name"]), ha="left", va="center")
        axis.text(0.985, current_y, str(row["map_number"]), ha="right", va="center", multialignment="right")
        current_y -= row_step


def build_thesis_map(target_villas: pd.DataFrame, boundaries: gpd.GeoDataFrame,
                     output_dir: Path, style: str = "grayscale") -> Path:
    """Map 1: South Limburg detail of the target villas."""
    colors = THESIS_GRAYSCALE_PALETTE if style == "grayscale" else THESIS_COLOR_PALETTE
    villas = target_villas.copy()
    villas["map_number"] = range(1, len(villas) + 1)

    limburg = boundaries[boundaries["province_name_normalized"].str.casefold() == "limburg"].copy()
    if limburg.empty:
        raise ValueError('Could not find the province "Limburg".')
    netherlands = boundaries.dissolve()
    boundaries_km = scale_geometries_to_km(boundaries)
    limburg_km = scale_geometries_to_km(limburg)
    netherlands_km = scale_geometries_to_km(netherlands)
    x_min, x_max, y_min, y_max = _thesis_study_extent(villas)

    figure = plt.figure(figsize=(13.6, 8.6), facecolor=colors["figure_background"], constrained_layout=False)
    map_axis = figure.add_axes([0.055, 0.150, 0.655, 0.760])
    scale_axis = figure.add_axes([0.055, 0.065, 0.140, 0.055])
    inset_axis = figure.add_axes([0.812, 0.745, 0.112, 0.128])
    list_axis = figure.add_axes([0.725, 0.225, 0.255, 0.455])
    legend_axis = figure.add_axes([0.735, 0.050, 0.245, 0.105])

    map_box = map_axis.get_position()
    figure.text(map_box.x0 + map_box.width / 2, map_box.y1 + 0.020, MAP_TITLE,
                ha="center", va="bottom", fontweight="bold")

    map_axis.set_facecolor(colors["map_background"])
    limburg_km.plot(ax=map_axis, facecolor=colors["province_fill"], edgecolor=colors["province_edge"],
                    linewidth=1.25, zorder=2)
    limburg_km.boundary.plot(ax=map_axis, color=colors["province_edge"], linewidth=1.25, zorder=3)
    map_axis.set_xlim(x_min, x_max)
    map_axis.set_ylim(y_min, y_max)
    map_axis.set_aspect("equal", adjustable="box")
    map_axis.grid(True, linestyle=":", linewidth=0.55, color=colors["grid"], alpha=0.55, zorder=0)
    map_axis.set_xlabel("Easting (km, RD New)")
    map_axis.set_ylabel("Northing (km, RD New)")
    map_axis.text(0.018, 0.70, "Belgium", transform=map_axis.transAxes, ha="left", va="center",
                  style="italic", color=colors["country_label"], zorder=20)

    add_north_arrow(map_axis, x=0.065, text_y=0.79)
    draw_external_scale_bar(scale_axis, y0=0.44, height=0.24)
    _thesis_plot_markers(map_axis, villas, colors)

    inset_box = inset_axis.get_position()
    figure.text(inset_box.x0 + inset_box.width / 2, inset_box.y1 + 0.0002,
                "Location within\nthe Netherlands", ha="center", va="bottom", fontsize=FONT_SIZE - 2)
    inset_axis.set_facecolor("white")
    netherlands_km.plot(ax=inset_axis, facecolor=colors["country_fill"], edgecolor=colors["country_edge"],
                        linewidth=0.9, zorder=1)
    boundaries_km.boundary.plot(ax=inset_axis, color=colors["internal_boundary"], linewidth=0.45, zorder=2)
    limburg_km.plot(ax=inset_axis, facecolor=colors["marker_fill"], edgecolor=colors["marker_fill"],
                    linewidth=0.7, zorder=3)
    inset_axis.add_patch(Rectangle((x_min, y_min), x_max - x_min, y_max - y_min, fill=False,
                                   edgecolor="#333333", linestyle="--", linewidth=0.8, zorder=4))
    nl_minx, nl_miny, nl_maxx, nl_maxy = netherlands_km.total_bounds
    nl_xpad, nl_ypad = (nl_maxx - nl_minx) * 0.04, (nl_maxy - nl_miny) * 0.04
    inset_axis.set_xlim(nl_minx - nl_xpad, nl_maxx + nl_xpad)
    inset_axis.set_ylim(nl_miny - nl_ypad, nl_maxy + nl_ypad)
    inset_axis.set_aspect("equal", adjustable="box")
    inset_axis.set_xticks([]); inset_axis.set_yticks([])
    for spine in inset_axis.spines.values():
        spine.set_linewidth(0.9); spine.set_edgecolor("black")

    _thesis_draw_list(list_axis, villas)
    legend_axis.axis("off")
    legend = legend_axis.legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor=colors["marker_fill"],
                   markeredgecolor="white", markeredgewidth=1.0, markersize=9, label="Roman villa location"),
            Rectangle((0, 0), 1, 1, facecolor=colors["province_fill"], edgecolor=colors["province_edge"],
                      linewidth=1.1, label="South Limburg"),
        ],
        title="Legend", loc="center", frameon=True, framealpha=1.0, fancybox=True,
        borderpad=0.38, labelspacing=0.34, handlelength=1.15)
    legend.get_title().set_fontsize(FONT_SIZE)
    legend.get_frame().set_edgecolor(colors["legend_edge"])
    legend.get_frame().set_linewidth(0.9)

    return save_map(figure, output_dir, "roman_villa_locations_map")


# ===========================================================================
# MAP 2 — All villas, targets highlighted ("roman_villa_sites_in_south_limburg")
# ===========================================================================

ALL_COLORS = {
    "figure_background": "white", "map_background": "#f7f7f7", "province_fill": "#efefef",
    "province_edge": "#222222", "grid": "#d7d7d7", "country_fill": "#f3f3f3",
    "country_edge": "#a0a0a0", "internal_boundary": "#c5c5c5", "country_label": "#777777",
    "target_marker_fill": "#111111", "target_marker_text": "white", "other_marker_fill": "#9a9a9a",
    "exact_point": "#111111", "leader": "#555555", "legend_edge": "#aaaaaa",
}
OTHER_MARKER_SIZE = 64
EXACT_POINT_SIZE = 10
LEADER_LINEWIDTH = 0.9
TARGET_BOX_PAD = 0.18
DEFAULT_LABEL_OFFSET = (14, 10)
SOUTH_LIMBURG_EXTENT = (170.5, 207.8, 306.5, 333.8)   # fixed RD New km extent


def _all_plot_targets(axis, target_villas: pd.DataFrame) -> None:
    for _, row in target_villas.iterrows():
        number = int(row["map_number"])
        key = (int(round(row["x_raw"])), int(round(row["y_raw"])))
        dx, dy = LABEL_OFFSETS_BY_COORDINATE.get(key, DEFAULT_LABEL_OFFSET)
        axis.scatter([row["x"]], [row["y"]], s=EXACT_POINT_SIZE, color=ALL_COLORS["exact_point"],
                     edgecolors="white", linewidths=0.35, zorder=8)
        axis.annotate(str(number), xy=(row["x"], row["y"]), xytext=(dx, dy),
                      textcoords="offset points", ha="center", va="center",
                      color=ALL_COLORS["target_marker_text"], fontsize=FONT_SIZE * 0.87, fontweight="bold",
                      bbox={"boxstyle": f"circle,pad={TARGET_BOX_PAD}",
                            "facecolor": ALL_COLORS["target_marker_fill"], "edgecolor": "white", "linewidth": 1.0},
                      arrowprops={"arrowstyle": "-", "color": ALL_COLORS["leader"],
                                  "linewidth": LEADER_LINEWIDTH, "shrinkA": 17, "shrinkB": 2,
                                  "connectionstyle": "arc3,rad=0"},
                      zorder=10)


def _all_netherlands_inset(map_axis, boundaries_km: gpd.GeoDataFrame) -> None:
    inset_container = map_axis.inset_axes([0.845, 0.715, 0.145, 0.27])
    inset_container.set_facecolor("white")
    inset_container.set_xticks([]); inset_container.set_yticks([])
    for spine in inset_container.spines.values():
        spine.set_linewidth(0.9); spine.set_edgecolor("black")
    inset_container.text(0.5, 0.94, "Location within\nthe Netherlands", ha="center", va="top",
                         transform=inset_container.transAxes, fontsize=FONT_SIZE * 0.48)
    inset_axis = inset_container.inset_axes([0.14, 0.10, 0.72, 0.58])
    inset_axis.set_facecolor("white")

    netherlands_km = boundaries_km.dissolve()
    limburg_km = boundaries_km[boundaries_km["province_name_normalized"].str.casefold() == "limburg"].copy()
    x_min, x_max, y_min, y_max = SOUTH_LIMBURG_EXTENT
    sl_box = gpd.GeoDataFrame(geometry=[box(x_min, y_min, x_max, y_max)], crs=boundaries_km.crs)
    sl_geom = gpd.overlay(limburg_km[["geometry"]], sl_box, how="intersection")

    boundaries_km.plot(ax=inset_axis, facecolor=ALL_COLORS["country_fill"],
                       edgecolor=ALL_COLORS["internal_boundary"], linewidth=0.45, zorder=1)
    netherlands_km.boundary.plot(ax=inset_axis, color=ALL_COLORS["country_edge"], linewidth=0.70, zorder=2)
    if not sl_geom.empty:
        sl_geom.plot(ax=inset_axis, facecolor="black", edgecolor="black", linewidth=0.45, zorder=3)
    sl_box.boundary.plot(ax=inset_axis, color="black", linewidth=0.8, zorder=4)

    nl_minx, nl_miny, nl_maxx, nl_maxy = netherlands_km.total_bounds
    nl_xpad, nl_ypad = (nl_maxx - nl_minx) * 0.08, (nl_maxy - nl_miny) * 0.08
    inset_axis.set_xlim(nl_minx - nl_xpad, nl_maxx + nl_xpad)
    inset_axis.set_ylim(nl_miny - nl_ypad, nl_maxy + nl_ypad)
    inset_axis.set_aspect("equal", adjustable="box")
    inset_axis.set_xticks([]); inset_axis.set_yticks([])
    for spine in inset_axis.spines.values():
        spine.set_linewidth(0.8); spine.set_edgecolor(ALL_COLORS["country_edge"])


def build_all_villas_map(all_villas: pd.DataFrame, target_villas: pd.DataFrame,
                         boundaries: gpd.GeoDataFrame, output_dir: Path) -> Path:
    """Map 2: all villas (grey) with the target villas highlighted (numbered black)."""
    targets = target_villas.drop_duplicates(subset=["site_id"]).reset_index(drop=True)
    targets["map_number"] = range(1, len(targets) + 1)
    target_ids = set(targets["site_id"])
    others = all_villas[~all_villas["site_id"].isin(target_ids)].drop_duplicates(subset=["site_id"]).copy()

    limburg = boundaries[boundaries["province_name_normalized"].str.casefold() == "limburg"].copy()
    if limburg.empty:
        raise ValueError('Could not find the province "Limburg" in the boundary dataset.')
    boundaries_km = scale_geometries_to_km(boundaries)
    limburg_km = scale_geometries_to_km(limburg)
    x_min, x_max, y_min, y_max = SOUTH_LIMBURG_EXTENT
    others = others[(others["x"] >= x_min) & (others["x"] <= x_max)
                    & (others["y"] >= y_min) & (others["y"] <= y_max)].copy()

    figure = plt.figure(figsize=(14.5, 11.0), facecolor=ALL_COLORS["figure_background"], constrained_layout=False)
    map_axis = figure.add_axes([0.07, 0.205, 0.86, 0.72])
    scale_axis = figure.add_axes([0.08, 0.095, 0.15, 0.045])
    legend_axis = figure.add_axes([0.20, 0.028, 0.60, 0.075])

    map_box = map_axis.get_position()
    figure.text(map_box.x0 + map_box.width / 2, map_box.y1 + 0.012, MAP_TITLE,
                ha="center", va="bottom", fontweight="bold")

    map_axis.set_facecolor(ALL_COLORS["map_background"])
    limburg_km.plot(ax=map_axis, facecolor=ALL_COLORS["province_fill"], edgecolor=ALL_COLORS["province_edge"],
                    linewidth=1.15, zorder=1)
    limburg_km.boundary.plot(ax=map_axis, color=ALL_COLORS["province_edge"], linewidth=1.15, zorder=2)
    map_axis.set_xlim(x_min, x_max)
    map_axis.set_ylim(y_min, y_max)
    map_axis.set_aspect("equal", adjustable="box")
    map_axis.grid(True, linestyle=":", linewidth=0.55, color=ALL_COLORS["grid"], alpha=0.8, zorder=0)
    map_axis.set_xlabel("Easting (km, RD New)")
    map_axis.set_ylabel("Northing (km, RD New)")
    map_axis.text(0.025, 0.75, "Belgium", transform=map_axis.transAxes, ha="left", va="center",
                  style="italic", color=ALL_COLORS["country_label"], zorder=20)

    add_north_arrow(map_axis, x=0.055, text_y=0.795)
    axis = map_axis
    axis.scatter(others["x"], others["y"], s=OTHER_MARKER_SIZE, c=ALL_COLORS["other_marker_fill"],
                 edgecolors="none", zorder=4)
    _all_plot_targets(map_axis, targets)
    draw_external_scale_bar(scale_axis, y0=0.55, height=0.20)
    _all_netherlands_inset(map_axis, boundaries_km)

    legend_axis.axis("off")
    legend = legend_axis.legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor=ALL_COLORS["target_marker_fill"],
                   markersize=9, label="Target Roman villa"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=ALL_COLORS["other_marker_fill"],
                   markeredgecolor="none", markersize=7, label="Other Roman villa"),
            Rectangle((0, 0), 1, 1, facecolor=ALL_COLORS["province_fill"], edgecolor=ALL_COLORS["province_edge"],
                      linewidth=1.0, label="South Limburg"),
        ],
        loc="center", ncol=3, frameon=True, fancybox=True, framealpha=1.0, borderpad=0.45,
        handlelength=1.25, columnspacing=1.8, handletextpad=0.7, title="Legend")
    legend.get_title().set_fontsize(FONT_SIZE)
    legend.get_frame().set_edgecolor(ALL_COLORS["legend_edge"])
    legend.get_frame().set_linewidth(0.9)

    return save_map(figure, output_dir, "roman_villa_sites_in_south_limburg")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    data = script_dir / "data"
    p = argparse.ArgumentParser(description="Generate the two Roman-villa maps for the scientific report.")
    p.add_argument("--all", type=Path, default=data / "all_roman_villas.csv",
                   help="CSV of all Roman villas (default: data/all_roman_villas.csv).")
    p.add_argument("--target", type=Path, default=data / "target_roman_villas.csv",
                   help="CSV of the target villas (default: data/target_roman_villas.csv).")
    p.add_argument("--boundaries", type=Path, default=data / "provinces_boundaries.geojson",
                   help="Cached province-boundaries GeoJSON (default: data/provinces_boundaries.geojson; "
                        "falls back to the live PDOK WFS if missing).")
    p.add_argument("--output-dir", type=Path, default=script_dir / "maps_output",
                   help="Folder for the generated maps (default: <script_dir>/maps_output/).")
    p.add_argument("--which", choices=["both", "thesis", "all"], default="both",
                   help="Which map(s) to generate (default: both).")
    p.add_argument("--style", choices=["grayscale", "color"], default="grayscale",
                   help="Palette for the target-villas (thesis) map (default: grayscale).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        boundaries = load_boundaries(args.boundaries)
        target_villas = load_villa_csv(args.target)
        print(f"Writing maps to: {args.output_dir.resolve()}")
        if args.which in ("both", "thesis"):
            build_thesis_map(target_villas, boundaries, args.output_dir, style=args.style)
        if args.which in ("both", "all"):
            all_villas = load_villa_csv(args.all)
            build_all_villas_map(all_villas, target_villas, boundaries, args.output_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

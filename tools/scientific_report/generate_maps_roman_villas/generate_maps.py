#!/usr/bin/env python3
"""Generate the two Roman-villa maps for the scientific report, from one script.

Merges the former map_thesis_roman_villas/map.py and map_all_roman_villas/map_all_roman_villas_final.py
into a single, self-contained tool that reads the two villa CSVs and produces BOTH maps:

  1. "roman_villa_locations_map"          — map of South Limburg showing the TARGET villas (numbered
                                            markers + toponym list + Netherlands inset).
  2. "roman_villa_sites_in_south_limburg" — the other Roman villas (grey) with the target villas
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

# On-page typography. The maps are placed in the thesis / Google Doc at the 16 cm text-column
# width (6.3 in), the same as the charts, so their text should read at a true ~12 pt there. By the
# rule on-page pt = font pt x (display width / figure width), both maps use a fixed figure WIDTH of
# MAP_FIGURE_WIDTH_IN and FONT_SIZE is derived so the text lands at TARGET_ON_PAGE_PT at 16 cm.
# Each map keeps its original aspect ratio (heights below). A wider-than-6.3 in figure is used so
# the dense map detail rasterises sharply while the on-page font stays 12 pt.
DISPLAY_WIDTH_IN = 6.3            # 16 cm text column the PNG is placed at in the Doc
TARGET_ON_PAGE_PT = 12.0         # desired on-page text size at that width
MAP_FIGURE_WIDTH_IN = 8.4        # both maps; 300 DPI -> 2520 px wide
FONT_SIZE = TARGET_ON_PAGE_PT * MAP_FIGURE_WIDTH_IN / DISPLAY_WIDTH_IN   # = 16.0 pt
INSET_CAPTION_FACTOR = 0.50      # inset caption size relative to FONT_SIZE (must fit the inset box)

# The numbered villa markers and the locality list are MAP/REFERENCE elements, not body text, so
# they are sized for the figure and NOT tied to the 12 pt body font — otherwise the circles bloat
# and crowd the map, and the 16-row list overflows its panel.
MARKER_NUMBER_PT = 12.0          # map 1 villa circles: between compact and full 12 pt (~9 pt on page)
LIST_PT = FONT_SIZE              # locality list reads at the same true 12 pt as the body text
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
# Fixed RD New km extent shared by BOTH maps, so they frame the identical area (a villa sits in the
# same relative spot on each). Note this equalises the AREA SHOWN, not the scale: map 1 gives ~46%
# of its width to the locality list, so its map panel is narrower and therefore drawn at a smaller
# scale than map 2 — each map carries its own correct scale bar to reflect that.
SOUTH_LIMBURG_EXTENT = (170.5, 207.8, 306.5, 333.8)
PDOK_PROVINCES_WFS = (
    "https://service.pdok.nl/kadaster/bestuurlijkegebieden/wfs/v1_0"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=bestuurlijkegebieden:provinciegebied"
    "&srsName=EPSG:28992&outputFormat=application/json"
)

# Label offsets (display points) for the numbered target villas, keyed by RD New coordinate, used
# by BOTH maps so each numbered villa is nudged in the same direction on each. EVERY villa gets a
# short hop off its exact point, with a small dot marking the true location and a short leader back
# to it. Directions are chosen so the numbered circles spread out without overlapping each other or
# covering a neighbour's dot. Numbers are 1..16 alphabetical by toponym (see assign_map_numbers).
TARGET_LABEL_OFFSETS = {
    (180500, 317600): (-12, 8),     # 1  Bemelerweg
    (179450, 310680): (12, 11),     # 2  Bij het Savelsbosch
    (198520, 318294): (-14, -7),    # 3  De Locht
    (201080, 319390): (2, 14),      # 4  Kaalheide
    (190250, 313300): (0, 14),      # 5  Kampborn
    (200400, 323750): (-2, 15),     # 6  Koelweg
    (197848, 322902): (-13, 7),     # 7  Leenderhof
    (198320, 313510): (-15, 8),     # 8  Orsbacherweg
    (200020, 321270): (-4, 16),     # 9  Overstehof
    (181840, 316700): (12, -7),     # 10 Pannestuk
    (198320, 310500): (13, -7),     # 11 Platte Bend
    (203550, 320130): (16, 2),      # 12 Rolduc
    (195650, 317270): (-13, -4),    # 13 Schanternelbosje
    (202100, 325400): (14, 9),      # 14 Sportpark
    (178950, 313800): (-13, 7),     # 15 Veldhoff
    (199060, 319550): (-14, 11),    # 16 Winckelen
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
    """Load a villa CSV into columns: site_id, villa_name, toponym, x_raw, y_raw, x, y (km)."""
    df = pd.read_csv(csv_path)
    aliases = {
        "site_id": ["SiteID", "Site_Id", "site_id", "id", "ID"],
        "villa_name": ["Name", "Villa", "Villa_name", "Site_name"],
        "toponym": ["Toponym", "toponym", "Topo"],
        "x_raw": ["X-coordinate", "X_coordinate", "X-coordinate_RD", "X_coordinate_RD", "X", "RD_X"],
        "y_raw": ["Y-coordinate", "Y_coordinate", "Y-coordinate_RD", "Y_coordinate_RD", "Y", "RD_Y"],
    }
    cols = {}
    for canon, al in aliases.items():
        col = find_column(df.columns, al)
        # Only coordinates are mandatory. site_id, villa_name and toponym are all optional: the
        # other-villas file has only IDs + coordinates (grey dots, no labels), so name falls back to
        # the site id and toponym falls back to the name.
        if not col and canon in ("site_id", "villa_name", "toponym"):
            continue
        if not col:
            raise ValueError(f"Could not find the column for {canon!r} in {csv_path.name}.")
        cols[canon] = col
    out = pd.DataFrame()
    out["site_id"] = (df[cols["site_id"]].astype(str).str.strip()
                      if "site_id" in cols else range(len(df)))
    out["villa_name"] = (df[cols["villa_name"]].astype(str).str.strip()
                         if "villa_name" in cols else out["site_id"].astype(str))
    out["toponym"] = (df[cols["toponym"]].astype(str).str.strip()
                      if "toponym" in cols else out["villa_name"])
    out["x_raw"] = pd.to_numeric(df[cols["x_raw"]], errors="coerce")
    out["y_raw"] = pd.to_numeric(df[cols["y_raw"]], errors="coerce")
    out = out.dropna(subset=["x_raw", "y_raw"]).reset_index(drop=True)
    if out.empty:
        raise ValueError(f"No valid villa coordinates in {csv_path.name}.")
    out["x"] = out["x_raw"] / 1000.0   # metres -> km (readable axes, simple 5 km scale bar)
    out["y"] = out["y_raw"] / 1000.0
    return out


def assign_map_numbers(villas: pd.DataFrame) -> pd.DataFrame:
    """Number the villas 1..n alphabetically by toponym (A->Z).

    The number is a stable lookup label, not a spatial cue: because the locality list is sorted by
    number, an alphabetical numbering makes the list read A->Z, so both lookups work off the one list
    (marker -> name by reading down to row N; name -> marker by scanning alphabetically). Both maps
    call this so the numbering is identical on each. The per-villa label offsets are keyed by RD
    coordinate, not by number, so they follow each villa regardless of the numbering order.
    """
    out = villas.drop_duplicates(subset=["site_id"]).copy()
    out = out.sort_values("toponym", kind="stable").reset_index(drop=True)
    out["map_number"] = range(1, len(out) + 1)
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


def add_north_arrow(axis, x: float, text_y: float, base_y: float = 0.82) -> None:
    axis.annotate("", xy=(x, base_y + 0.08), xytext=(x, base_y), xycoords="axes fraction",
                  arrowprops={"arrowstyle": "simple", "color": "black", "shrinkA": 0, "shrinkB": 0},
                  zorder=20)
    axis.text(x, text_y, "N", transform=axis.transAxes, ha="center", va="top", zorder=20)


def draw_margin_scale_bar(figure, map_axis, x_anchor: float, y_anchor: float,
                          height: float = 0.022, length_km: float = 5.0) -> None:
    """Add a scale bar in the figure margin below the map, sized to be exactly to scale.

    The map axis uses set_aspect("equal", adjustable="box"), so its true on-figure width is only
    known AFTER the box is laid out. We render once, MEASURE the map's pixels-per-km, and size a
    dedicated bar axis so its full width represents exactly `length_km`. This keeps the bar correct
    (unlike a hand-typed width) while sitting in the clean margin, never over the plotted villas.
    """
    figure.canvas.draw()                                  # finalise the aspect-adjusted map box
    map_box_px = map_axis.get_window_extent()
    map_frac_w = map_box_px.width / figure.bbox.width     # map width as a figure fraction (dpi-free)
    x_span_km = map_axis.get_xlim()[1] - map_axis.get_xlim()[0]
    bar_frac_w = length_km / x_span_km * map_frac_w       # figure-fraction width that is length_km
    bar_axis = figure.add_axes([x_anchor, y_anchor, bar_frac_w, height])
    bar_axis.set_xlim(0, length_km)
    bar_axis.set_ylim(0, 1)
    bar_axis.axis("off")
    half = length_km / 2.0
    bar_axis.add_patch(Rectangle((0, 0.45), half, 0.5, facecolor="black", edgecolor="black", linewidth=1.0))
    bar_axis.add_patch(Rectangle((half, 0.45), half, 0.5, facecolor="white", edgecolor="black", linewidth=1.0))
    # Label only the ends: the bar is compact, so a midpoint "2.5" would collide with "5 km" at body
    # size. The equal black/white segments already mark the 2.5 km midpoint visually.
    bar_axis.text(0, 0.20, "0", ha="center", va="top")
    bar_axis.text(length_km, 0.20, f"{length_km:g} km", ha="center", va="top")


def save_map(figure, output_dir: Path, basename: str) -> Path:
    """Save a figure as PNG (no bbox_inches: the fixed axes positions must stay fixed)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    png = output_dir / f"{basename}.png"
    figure.savefig(png, dpi=300, facecolor=figure.get_facecolor())
    plt.close(figure)
    print(f"  wrote {png.name}")
    return png


# ===========================================================================
# MAP 1 — Target villas over South Limburg ("roman_villa_locations_map")
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

def _thesis_plot_markers(axis, villas: pd.DataFrame, colors: dict) -> None:
    # Numbered circle a short hop off each villa point; an exact dot marks the true point and a
    # short leader connects them. shrinkA=0 runs the line all the way to the circle centre (the
    # circle, drawn on top, covers the inner end) so the leader is always visibly connected; shrinkB
    # leaves the dot just clear. A heavier linewidth keeps the leader from looking too thin.
    for _, row in villas.iterrows():
        number = int(row["map_number"])
        key = (int(round(row["x_raw"])), int(round(row["y_raw"])))
        dx, dy = TARGET_LABEL_OFFSETS.get(key, (0, 0))
        leader_line = None
        if dx != 0 or dy != 0:
            axis.scatter([row["x"]], [row["y"]], s=16, color=colors["exact_point"],
                         edgecolors="white", linewidths=0.4, zorder=8)
            leader_line = {"arrowstyle": "-", "color": "#444444", "linewidth": 1.4,
                           "shrinkA": 0, "shrinkB": 3, "connectionstyle": "arc3,rad=0"}
        axis.annotate(str(number), xy=(row["x"], row["y"]), xytext=(dx, dy),
                      textcoords="offset points", ha="center", va="center",
                      color=colors["marker_text"], fontsize=MARKER_NUMBER_PT, fontweight="bold",
                      bbox={"boxstyle": "circle,pad=0.22", "facecolor": colors["marker_fill"],
                            "edgecolor": "white", "linewidth": 1.0},
                      arrowprops=leader_line, zorder=10)


def _thesis_draw_list(axis, villas: pd.DataFrame) -> None:
    axis.axis("off")
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    # No title / column headers: the numbered circles on the map and the legend already make it
    # clear this is the toponym -> map-number key, so the bare two-column list reads unambiguously.
    # Ordered by map number, which (because the numbering is alphabetical by toponym) also reads
    # A->Z, so the list serves both lookups: marker -> name (read down to row N) and name -> marker.
    grouped = (villas.groupby("toponym", sort=True)
               .agg(numbers=("map_number", lambda v: ", ".join(str(int(n)) for n in v)),
                    sort_key=("map_number", "min")).reset_index()
               .sort_values("sort_key").reset_index(drop=True))
    # Even row spacing to fill the panel without overlapping (rows render at LIST_PT).
    n = len(grouped)
    top, bottom = 0.97, 0.085
    step = (top - bottom) / max(n - 1, 1)
    y = top
    for _, row in grouped.iterrows():
        axis.text(0.0, y, str(row["toponym"]), ha="left", va="center", fontsize=LIST_PT)
        axis.text(1.0, y, str(row["numbers"]), ha="right", va="center", fontsize=LIST_PT,
                  multialignment="right")
        y -= step


def build_thesis_map(target_villas: pd.DataFrame, boundaries: gpd.GeoDataFrame,
                     output_dir: Path, style: str = "grayscale") -> Path:
    """Map 1: the target villas over South Limburg (same frame as map 2)."""
    colors = THESIS_GRAYSCALE_PALETTE if style == "grayscale" else THESIS_COLOR_PALETTE
    villas = assign_map_numbers(target_villas)

    limburg = boundaries[boundaries["province_name_normalized"].str.casefold() == "limburg"].copy()
    if limburg.empty:
        raise ValueError('Could not find the province "Limburg".')
    netherlands = boundaries.dissolve()
    boundaries_km = scale_geometries_to_km(boundaries)
    limburg_km = scale_geometries_to_km(limburg)
    netherlands_km = scale_geometries_to_km(netherlands)
    x_min, x_max, y_min, y_max = SOUTH_LIMBURG_EXTENT   # same frame as map 2

    # Everything renders at the true 12 pt body size. Layout (content centred with even margins):
    # LEFT column = map (top) + scale bar + legend (bottom); RIGHT column = Netherlands inset (top,
    # above the table) + locality list (below). The figure is tall because a 16-row list at 12 pt
    # needs the height; width stays 16 cm on page.
    figure = plt.figure(figsize=(MAP_FIGURE_WIDTH_IN, 6.94),
                        facecolor=colors["figure_background"], constrained_layout=False)
    map_axis = figure.add_axes([0.113, 0.378, 0.540, 0.529])    # top-left; aspect ~matches the data
    inset_axis = figure.add_axes([0.783, 0.731, 0.180, 0.164])  # top-right, ABOVE the list
    list_axis = figure.add_axes([0.668, 0.006, 0.300, 0.668])   # right column, below the inset
    legend_axis = figure.add_axes([0.235, 0.066, 0.410, 0.271]) # raised, between scale bar and list

    map_box = map_axis.get_position()
    figure.text(map_box.x0 + map_box.width / 2, map_box.y1 + 0.012, MAP_TITLE,
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
    _thesis_plot_markers(map_axis, villas, colors)

    inset_box = inset_axis.get_position()
    figure.text(inset_box.x0 + inset_box.width / 2, inset_box.y1 + 0.004,
                "Location within\nthe Netherlands", ha="center", va="bottom", fontsize=FONT_SIZE)
    inset_axis.set_facecolor("white")
    netherlands_km.plot(ax=inset_axis, facecolor=colors["country_fill"], edgecolor=colors["country_edge"],
                        linewidth=0.9, zorder=1)
    boundaries_km.boundary.plot(ax=inset_axis, color=colors["internal_boundary"], linewidth=0.45, zorder=2)
    # Highlight in black ONLY the study area (Limburg ∩ the map extent), like map 2's inset —
    # not the whole province.
    sl_box = gpd.GeoDataFrame(geometry=[box(x_min, y_min, x_max, y_max)], crs=limburg_km.crs)
    sl_geom = gpd.overlay(limburg_km[["geometry"]], sl_box, how="intersection")
    if not sl_geom.empty:
        sl_geom.plot(ax=inset_axis, facecolor=colors["marker_fill"], edgecolor=colors["marker_fill"],
                     linewidth=0.5, zorder=3)
    sl_box.boundary.plot(ax=inset_axis, color="#333333", linewidth=0.8, zorder=4)
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
                   markeredgecolor="white", markeredgewidth=1.0, markersize=11, label="Roman villa location"),
            Rectangle((0, 0), 1, 1, facecolor=colors["province_fill"], edgecolor=colors["province_edge"],
                      linewidth=1.1, label="South Limburg"),
        ],
        title="Legend", loc="center", frameon=True, framealpha=1.0, fancybox=True,
        borderpad=0.38, labelspacing=0.34, handlelength=1.15)
    legend.get_title().set_fontsize(FONT_SIZE)
    legend.get_frame().set_edgecolor(colors["legend_edge"])
    legend.get_frame().set_linewidth(0.9)

    # Last, so the map box is fully laid out before its scale is measured. Anchored below the map's
    # x-axis label, above the legend (clear margin — never over a villa).
    draw_margin_scale_bar(figure, map_axis, x_anchor=0.128, y_anchor=0.230, height=0.023)
    return save_map(figure, output_dir, "roman_villa_locations_map")


# ===========================================================================
# MAP 2 — Other villas, targets highlighted ("roman_villa_sites_in_south_limburg")
# ===========================================================================

ALL_COLORS = {
    "figure_background": "white", "map_background": "#f7f7f7", "province_fill": "#efefef",
    "province_edge": "#222222", "grid": "#d7d7d7", "country_fill": "#f3f3f3",
    "country_edge": "#a0a0a0", "internal_boundary": "#c5c5c5", "country_label": "#777777",
    "target_marker_fill": "#111111", "target_marker_text": "white", "other_marker_fill": "#9a9a9a",
    "exact_point": "#111111", "leader": "#444444", "legend_edge": "#aaaaaa",
}
OTHER_MARKER_SIZE = 40
EXACT_POINT_SIZE = 16            # match map 1's exact dot
LEADER_LINEWIDTH = 1.4          # match map 1's thicker leader
TARGET_BOX_PAD = 0.22           # match map 1's circle padding
DEFAULT_LABEL_OFFSET = (14, 10)


def _all_plot_targets(axis, target_villas: pd.DataFrame) -> None:
    for _, row in target_villas.iterrows():
        number = int(row["map_number"])
        key = (int(round(row["x_raw"])), int(round(row["y_raw"])))
        dx, dy = TARGET_LABEL_OFFSETS.get(key, DEFAULT_LABEL_OFFSET)
        axis.scatter([row["x"]], [row["y"]], s=EXACT_POINT_SIZE, color=ALL_COLORS["exact_point"],
                     edgecolors="white", linewidths=0.35, zorder=8)
        axis.annotate(str(number), xy=(row["x"], row["y"]), xytext=(dx, dy),
                      textcoords="offset points", ha="center", va="center",
                      color=ALL_COLORS["target_marker_text"], fontsize=MARKER_NUMBER_PT, fontweight="bold",
                      bbox={"boxstyle": f"circle,pad={TARGET_BOX_PAD}",
                            "facecolor": ALL_COLORS["target_marker_fill"], "edgecolor": "white", "linewidth": 1.0},
                      arrowprops={"arrowstyle": "-", "color": ALL_COLORS["leader"],
                                  "linewidth": LEADER_LINEWIDTH, "shrinkA": 0, "shrinkB": 3,
                                  "connectionstyle": "arc3,rad=0"},
                      zorder=10)


def _all_netherlands_inset(map_axis, boundaries_km: gpd.GeoDataFrame) -> None:
    # Raised clear of the northern villa markers, which sit just below this corner.
    inset_container = map_axis.inset_axes([0.85, 0.745, 0.15, 0.24])
    inset_container.set_facecolor("white")
    inset_container.set_xticks([]); inset_container.set_yticks([])
    for spine in inset_container.spines.values():
        spine.set_linewidth(0.9); spine.set_edgecolor("black")
    inset_container.text(0.5, 0.94, "Location within\nthe Netherlands", ha="center", va="top",
                         transform=inset_container.transAxes, fontsize=FONT_SIZE * INSET_CAPTION_FACTOR)
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


def build_all_villas_map(other_villas: pd.DataFrame, target_villas: pd.DataFrame,
                         boundaries: gpd.GeoDataFrame, output_dir: Path) -> Path:
    """Map 2: the other villas (grey) with the target villas highlighted (numbered black)."""
    targets = assign_map_numbers(target_villas)
    target_ids = set(targets["site_id"])
    # Drop any target that also appears in the other-villas file, so a target shows ONLY as a
    # numbered analysed villa, never doubled as a grey dot underneath.
    others = other_villas[~other_villas["site_id"].isin(target_ids)].drop_duplicates(subset=["site_id"]).copy()

    limburg = boundaries[boundaries["province_name_normalized"].str.casefold() == "limburg"].copy()
    if limburg.empty:
        raise ValueError('Could not find the province "Limburg" in the boundary dataset.')
    boundaries_km = scale_geometries_to_km(boundaries)
    limburg_km = scale_geometries_to_km(limburg)
    x_min, x_max, y_min, y_max = SOUTH_LIMBURG_EXTENT
    others = others[(others["x"] >= x_min) & (others["x"] <= x_max)
                    & (others["y"] >= y_min) & (others["y"] <= y_max)].copy()

    # The map axis aspect matches the data (~1.366) so the map fills it with no letterbox, and it is
    # sized/placed to leave even margins all round (like map 1), with the title above and the scale
    # bar + legend below. The scale bar sits ABOVE the legend; the legend box is opaque, so labels clear.
    figure = plt.figure(figsize=(MAP_FIGURE_WIDTH_IN, 7.3),
                        facecolor=ALL_COLORS["figure_background"], constrained_layout=False)
    map_axis = figure.add_axes([0.121, 0.224, 0.840, 0.707])
    legend_axis = figure.add_axes([0.221, 0.016, 0.600, 0.075])

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

    add_north_arrow(map_axis, x=0.055, text_y=0.845, base_y=0.865)   # raised clear of "Belgium"
    map_axis.scatter(others["x"], others["y"], s=OTHER_MARKER_SIZE, c=ALL_COLORS["other_marker_fill"],
                     edgecolors="none", zorder=4)
    _all_plot_targets(map_axis, targets)
    _all_netherlands_inset(map_axis, boundaries_km)

    legend_axis.axis("off")
    legend = legend_axis.legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor=ALL_COLORS["target_marker_fill"],
                   markersize=11, label="Analyzed villa"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=ALL_COLORS["other_marker_fill"],
                   markeredgecolor="none", markersize=9, label="Other Roman villa"),
            Rectangle((0, 0), 1, 1, facecolor=ALL_COLORS["province_fill"], edgecolor=ALL_COLORS["province_edge"],
                      linewidth=1.0, label="South Limburg"),
        ],
        loc="center", ncol=3, frameon=True, fancybox=True, framealpha=1.0, borderpad=0.5,
        handlelength=1.25, columnspacing=1.8, handletextpad=0.7)
    legend.get_frame().set_edgecolor(ALL_COLORS["legend_edge"])
    legend.get_frame().set_linewidth(0.9)

    # Last, so the map box is fully laid out before its scale is measured. Anchored below the map's
    # x-axis label, above the legend (clear margin — never over a villa).
    draw_margin_scale_bar(figure, map_axis, x_anchor=0.131, y_anchor=0.132, height=0.026)
    return save_map(figure, output_dir, "roman_villa_sites_in_south_limburg")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    data = script_dir / "data"
    p = argparse.ArgumentParser(description="Generate the two Roman-villa maps for the scientific report.")
    p.add_argument("--others", "--all", dest="others", type=Path,
                   default=data / "other_roman_villas.csv",
                   help="CSV of the other Roman villas shown as grey dots on map 2 "
                        "(default: data/other_roman_villas.csv). May include the target villas; "
                        "they are de-duplicated so a target shows only as an analysed villa.")
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
            other_villas = load_villa_csv(args.others)
            build_all_villas_map(other_villas, target_villas, boundaries, args.output_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

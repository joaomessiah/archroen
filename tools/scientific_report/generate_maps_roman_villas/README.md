# Roman-villa map generator

`generate_maps.py` produces the two Roman-villa maps used in the scientific report, from one
script and the two bundled villa datasets.

## What it does

It reads two CSVs of villa locations and renders two publication-ready maps of South Limburg
(the Netherlands), each as a **PNG**:

| Map | File basename | Shows |
|-----|---------------|-------|
| 1 | `roman_villa_locations_map` | The **target** villas as a numbered map of South Limburg, with a toponym list and a Netherlands inset. |
| 2 | `roman_villa_sites_in_south_limburg` | The **other** Roman villas as grey dots, with the target villas highlighted as numbered black markers, over the same area. |

The script is:

- **Self-contained.** It carries its own input data (`data/`), its own bundled font (`fonts/`),
  and a cached copy of the boundaries, so it has no dependency on any other folder.
- **Offline by default.** Province boundaries are read from the local cache (see *Boundaries*),
  so no internet is needed.
- Coordinates are Dutch **RD New (EPSG:28992)**, plotted in kilometres.

## Requirements

- Python with `geopandas`, `shapely`, `pyproj`, `matplotlib`, `pandas` (and `requests`). These are
  all in the repo's `requirements.txt`, so a one-time
  `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (from the repo root)
  installs everything. If the repo's `.venv` is already set up, you're ready.
- **Fonts: nothing to install** (see *Fonts* below).
- **Internet: not required** by default (see *Boundaries* below).

## Inputs

Three files, all with sensible defaults pointing at the bundled `data/` folder — so you can just
run the script with no arguments. Override any of them if needed:

| Flag | Default | What it is |
|------|---------|------------|
| `--target` | `data/target_roman_villas.csv` | the target villas (numbered on both maps) |
| `--others` | `data/other_roman_villas.csv` | the other Roman villas (grey dots on map 2) |
| `--boundaries` | `data/provinces_boundaries.geojson` | cached Dutch province boundaries |

Both villa CSVs are read by the same loader. Only the coordinate columns are required; it accepts
`X-coordinate`/`Y-coordinate` or the `_RD` suffixed variants (RD New metres). `SiteID`, `Name` and
`Toponym` are optional (the others file has only IDs + coordinates — its dots are unlabelled).

**About `other_roman_villas.csv`.** It holds **one row per `SiteID`**, each at its own recorded RD
New coordinate (no centroiding — the dot is plotted exactly where the CSV says). It may also list
the target villas; map 2 de-duplicates by `SiteID`, so a target is drawn only as a numbered
analysed villa, never doubled as a grey dot. (`--all` is still accepted as an alias of `--others`.)

## Output

By default, two PNG files (one per map) are written to a `maps_output/` folder next to the
script (`tools/scientific_report/generate_maps_roman_villas/maps_output/`). Override with
`--output-dir`.

**Size / placement.** Both maps are exported at **300 DPI** with a figure width of 8.4 in
(2520 px). They are tuned so that when each image is placed at the **16 cm (6.3 in)** thesis
text-column width — the same width as the charts — the map text renders at a true **~12 pt**,
matching 12 pt body text. (This uses `on-page pt = font pt × display width / figure width`; the
figure is wider than 6.3 in only so the dense map detail rasterises sharply, while the on-page
font stays 12 pt.) Insert each map at **16 cm** wide.

## Boundaries (offline by default)

The province outlines come from the Dutch national geodata service (**PDOK**). A full-resolution
copy is cached in `data/provinces_boundaries.geojson` (~3.7 MB), so the script runs **fully
offline**. If that file is ever missing, the script automatically falls back to the **live PDOK
WFS** (which needs internet). A `[boundaries]` line on each run states which source was used.

## Fonts

All map text is rendered in a **Times New Roman style**, and you do not need to install anything.
The script resolves a font automatically and never fails over fonts:

1. a real **Times New Roman** if your computer already has one (typical on Windows/macOS), else
2. the **Liberation Serif** font bundled in `fonts/` (a free, look-alike of Times New Roman, used
   automatically with no setup), else
3. another Times-like serif, or finally Matplotlib's built-in serif (with a short `[fonts]` notice).

The bundled fonts are loaded directly into Matplotlib (not installed into your operating system),
so they work identically on Linux, Windows and macOS. See `fonts/NOTICE.txt` for the font license.

## Usage (step by step)

You do not need to be a programmer to run this.

### Step 1 - Open a terminal in the project folder

- **Windows:** open the project folder in File Explorer, click the address bar, type `cmd`, Enter.
- **macOS:** open the **Terminal** app, type `cd ` (with a space), drag the project folder onto the
  window, Enter.
- **Linux:** right-click the project folder and choose "Open in Terminal".

### Step 2 - Run the command

The inputs are bundled, so the simplest run needs no arguments. Paste this and press Enter:

```bash
.venv/bin/python3 tools/scientific_report/generate_maps_roman_villas/generate_maps.py
```

On **Windows**, replace `.venv/bin/python3` with `.venv\Scripts\python`.

### Step 3 - Find your maps

When it finishes you will see lines like:

```
[fonts] using Times New Roman.
[boundaries] using local cache: .../data/provinces_boundaries.geojson
  wrote roman_villa_locations_map.png
  wrote roman_villa_sites_in_south_limburg.png
Done.
```

The two PNG files are now in the **`maps_output/`** folder next to the script
(`tools/scientific_report/generate_maps_roman_villas/maps_output/`). Open that folder to view them
or insert them into the thesis.

### Useful options

```bash
# Generate only one of the two maps:
... generate_maps.py --which thesis      # only map 1 (target villas)
... generate_maps.py --which all         # only map 2 (other villas)

# Save the maps elsewhere:
... generate_maps.py --output-dir my_maps

# Use a colour palette for map 1 instead of grayscale:
... generate_maps.py --style color
```

### If something goes wrong

- **A `[boundaries]` line says it is fetching from the live PDOK WFS** - the local cache file is
  missing or was moved. Restore `data/provinces_boundaries.geojson`, or just let it fetch online
  (needs internet).
- **`ERROR: ... Limburg ...`** - the boundary data did not contain the Limburg province; check the
  boundaries file.
- **A `[fonts]` notice about a fallback font** - not an error; the maps still render, just in a
  slightly different (still serif) font.

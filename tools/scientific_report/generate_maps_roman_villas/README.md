# Roman-villa map generator

`generate_maps.py` produces the two Roman-villa maps used in the scientific report, from one
script and the two bundled villa datasets.

## What it does

It reads two CSVs of villa locations and renders two publication-ready maps of South Limburg
(the Netherlands), each as a **PNG**:

| Map | File basename | Shows |
|-----|---------------|-------|
| 1 | `roman_villa_locations_map` | The **target** villas as a numbered South Limburg detail map, with a locality list and a Netherlands inset. |
| 2 | `roman_villa_sites_in_south_limburg` | **All** Roman villas as grey dots, with the target villas highlighted as numbered black markers, over the same area. |

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
| `--all` | `data/all_roman_villas.csv` | every Roman villa (grey dots on map 2) |
| `--boundaries` | `data/provinces_boundaries.geojson` | cached Dutch province boundaries |

Each villa CSV has the columns `SiteID, Name, X-coordinate, Y-coordinate` (RD New metres).

## Output

By default, two PNG files (one per map) are written to a `maps_output/` folder next to the
script (`tools/scientific_report/generate_maps_roman_villas/maps_output/`). Override with
`--output-dir`.

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
... generate_maps.py --which all         # only map 2 (all villas)

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

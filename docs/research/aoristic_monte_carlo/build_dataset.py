"""
build_dataset.py - rebuild data/aoristic_dataset.csv from repository sources.

The aoristic/Monte Carlo analysis runs on `data/aoristic_dataset.csv`: the ARCHROEN pottery
summaries for the Roman-villa corpus, one row per dated find, tagged with its villa site. This
script regenerates that file from data already in the repository, so the whole chain is reproducible:

    ../datasets/roman_villas/outputs/  ->  build_dataset.py  ->  data/aoristic_dataset.csv

Steps: merge the 30 frozen per-report pottery summaries (in report-id order), keep only the base
pipeline columns (the ABR `std_*` columns are dropped - this study predates them), drop undated rows,
map each report to its villa site via `sites.csv` (semicolon-separated `LiteratureID` = report id),
and write the site-tagged dataset. Row order matches the frozen inputs so the seeded Monte Carlo in
`aoristic_analysis.py` reproduces exactly.
"""
import pandas as pd
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN_OUTPUTS = HERE.parent / "datasets" / "roman_villas" / "outputs"   # ARCHROEN villa outputs (frozen)
SITES_CSV = HERE / "data" / "sites.csv"
DEST = HERE / "data" / "aoristic_dataset.csv"

# The base pipeline columns kept from each per-report summary (drops the std_* ABR columns).
BASE_COLS = [
    "report_id", "site_name", "page", "pottery", "typology", "term_found",
    "term_found_normalized_en", "quantity", "start_date", "end_date", "date_method",
    "context_label", "pot_name_certainty_level", "pot_name_llm_reasoning",
    "pot_presence_certainty_level", "pot_presence_llm_reasoning", "dates_certainty_level",
    "date_llm_reasoning", "overall_certainty_level", "original_text",
]
# Final column order: five site columns, then the report columns (report site_name -> report_site_name).
FINAL_COLS = (
    ["site_id", "site_name", "site_toponym", "site_x_coordinate", "site_y_coordinate"]
    + ["report_id", "report_site_name"] + BASE_COLS[2:]
)


def main():
    # 1. merge the per-report summaries in report-id order (drops std_* and any extra columns)
    files = sorted(FROZEN_OUTPUTS.glob("*.csv"), key=lambda p: p.stem)
    merged = pd.concat([pd.read_csv(f, dtype=str)[BASE_COLS] for f in files], ignore_index=True)

    # 2. drop undated rows (both endpoints required)
    dated = merged[
        merged["start_date"].notna() & (merged["start_date"] != "")
        & merged["end_date"].notna() & (merged["end_date"] != "")
    ].copy()

    # 3. map report_id -> villa site (sites.csv: semicolon-separated LiteratureID)
    sites = pd.read_csv(SITES_CSV, dtype=str)
    rid2site = {}
    for _, s in sites.iterrows():
        for rid in str(s["literature_id"]).split(";"):
            rid2site[rid.strip()] = s
    dated = dated[dated["report_id"].isin(rid2site)].copy()

    # 4. attach the site columns
    dated = dated.rename(columns={"site_name": "report_site_name"})
    dated["site_id"] = dated["report_id"].map(lambda r: rid2site[r]["site_id"])
    dated["site_name"] = dated["report_id"].map(lambda r: rid2site[r]["name"])
    dated["site_toponym"] = dated["report_id"].map(lambda r: rid2site[r]["toponym"])
    dated["site_x_coordinate"] = dated["report_id"].map(lambda r: rid2site[r]["x_coordinate"])
    dated["site_y_coordinate"] = dated["report_id"].map(lambda r: rid2site[r]["y_coordinate"])

    # 5. order columns and write
    dated[FINAL_COLS].to_csv(DEST, index=False)
    print(f"wrote {DEST}  ({len(dated)} rows, {len(FINAL_COLS)} columns)")


if __name__ == "__main__":
    main()

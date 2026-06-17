#!/usr/bin/env python3
"""
Reads pottery_vocab_master.csv and produces pottery_vocab_normalized.csv.

Groups synonymous typology codes (from the explicit 'synonyms' column) into a
single entry so that every variant form — individual codes, abbreviations, and
all combinations — resolves to one canonical code and one date range.

Output columns:
  typology_code, all_forms, abbreviations,
  pot_name_en, pot_name_nl, pot_name_de, pot_name_fr,
  ware_type, vessel_form, production_region,
  date_start, date_end, date_confidence, date_source
"""

import csv
from collections import defaultdict
from pathlib import Path

DATA_DIR  = Path(__file__).resolve().parent.parent / "data" / "vocabularies"
MASTER    = DATA_DIR / "pottery_vocab_master.csv"
OUT_FILE  = DATA_DIR / "pottery_vocab_normalized.csv"

FIELDNAMES = [
    "typology_code", "all_forms", "abbreviations",
    "pot_name_en", "pot_name_nl", "pot_name_de", "pot_name_fr",
    "ware_type", "vessel_form", "production_region",
    "date_start", "date_end", "date_confidence", "date_source",
]


class UnionFind:
    def __init__(self) -> None:
        self._p: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._p:
            self._p[x] = x
        # Iterative path compression
        root = x
        while self._p[root] != root:
            root = self._p[root]
        while self._p[x] != root:
            self._p[x], x = root, self._p[x]
        return root

    def union(self, x: str, y: str) -> None:
        px, py = self.find(x), self.find(y)
        if px != py:
            if px < py:
                self._p[py] = px
            else:
                self._p[px] = py


def main() -> None:
    """Read pottery_vocab_master.csv and write pottery_vocab_normalized.csv, collapsing each group
    of synonymous typology codes (per the 'synonyms' column) into one canonical entry with a single
    date range, so every variant — codes, abbreviations, combinations — resolves to one code."""
    with open(MASTER, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # ── Build Union-Find from explicit synonyms ───────────────────────────────
    uf = UnionFind()
    for row in rows:
        code = row["typology_code"]
        for syn in row["synonyms"].split("|"):
            syn = syn.strip()
            if syn:
                uf.union(code, syn)

    # ── Group rows by canonical root ──────────────────────────────────────────
    groups: dict[str, dict] = defaultdict(lambda: {
        "codes":      [],   # all typology codes in this group
        "abbrevs":    [],   # all abbreviation strings
        "date_start": None,
        "date_end":   None,
        "rows":       [],   # source rows (for picking best names/metadata)
        "standalone": [],   # codes that have their own row
    })

    for row in rows:
        root = uf.find(row["typology_code"])
        g = groups[root]
        code = row["typology_code"]
        if code not in g["codes"]:
            g["codes"].append(code)
        g["standalone"].append(code)
        g["rows"].append(row)
        start, end = int(row["date_start"]), int(row["date_end"])
        if g["date_start"] is None or start < g["date_start"]:
            g["date_start"] = start
        if g["date_end"] is None or end > g["date_end"]:
            g["date_end"] = end
        for abbr in row["abbreviations"].split("|"):
            abbr = abbr.strip()
            if abbr and abbr not in g["abbrevs"]:
                g["abbrevs"].append(abbr)

    # ── Build output rows ─────────────────────────────────────────────────────
    output_rows: list[dict] = []

    for g in groups.values():
        # Primary canonical: alphabetically first standalone code
        primary = sorted(g["standalone"])[0]
        primary_row = next((r for r in g["rows"] if r["typology_code"] == primary), g["rows"][0])

        # all_forms = all individual codes in the group
        all_forms = sorted(set(g["codes"]))

        output_rows.append({
            "typology_code":     primary,
            "all_forms":         "|".join(all_forms),
            "abbreviations":     "|".join(g["abbrevs"]),
            "pot_name_en":       primary_row["pot_name_en"],
            "pot_name_nl":       primary_row["pot_name_nl"],
            "pot_name_de":       primary_row["pot_name_de"],
            "pot_name_fr":       primary_row["pot_name_fr"],
            "ware_type":         primary_row["ware_type"],
            "vessel_form":       primary_row["vessel_form"],
            "production_region": primary_row["production_region"],
            # Date the group to its PRIMARY (canonical) code's own date, not the
            # min/max union across the group — a synonym like "Dressel 2-4" must
            # not widen the canonical "Dressel 2" range (−30–150 → −30–250).
            "date_start":        primary_row["date_start"],
            "date_end":          primary_row["date_end"],
            "date_confidence":   primary_row["date_confidence"],
            "date_source":       primary_row["date_source"],
        })

    output_rows.sort(key=lambda r: r["typology_code"])

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    n_syn = sum(1 for g in groups.values() if len(set(g["codes"])) > 1)
    print(f"Master rows  : {len(rows)}")
    print(f"Output groups: {len(output_rows)}  ({n_syn} synonym groups)")
    print(f"Written to   : {OUT_FILE}")


if __name__ == "__main__":
    main()

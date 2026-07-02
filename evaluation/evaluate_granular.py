#!/usr/bin/env python3
"""Granular, per-field gold-vs-output evaluation harness.

A finer-grained companion to `evaluate.py`. Where `evaluate.py` reports detection recall and
per-field agreement as single percentages, this script classifies EACH field of EACH finding and
shows the gold value next to the workflow value, so the result can be audited field-by-field
(replacing the manual spreadsheet that used the confusing Positive / Negative / False-positive /
False-negative labels).

Each gold find is paired one-to-one with a pipeline row using `evaluate.match()` (the same matching
methodology). Then every field gets a verdict computed purely from its two values:

    exact       - gold and workflow values are identical (after normalisation)
    acceptable  - not identical but archaeologically tolerable (ware family / token overlap for
                  pottery; one site name's tokens contained in the other for site_name; date
                  endpoint within +/-TOLERANCE years ONLY when the gold finding has no typology -
                  if the gold has a typology the date must be exact, the typology being "master")
    incorrect   - the pair is MATCHED but this field disagrees: either both present and different,
                  OR exactly one side is blank (a blank workflow field where the gold has a value -
                  and the reverse - is an incorrect field, NOT `missing`/`overclaim`). Both blank
                  counts as `exact` (genuine agreement that the field is empty).

`missing` and `overclaim` are RECORD-level verdicts only - they never arise inside a matched pair.
A record that does not pair up fills every field uniformly:

    missing-record    - a GOLD find with no pipeline row  -> every field `missing`
                        (old "false negative"): the find was not surfaced at all. A pure RECALL miss.
    overclaim-record  - a PIPELINE row with no gold find  -> every field `overclaim`
                        (old "false positive"): an over-detection the gold does not list. Because the
                        gold is a SILVER standard (deliberately incomplete), an overclaim is likely
                        wrong but NOT definitively so without manual review.

There is no separate record-level verdict column: a wholly-`missing` row is a missed find, a
wholly-`overclaim` row is an over-detection, and everything else is a matched pair.

COUNTING UNIT — important: every count in the per-field columns and the `total_*` rollups is over
field VALUES, not findings. Each finding has five fields, so a wholly-`missing` finding contributes
5 to the missing counts (one per field) and a wholly-`overclaim` finding contributes 5 to overclaim;
a matched finding that merely lacks one value adds just 1 to that field's missing. So
`total_missing_values` means "number of missing field-VALUES", NOT "number of missing findings".
The count of whole FINDINGS that paired / were missed / were overclaimed is printed separately as the
console "Record tallies" (a finding-level correct/incorrect rollup is deliberately NOT emitted: any
all-or-nothing threshold would mislabel a finding that is perfect except for one empty field).

Outputs:
  - a console summary table (per report + aggregate),
  - a DETAIL csv (one row per finding: per field, the verdict + gold value + workflow value),
  - a wide SUMMARY csv: per field the five verdict counts (exact, acceptable, incorrect, missing,
    overclaim), plus grouped row totals over VALUES (total_correct_values / total_incorrect_values /
    total_missing_values / total_overclaim_values / total_values, where correct = exact +
    acceptable). Mirrors the original manual spreadsheet.

Usage:
    python3 evaluation/evaluate_granular.py
    python3 evaluation/evaluate_granular.py --report new_rep_2
    python3 evaluation/evaluate_granular.py --summary-dir output_files/reports/workflow_evaluation_sample-claude
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so `import evaluate` finds the sibling
import evaluate as ev

# Where this script writes its two CSVs by default: output_files/evaluation/<stem>/, where <stem> is
# the name of the scored output set (e.g. "workflow_evaluation_sample-claude"). Computed per-run
# (in main) once the output folder is resolved, so Claude- and Llama-mode evals never collide.
EVAL_OUTPUT_BASE = ev.BASE / "output_files" / "evaluation"

# Default +/- years within which a non-exact date endpoint still counts as "acceptable" — applied
# ONLY when the gold finding has no typology (a typology pins the date, so it must then be exact).
# A module constant by design (so the methodology is visible); overridable with --tolerance.
TOLERANCE = 25

FIELDS = ["site_name", "pottery", "typology", "start_date", "end_date"]
VERDICTS = ["exact", "acceptable", "incorrect", "missing", "overclaim"]
# The summary rolls the five verdicts up into four groups (exact + acceptable -> correct); the full
# exact-vs-acceptable split stays in the detail CSV.
GROUPS = ["correct", "incorrect", "missing", "overclaim"]


def grouped(counts):
    """Collapse a {verdict: n} dict into the four summary groups (exact + acceptable -> correct)."""
    return {
        "correct": counts["exact"] + counts["acceptable"],
        "incorrect": counts["incorrect"],
        "missing": counts["missing"],
        "overclaim": counts["overclaim"],
    }

# Column names in the gold and output CSVs (same as evaluate.main()).
GOLD_COLS = ("Pot_name", "Typology", "Start_date", "End_date", "Site_name")
OUT_COLS = ("pottery", "typology", "start_date", "end_date", "site_name")


def gload(path, potk, typk, sk, ek, sitek, present_only=False):
    """Like `evaluate.load()` (same normalisation, scope filter and present-only filter), but also
    keeps the RAW site/typology strings so the detail CSV can show what was actually in the files,
    not the lower-cased / normalised form used for comparison."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for d in csv.DictReader(f):
            if present_only and d.get("context_label", "") in ("absent", "comparison", "citation", "irrelevant"):
                continue
            _scope_txt = " ".join(str(d.get(k, "")) for k in
                                  (potk, "term_found_normalized_en", "Original_text", "original_text"))
            if ev._ROMAN_ONLY and not ev._roman_in_scope(d.get(sk), d.get(ek), _scope_txt):
                continue
            rows.append({
                "pot": d.get(potk, "") or "", "typ": ev.norm_typ(d.get(typk, "")),
                "s": ev.to_int(d.get(sk)), "e": ev.to_int(d.get(ek)),
                "site": (d.get(sitek, "") or "").strip().lower(),
                "raw_site": (d.get(sitek, "") or "").strip(),
                "raw_typ": (d.get(typk, "") or "").strip(),
            })
    return rows


# ── per-field verdicts from a pair of values (gold vs workflow) ──────────────────
def _present(v):
    return v not in (None, "")


def _site_tokens(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def v_site(g, p):
    gs, ps = g["site"], p["site"]
    if _present(gs) and _present(ps):
        if gs == ps:
            return "exact"
        # acceptable = a granularity difference: one site name's tokens are fully contained in the
        # other (e.g. "Voerendaal" vs "Voerendaal-Ten Hove", "Kerkrade" vs "Kerkrade (Kaalheide)").
        gt, pt = _site_tokens(gs), _site_tokens(ps)
        if gt and pt and (gt <= pt or pt <= gt):
            return "acceptable"
        return "incorrect"
    # Inside a matched pair: one side blank -> incorrect; both blank -> exact (agreed empty).
    return "exact" if not (_present(gs) or _present(ps)) else "incorrect"


def v_pottery(g, p):
    gh, ph = _present(ev.keyname(g["pot"])), _present(ev.keyname(p["pot"]))
    if gh and ph:
        if ev.keyname(g["pot"]) == ev.keyname(p["pot"]):
            return "exact"
        return "acceptable" if ev.pot_match(g, p) else "incorrect"   # ware family / token overlap
    # Inside a matched pair: one side blank -> incorrect; both blank -> exact.
    return "exact" if not (gh or ph) else "incorrect"


def v_typology(g, p):
    if _present(g["typ"]) and _present(p["typ"]):
        return "exact" if g["typ"] == p["typ"] else "incorrect"      # exact-or-incorrect only
    # Inside a matched pair: one side blank -> incorrect; both blank -> exact (often: neither typed).
    return "exact" if not (_present(g["typ"]) or _present(p["typ"])) else "incorrect"


def v_endpoint(gv, pv, strict):
    # `strict` (gold finding has a typology -> the typology is "master" and pins the date): the
    # endpoint must match EXACTLY, no +/-TOLERANCE leeway. The tolerance only applies to dates the
    # gold derived from text (no typology).
    if gv is not None and pv is not None:
        if gv == pv:
            return "exact"
        if not strict and abs(gv - pv) <= TOLERANCE:
            return "acceptable"
        return "incorrect"
    # Inside a matched pair: one endpoint blank -> incorrect; both blank -> exact (agreed undated).
    return "exact" if gv is None and pv is None else "incorrect"


def _disp(x):
    return "" if x is None else x


def pair_cells(g, p):
    """For a matched pair, return {field: (verdict, gold_value, workflow_value)} using raw display
    values."""
    strict = _present(g["typ"])   # gold has a typology -> dates must match exactly (typology is master)
    return {
        "site_name": (v_site(g, p), g["raw_site"], p["raw_site"]),
        "pottery": (v_pottery(g, p), g["pot"], p["pot"]),
        "typology": (v_typology(g, p), g["raw_typ"], p["raw_typ"]),
        "start_date": (v_endpoint(g["s"], p["s"], strict), _disp(g["s"]), _disp(p["s"])),
        "end_date": (v_endpoint(g["e"], p["e"], strict), _disp(g["e"]), _disp(p["e"])),
    }


def solo_cells(row, verdict, side):
    """For an unpaired record, every field gets `verdict`; the value sits on `side` ('gold' or
    'workflow') and the other side is blank."""
    vals = {
        "site_name": row["raw_site"], "pottery": row["pot"], "typology": row["raw_typ"],
        "start_date": _disp(row["s"]), "end_date": _disp(row["e"]),
    }
    if side == "gold":
        return {f: (verdict, vals[f], "") for f in FIELDS}
    return {f: (verdict, "", vals[f]) for f in FIELDS}


def main():
    global TOLERANCE
    ap = argparse.ArgumentParser(description="Granular per-field gold-vs-output evaluation")
    ap.add_argument("--report", help="restrict to one report")
    ap.add_argument("--tolerance", type=int, default=TOLERANCE,
                    help=f"+/- years for an 'acceptable' (non-exact) date endpoint (default {TOLERANCE})")
    ap.add_argument("--present-only", action="store_true",
                    help="grade only pipeline rows the classifier labelled present")
    ap.add_argument("--folder", default=ev._FOLDER,
                    help="reports batch folder name (default: %(default)s); scores "
                         "output_files/reports/<folder>/ vs input_files/gold_standards/<folder>/.")
    ap.add_argument("--summary-dir",
                    help="override the output directory of <report>.csv files to score "
                         "(e.g. a copy of an alternate run). Takes precedence over --folder.")
    ap.add_argument("--detail-csv", default=None,
                    help="per-finding detail output (default: output_files/evaluation/<stem>/granular_detail.csv)")
    ap.add_argument("--summary-csv", default=None,
                    help="wide per-report summary output (default: output_files/evaluation/<stem>/granular_summary.csv)")
    args = ap.parse_args()
    TOLERANCE = args.tolerance

    ev.GOLD_DIR, ev.OUT_DIR = ev._resolve_dirs(args.folder, args.summary_dir)

    # Default CSV location: output_files/evaluation/<stem>/, <stem> = name of the scored output set.
    out_base = EVAL_OUTPUT_BASE / ev.OUT_DIR.name
    detail_csv = Path(args.detail_csv) if args.detail_csv else out_base / "granular_detail.csv"
    summary_csv = Path(args.summary_csv) if args.summary_csv else out_base / "granular_summary.csv"
    print(f"[scoring summaries in] {ev.OUT_DIR}   (date tolerance +/-{TOLERANCE}y)\n")
    if args.present_only:
        print("[present-only] grading only rows with context_label == present\n")

    detail_rows = []
    summary_rows = []
    agg = {f: {v: 0 for v in VERDICTS} for f in FIELDS}      # agg[field][verdict] -> value count
    rec = dict(gold=0, matched=0, missing=0, overclaim=0)    # record-level tallies

    print("Per-field verdict counts — field VALUES, not findings "
          "(a missing/overclaim finding counts 5, one per field):")
    print("exact / acceptable / incorrect / missing / overclaim (E/A/I/M/O).")
    hdr = (f"{'report':10} {'gold':>4} {'mat':>4} {'mis':>4} {'ovc':>4} | "
           + " ".join(f"{f[:4]:>15}" for f in FIELDS))
    print(hdr)
    print("-" * len(hdr))

    for r in ev.reports(args.report):
        g = gload(ev.GOLD_DIR / f"{r}.csv", *GOLD_COLS)
        o = gload(ev.OUT_DIR / f"{r}.csv", *OUT_COLS, present_only=args.present_only)
        pairs, missing, overclaim = ev.match(g, o)

        per = {f: {v: 0 for v in VERDICTS} for f in FIELDS}     # value counts for this report

        def emit(cells):
            row = [r]
            for f in FIELDS:
                verdict, gv, wv = cells[f]
                per[f][verdict] += 1
                row += [verdict, gv, wv]
            detail_rows.append(row)

        for gg, pp in pairs:
            emit(pair_cells(gg, pp))
        for gg in missing:
            emit(solo_cells(gg, "missing", "gold"))
        for pp in overclaim:
            emit(solo_cells(pp, "overclaim", "workflow"))

        for f in FIELDS:
            for v in VERDICTS:
                agg[f][v] += per[f][v]
        rec["gold"] += len(g); rec["matched"] += len(pairs)
        rec["missing"] += len(missing); rec["overclaim"] += len(overclaim)

        cell = lambda f: "/".join(str(per[f][v]) for v in VERDICTS)
        print(f"{r:10} {len(g):>4} {len(pairs):>4} {len(missing):>4} {len(overclaim):>4} | "
              + " ".join(f"{cell(f):>15}" for f in FIELDS))

        # Per-field columns stay full 5-way; the row's trailing totals are grouped over VALUES.
        vtot = {grp: sum(grouped(per[f])[grp] for f in FIELDS) for grp in GROUPS}
        summary_rows.append([r]
                            + [per[f][v] for f in FIELDS for v in VERDICTS]
                            + [vtot[grp] for grp in GROUPS] + [sum(vtot.values())])

    print("-" * len(hdr))
    cell = lambda f: "/".join(str(agg[f][v]) for v in VERDICTS)
    print(f"{'TOTAL':10} {rec['gold']:>4} {rec['matched']:>4} {rec['missing']:>4} {rec['overclaim']:>4} | "
          + " ".join(f"{cell(f):>15}" for f in FIELDS))

    print("\n=== Per-field verdicts — counts are field VALUES, not findings "
          "(silver gold; overclaim = extra not in gold) ===")
    for f in FIELDS:
        c = agg[f]
        print(f"  {f:11}: exact {c['exact']:>4}  acceptable {c['acceptable']:>4}  "
              f"incorrect {c['incorrect']:>4}  missing {c['missing']:>4}  overclaim {c['overclaim']:>4}")
    print("\n=== Record tallies — counts are FINDINGS (whole records), not field values ===")
    print(f"  matched   : {rec['matched']:>4}  (gold find paired to an output row)")
    print(f"  missing   : {rec['missing']:>4}  (gold find not produced)")
    print(f"  overclaim : {rec['overclaim']:>4}  (produced, not in gold)")

    # ── write the two CSVs ───────────────────────────────────────────────────
    detail_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(detail_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["report"]
        for fld in FIELDS:
            header += [f"{fld}_verdict", f"{fld}_gold", f"{fld}_workflow"]
        w.writerow(header)
        w.writerows(detail_rows)

    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["report"]
                   + [f"{fld}_{v}" for fld in FIELDS for v in VERDICTS]
                   + [f"total_{grp}_values" for grp in GROUPS] + ["total_values"])
        w.writerows(summary_rows)
        vgrand = {grp: sum(grouped(agg[f])[grp] for f in FIELDS) for grp in GROUPS}
        w.writerow(["TOTAL"]
                   + [agg[fld][v] for fld in FIELDS for v in VERDICTS]
                   + [vgrand[grp] for grp in GROUPS] + [sum(vgrand.values())])

    print(f"\nDetail  ({len(detail_rows)} rows) -> {detail_csv}")
    print(f"Summary ({len(summary_rows)} reports) -> {summary_csv}")

    print("\nNote: these are the raw (un-adjudicated) per-field verdicts. The reported headline")
    print("(e.g. Claude 95.6% field-level correctness) applies a manual adjudication of borderline")
    print("cases on top of these, so it will not match exactly. See docs/research/results.md.")


if __name__ == "__main__":
    main()

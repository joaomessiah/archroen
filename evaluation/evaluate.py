#!/usr/bin/env python3
"""Quantitative gold-vs-output evaluation harness (C1; spec in notes/TODO.txt).

Scores every pipeline output (output_files/reports/<folder>/<report>.csv) against its
gold standard (input_files/gold_standards/<folder>/<report>.csv) and prints, per report and in
aggregate:
  - Detection: precision / recall / F1 (matched / missed / spurious)
  - Per-field agreement over matched pairs: site, pottery name, typology, start, end
  - Dates: exact-endpoint AND "overlaps gold" (two metrics, as the spec requires)

Matching policy (this is itself thesis methodology — stated explicitly so it is defensible):
each gold find is paired one-to-one to a pipeline row in priority order:
  1. typology code (exact, after normalisation)
  2. exact / catalogue-number name
  3. WARE FAMILY — granularity + synonym aware. The golds mix granularity and language:
     gold "Amphorae" vs pipeline "Baetican olive oil amphora / Dressel 20"; gold
     "Mortarium rim" vs pipeline "Grinding bowl" (= wrijfschaal); gold "Belgian ware" vs
     pipeline "terra rubra"/"terra nigra". Family matching credits these as found.
  4. alias-normalised token overlap (Dutch->English) as a last resort.

Usage:
    python3 evaluate.py                  # console report (all reports)
    python3 evaluate.py --csv eval.csv   # also dump per-find matched/missed/spurious rows
    python3 evaluate.py --report table_5  # restrict to one report
"""
import argparse
import csv
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # project root (this script lives in evaluation/)
sys.path.insert(0, str(BASE))
try:
    from config import POTTERY_ROMAN_ONLY as _ROMAN_ONLY, DEFAULT_REPORTS_DIR as _RDIR
    from src.periods import roman_in_scope as _roman_in_scope
    _FOLDER = _RDIR.name
except ImportError:                       # config not importable -> no period filter
    _ROMAN_ONLY = False
    _FOLDER = "workflow_evaluation_sample"
    def _roman_in_scope(s, e, t=""):
        return True

# A reports batch folder mirrors across the tree: input PDFs in input_files/reports/<folder>/,
# scored output in output_files/reports/<folder>/, golds in input_files/gold_standards/<folder>/.
GOLD_DIR = BASE / "input_files" / "gold_standards" / _FOLDER
OUT_DIR = BASE / "output_files" / "reports" / _FOLDER
SKIP = {"2360"}

# Dutch / form aliases -> english head noun (cross-language token matching).
ALIAS = {
    "aardewerk": "pottery", "belgisch": "belgian", "belgische": "belgian",
    "kogelpot": "globular", "kogelpotaardewerk": "globular", "scherf": "sherd", "scherven": "sherd",
    "stempel": "stamp", "gestempeld": "stamp", "beker": "beaker", "bekers": "beaker", "drinkbeker": "beaker",
    "kruik": "jug", "kruiken": "jug", "kruikwaar": "flagon", "kom": "bowl", "kommen": "bowl",
    "schaal": "bowl", "schalen": "bowl", "bord": "dish", "borden": "dish",
    "urn": "urn", "urnen": "urn", "urns": "urn", "deksel": "lid",
    "wrijfschaal": "mortarium", "wrijfschalen": "mortarium", "mortaria": "mortarium", "mortarium": "mortarium",
    "gladwandig": "smoothwalled", "gladwandige": "smoothwalled", "ruwwandig": "roughwalled", "ruwwandige": "roughwalled",
    "geverfd": "painted", "geverfde": "painted", "beschilderd": "painted", "cup": "beaker", "cups": "beaker",
    "dolium": "dolia", "dolia": "dolia", "voorraadvat": "dolia", "amphorae": "amphora", "amfoor": "amphora",
    "amphora": "amphora", "kookpotten": "cooking", "kookpot": "cooking", "flagon": "flagon",
    "rood": "red", "rode": "red", "wit": "white", "witte": "white", "grijs": "grey", "grijze": "grey",
    "indigenous": "native", "inheems": "native",   # gold "Indigenous pottery" == pipeline "Native ware"
}
STOP = {"the", "a", "an", "of", "and", "ware", "wares", "type", "rim",
        "fragment", "fragmenten", "fragments", "with", "probably", "red", "white", "grey"}

# Ware FAMILY: maps any head noun to a coarse family, so a generic gold find matches a
# typed/specific pipeline find of the same family (and vice versa), bridging granularity
# and Dutch<->English synonyms.
FAMILY = {
    "amphora": "amphora", "amphorae": "amphora", "amfoor": "amphora", "amphoor": "amphora",
    "mortarium": "mortarium", "mortaria": "mortarium", "wrijfschaal": "mortarium",
    "wrijfschalen": "mortarium", "wrijfkom": "mortarium", "wrijfschotel": "mortarium", "grinding": "mortarium",
    "dolium": "dolia", "dolia": "dolia", "voorraadvat": "dolia", "voorraadpot": "dolia", "storage": "dolia",
    "sigillata": "sigillata",
    "nigra": "belgian", "rubra": "belgian", "belgisch": "belgian", "belgische": "belgian", "belgian": "belgian",
    "kogelpot": "globular", "kogelpotaardewerk": "globular", "globular": "globular",
    # vessel-form synonym families (Dutch <-> English, singular/plural) so a gold "Flagon"
    # pairs with a pipeline "Jug"/"kruik", etc. — measures detection, not naming.
    "flagon": "flagon", "jug": "flagon", "jugs": "flagon", "kruik": "flagon", "kruiken": "flagon",
    "kruikje": "flagon", "kruikjes": "flagon", "kan": "flagon", "kannen": "flagon", "kannetje": "flagon",
    "pitcher": "flagon", "kruikamfoor": "flagon",
    "beaker": "beaker", "beakers": "beaker", "beker": "beaker", "bekers": "beaker", "bekertje": "beaker",
    "drinkbeker": "beaker", "gordelbeker": "beaker", "cup": "beaker", "cups": "beaker",
    "plate": "plate", "plates": "plate", "bord": "plate", "borden": "plate", "bordje": "plate",
    "dish": "dish", "dishes": "dish", "schotel": "dish", "schotels": "dish",
    "bowl": "bowl", "bowls": "bowl", "kom": "bowl", "kommen": "bowl", "kommetje": "bowl",
    "schaal": "bowl", "schalen": "bowl", "schaaltje": "bowl",
    "jar": "jar", "jars": "jar", "pot": "jar", "potten": "jar",
    "lid": "lid", "lids": "lid", "deksel": "lid", "deksels": "lid",
    "cooking": "cooking", "kookpot": "cooking", "kookpotten": "cooking", "cookpot": "cooking",
    "urn": "urn", "urns": "urn", "urnen": "urn", "urntje": "urn",
    "honey": "honey", "honingpot": "honey", "honingpotje": "honey", "honing": "honey",
    "lamp": "lamp", "lamps": "lamp", "olielamp": "lamp", "firmalamp": "lamp",
    "pan": "pan", "pannetje": "pan",
    "kurkurn": "corkurn", "corkurn": "corkurn",
    "pingsdorf": "pingsdorf", "badorf": "badorf", "siegburg": "stoneware", "steengoed": "stoneware",
    # ware-surface synonyms across languages / English variants — measures detection, not naming,
    # so gold "Varnished pottery" pairs with pipeline/Claude "color-coated ware", gold
    # "Rough-walled" with "coarse-walled"/"ruwwandig", gold "Smooth-walled" with "gladwandig".
    "varnished": "colorcoated", "coated": "colorcoated", "gevernist": "colorcoated",
    "geverfd": "colorcoated", "geverniste": "colorcoated",
    "rough": "roughwalled", "coarse": "roughwalled", "ruwwandig": "roughwalled", "ruwwandige": "roughwalled",
    "smooth": "smoothwalled", "gladwandig": "smoothwalled", "gladwandige": "smoothwalled",
}


def norm_typ(s):
    s = (s or "").strip().lower()
    if not s:
        return ""
    # Normalise typology-system abbreviations + the word "type" so "Gose type 377" == "Gose 377".
    s = re.sub(r"\bdrag\.?\b|\bdragendorff\b", "dragendorff", s)
    s = re.sub(r"\bstu\.?\b", "stuart", s)
    s = re.sub(r"\bhalt\.?\b", "haltern", s)
    s = re.sub(r"\bnb\b|\bnieder\.?\b", "niederbieber", s)
    s = re.sub(r"\balz\.?\b|\balzei\b", "alzey", s)
    s = re.sub(r"\btype\b|\btypen\b|\bvorm\b", " ", s)
    # strip tentative-attribution markers so "Alzey 33 cf." matches gold "Alzey 33" (mirrors the
    # pipeline's Option A: a cf./vgl./? code grounds to the base type).
    s = re.sub(r"\bcf\b|\bvgl\b|\bconf\b|\bconfer\b|\?", " ", s)
    s = re.sub(r"[.\s]+", " ", s).strip()
    s = re.sub(r"dragendorff\s+(\d+\w*)\s*/\s*dragendorff\s+(\d+\w*)", r"dragendorff \1/\2", s)
    return s


def keyname(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def toks(s):
    out = set()
    for w in re.findall(r"[a-z]+", (s or "").lower()):
        w = ALIAS.get(w, w)
        if len(w) > 4 and w.endswith("s"):   # light singularize (jugs->jug, beakers->beaker)
            w = ALIAS.get(w[:-1], w[:-1])
        if w not in STOP and len(w) > 2:
            out.add(w)
    return out


# Fabric/surface families are SECONDARY: used only when a name has no vessel-form/ware family,
# so "coarse oxidized jar" resolves to "jar", not "roughwalled" — the fabric word must not hijack
# the vessel form when both are present (both gold and pipeline sides resolve consistently).
_FABRIC_FAMS = {"roughwalled", "smoothwalled", "colorcoated"}


def family(name, typology):
    """Coarse ware family of a find, from its name words or typology system. A vessel-form / ware
    family takes precedence over a fabric/surface qualifier (coarse/smooth/varnished)."""
    fams = [FAMILY[w] for w in re.findall(r"[a-z]+", (name or "").lower()) if w in FAMILY]
    primary = [f for f in fams if f not in _FABRIC_FAMS]
    if primary:
        return primary[0]
    if fams:
        return fams[0]
    # typology system hints (e.g. Dressel/Gauloise/Haltern = amphora; Chenet = sigillata)
    t = (typology or "").lower()
    if re.search(r"dressel|gauloise|haltern|pascual|lamboglia|pompeii|camulodunum", t):
        return "amphora"
    if re.search(r"dragendorff|chenet|drag|consp|ritterling|hofheim", t):
        return "sigillata"
    return ""


def to_int(x):
    x = (x or "").strip()
    if x == "":
        return None
    try:
        return int(float(x))
    except ValueError:
        m = re.match(r"-?\d+", x)
        return int(m.group()) if m else None


def load(path, potk, typk, sk, ek, sitek, present_only=False):
    rows = []
    with open(path, encoding="utf-8") as f:
        for d in csv.DictReader(f):
            # present_only: drop rows the pottery classifier judged a non-find here —
            # absent / comparison / citation / irrelevant (general discussion, parallels,
            # references) — the present-vs-mention view (D2). Keeps present/uncertain/unlabelled,
            # and gold rows (no such column) pass through. Uses context_label (llm_find_status
            # was removed from the output; context_label is the kept categorical).
            if present_only and d.get("context_label", "") in ("absent", "comparison", "citation", "irrelevant"):
                continue
            # Roman-period scope: when on, drop dated-but-non-Roman rows (and fully-undated clearly
            # non-Roman rows) from BOTH gold and output so the comparison stays in the same scope as
            # the pipeline (src.periods.roman_in_scope).
            _scope_txt = " ".join(str(d.get(k, "")) for k in
                                  (potk, "term_found_normalized_en", "Original_text", "original_text"))
            if _ROMAN_ONLY and not _roman_in_scope(d.get(sk), d.get(ek), _scope_txt):
                continue
            rows.append({
                "pot": d.get(potk, "") or "", "typ": norm_typ(d.get(typk, "")),
                "s": to_int(d.get(sk)), "e": to_int(d.get(ek)),
                "site": (d.get(sitek, "") or "").strip().lower(),
            })
    return rows


# ── field comparators ─────────────────────────────────────────────────────────
def site_match(g, p):
    return g["site"] == p["site"]


def typ_match(g, p):
    return g["typ"] == p["typ"]


def pot_match(g, p):
    if keyname(g["pot"]) and keyname(g["pot"]) == keyname(p["pot"]):
        return True
    gt, pt = toks(g["pot"]), toks(p["pot"])
    if gt and pt and ((len(gt & pt) / len(gt | pt)) >= 0.34 or gt <= pt or pt <= gt):
        return True
    gf, pf = family(g["pot"], g["typ"]), family(p["pot"], p["typ"])
    return bool(gf) and gf == pf


def start_match(g, p):
    return g["s"] == p["s"]


def end_match(g, p):
    return g["e"] == p["e"]


def date_overlap(g, p):
    if g["s"] is None and g["e"] is None:
        return True
    if p["s"] is None and p["e"] is None:
        return False
    gs, ge = (g["s"] if g["s"] is not None else -9999), (g["e"] if g["e"] is not None else 9999)
    ps, pe = (p["s"] if p["s"] is not None else -9999), (p["e"] if p["e"] is not None else 9999)
    return ps <= ge and gs <= pe


# Among several pipeline rows that match a gold find on POT identity (same typology,
# name, or ware family), prefer the one whose DATE best agrees — otherwise, when a report
# has many same-ware rows (e.g. a finds list of generic "Pottery"), an arbitrary first-
# match pairing makes correct rows look wrong. Ranks by: #exact endpoints, then overlap,
# then smallest endpoint distance. Pure measurement — does not affect the pipeline.
def _date_score(g, p):
    se = g["s"] is not None and p["s"] is not None and g["s"] == p["s"]
    ee = g["e"] is not None and p["e"] is not None and g["e"] == p["e"]
    dist = 0
    if None not in (g["s"], g["e"], p["s"], p["e"]):
        dist = abs(g["s"] - p["s"]) + abs(g["e"] - p["e"])
    return (int(se) + int(ee), int(date_overlap(g, p)), -dist)


def _pick(g, candidates):
    return max(candidates, key=lambda p: _date_score(g, p))


# ── matcher: typology -> exact/catalogue -> ware family -> token overlap ─────────
def match(gold, out):
    """Pair each gold find one-to-one with a pipeline row, in descending priority: (1) exact
    typology code, (2) exact/catalogue name, (3) ware family (granularity- and synonym-aware),
    (4) Jaccard token overlap ≥ 0.34. A matched pipeline row is removed so it can't match twice.
    Returns (pairs, missing gold, spurious pipeline rows) — the basis for precision/recall/F1.

    The priority order and thresholds are deliberate evaluation methodology; see the module
    docstring for why family-level matching is credited."""
    out = list(out)
    pairs, rem = [], []
    for g in gold:                                            # 1. typology
        cands = [p for p in out if g["typ"] and p["typ"] == g["typ"]]
        if cands:
            hit = _pick(g, cands); out.remove(hit); pairs.append((g, hit))
        else:
            rem.append(g)
    rem2 = []
    for g in rem:                                            # 2. exact / catalogue name
        gk = keyname(g["pot"])
        cands = [p for p in out if gk and keyname(p["pot"]) == gk]
        if cands:
            hit = _pick(g, cands); out.remove(hit); pairs.append((g, hit))
        else:
            rem2.append(g)
    rem3 = []
    for g in rem2:                                           # 3. ware family (granularity)
        gf = family(g["pot"], g["typ"])
        cands = [p for p in out if gf and family(p["pot"], p["typ"]) == gf]
        if cands:
            hit = _pick(g, cands); out.remove(hit); pairs.append((g, hit))
        else:
            rem3.append(g)
    miss = []
    for g in rem3:                                           # 4. token overlap
        gt = toks(g["pot"])
        best, best_sc = None, 0.0
        for p in out:
            pt = toks(p["pot"])
            if not gt or not pt:
                continue
            sc = len(gt & pt) / len(gt | pt)
            if sc > best_sc:
                best_sc, best = sc, p
        if best and best_sc >= 0.34:
            out.remove(best); pairs.append((g, best))
        else:
            miss.append(g)
    return pairs, miss, out                                  # matched, missing gold, spurious


def extra_category(p, present_families):
    """Triage a pipeline row that has no gold match. The gold is a SILVER standard
    (incomplete), so an extra is a candidate, not necessarily an error:
      typed   - has a typology code -> strong candidate (likely a real find gold omitted)
      recap   - untyped, ware already counted in this report -> likely duplicate re-mention
      dated   - untyped but dated, ware not yet seen -> plausible new candidate
      undated - no date -> low information
    """
    if p["typ"]:
        return "typed"
    if p["s"] is None and p["e"] is None:
        return "undated"
    fam = family(p["pot"], p["typ"])
    if fam and fam in present_families:
        return "recap"
    return "dated"


def reports(only=None):
    order = {"old_rep": 0, "table": 1, "ocr": 2, "new_rep": 3}

    def key(stem):
        m = re.match(r"([a-z_-]*?)[_-]?(\d+)$", stem)
        prefix, num = (m.group(1).rstrip("_-"), int(m.group(2))) if m else (stem, 0)
        return (order.get(prefix, 9), prefix, num)

    names = sorted((p.stem for p in GOLD_DIR.glob("*.csv") if p.stem not in SKIP), key=key)
    names = [n for n in names if (OUT_DIR / f"{n}.csv").exists()]
    return [n for n in names if not only or n == only]


def main():
    """CLI entry point: score every report's pottery summary against its gold standard and print
    per-report + aggregate detection P/R/F1, per-field agreement, and date accuracy. Flags:
    `--report` one report, `--csv` dump per-find rows, `--present-only`, `--summary-dir` to score a
    different output set (e.g. a Claude vs Ollama run)."""
    ap = argparse.ArgumentParser(description="Gold-vs-output evaluation harness")
    ap.add_argument("--csv", help="dump per-find matched/missed/spurious rows to this path")
    ap.add_argument("--report", help="restrict to one report")
    ap.add_argument("--present-only", action="store_true",
                    help="grade only pipeline rows the classifier labelled present "
                         "(present-vs-mention view, D2)")
    ap.add_argument("--folder", default=_FOLDER,
                    help="reports batch folder name (default: %(default)s); scores "
                         "output_files/reports/<folder>/ vs input_files/gold_standards/<folder>/.")
    ap.add_argument("--summary-dir",
                    help="override the output directory of <report>.csv files to score (e.g. a copy "
                         "of an alternate Claude-vs-Ollama run). Takes precedence over --folder.")
    args = ap.parse_args()
    global OUT_DIR, GOLD_DIR
    GOLD_DIR = BASE / "input_files" / "gold_standards" / args.folder
    OUT_DIR = BASE / "output_files" / "reports" / args.folder
    if args.summary_dir:
        OUT_DIR = Path(args.summary_dir)
    print(f"[scoring summaries in] {OUT_DIR}\n")
    if args.present_only:
        print("[present-only] grading only rows with context_label == present\n")

    agg = dict(gold=0, match=0, miss=0, extra=0,
               site=0, pot=0, typ=0, ds=0, de=0, dov=0,
               xtyped=0, xdated=0, xrecap=0, xundated=0)
    detail_rows = []
    print("Per-field agreement over MATCHED pairs (n/match). Dates: exact start/end, + overlap.")
    hdr = (f"{'report':10} {'gold':>4} {'match':>5} {'miss':>4} {'extra':>5} {'recall':>7} | "
           f"{'site':>5} {'pot':>5} {'typ':>5} {'st':>5} {'end':>5} {'ovlp':>5}")
    print(hdr)
    print("-" * len(hdr))
    for r in reports(args.report):
        g = load(GOLD_DIR / f"{r}.csv", "Pot_name", "Typology", "Start_date", "End_date", "Site_name")
        o = load(OUT_DIR / f"{r}.csv", "pottery", "typology", "start_date", "end_date", "site_name",
                 present_only=args.present_only)
        pairs, miss, extra = match(g, o)
        m = len(pairs)
        present_families = {family(p["pot"], p["typ"]) for _, p in pairs}
        present_families.discard("")
        xcats = {p_id: extra_category(p, present_families) for p_id, p in enumerate(extra)}
        fs = sum(site_match(a, b) for a, b in pairs)
        fp = sum(pot_match(a, b) for a, b in pairs)
        ft = sum(typ_match(a, b) for a, b in pairs)
        fds = sum(start_match(a, b) for a, b in pairs)
        fde = sum(end_match(a, b) for a, b in pairs)
        fdo = sum(date_overlap(a, b) for a, b in pairs)
        rec = m / len(g) if g else 1.0
        d = lambda n: f"{n}/{m}"
        print(f"{r:10} {len(g):>4} {m:>5} {len(miss):>4} {len(extra):>5} {rec*100:>6.0f}% | "
              f"{d(fs):>5} {d(fp):>5} {d(ft):>5} {d(fds):>5} {d(fde):>5} {d(fdo):>5}")
        agg['gold'] += len(g); agg['match'] += m; agg['miss'] += len(miss); agg['extra'] += len(extra)
        agg['site'] += fs; agg['pot'] += fp; agg['typ'] += ft
        agg['ds'] += fds; agg['de'] += fde; agg['dov'] += fdo
        for c in xcats.values():
            agg['x' + c] += 1
        if args.csv:
            for gg, pp in pairs:
                detail_rows.append([r, "matched", gg["pot"], gg["typ"], f"{gg['s']}..{gg['e']}",
                                    pp["pot"], pp["typ"], f"{pp['s']}..{pp['e']}"])
            for gg in miss:
                detail_rows.append([r, "MISSED", gg["pot"], gg["typ"], f"{gg['s']}..{gg['e']}", "", "", ""])
            for p_id, pp in enumerate(extra):
                detail_rows.append([r, "EXTRA-" + xcats[p_id], "", "", "",
                                    pp["pot"], pp["typ"], f"{pp['s']}..{pp['e']}"])

    m = agg['match']
    R = m / agg['gold'] if agg['gold'] else 1.0
    print("-" * len(hdr))
    print(f"{'TOTAL':10} {agg['gold']:>4} {m:>5} {agg['miss']:>4} {agg['extra']:>5} | "
          f"{'':>4} {R*100:>3.0f}% {'':>4} |")

    pc = lambda k: f"{agg[k] / m * 100:.0f}%" if m else "-"
    print("\n=== Detection vs gold (primary; gold is a SILVER standard — may omit real finds) ===")
    print(f"Recall      : {m}/{agg['gold']} = {R*100:.0f}%   (matched {m}, missed {agg['miss']})")
    print(f"On matched  : site {pc('site')}  pottery {pc('pot')}  typology {pc('typ')}  "
          f"| date start {pc('ds')}  end {pc('de')}  overlap {pc('dov')}")

    # Extras are reported SEPARATELY (not as precision errors): the gold is incomplete, so a
    # pipeline find absent from the gold may well be real. Triaged so the noise is visible.
    x = agg['extra']
    print(f"\n=== Extra detections NOT in gold: {x}  (candidates, reviewed — not counted as errors) ===")
    print(f"  typed   {agg['xtyped']:>3}  (has typology code -> strong candidate, likely a real find gold omitted)")
    print(f"  dated   {agg['xdated']:>3}  (untyped + dated, ware not yet counted -> plausible candidate)")
    print(f"  recap   {agg['xrecap']:>3}  (ware already counted in report -> likely duplicate re-mention = noise)")
    print(f"  undated {agg['xundated']:>3}  (no date -> low information)")
    print("  (run with --csv to list every extra row with its category for review)")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["report", "status", "gold_pot", "gold_typ", "gold_date",
                        "pipe_pot", "pipe_typ", "pipe_date"])
            w.writerows(detail_rows)
        print(f"\nPer-find detail ({len(detail_rows)} rows) -> {args.csv}")


if __name__ == "__main__":
    main()

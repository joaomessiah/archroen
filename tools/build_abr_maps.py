#!/usr/bin/env python3
"""Build the ABR standard-vocabulary map CSVs from the frozen RDF snapshot.

This is a BUILD-TIME tool. It requires ``rdflib`` (installed in the venv) and reads the
frozen dump at ``data/vocabularies/standards/abr/source/abr_dump_*.trig.gz``. The pipeline
runtime never imports this module or rdflib — it only reads the generated CSVs.

It emits three ``*_generated.csv`` files under ``data/vocabularies/standards/abr/``:

  * ``ware_map_generated.csv``     — ABR ceramic categories (ware/bakselgroep): label + URI
  * ``form_map_generated.csv``     — ABR vessel forms: code + label + URI
  * ``combined_map_generated.csv`` — ABR ceramic combiterms (ware+form+typology): code, label,
                                     URI, and the ware/form/typology it decomposes into

Hand curation (English aliases for matching the pipeline's ware_type/vessel_form strings, the
SIKB Roman ware codes, and any corrections) lives in the sibling ``*_overrides.csv`` files and
is merged on top of the generated rows by ``merge_overrides`` — so regenerating never destroys
manual work.

ABR model (verified against the snapshot):
  * Ware  = concept ``rnce:CeramicCategoryAbr`` linked from a combiterm via ``hasCeramicCategoryAbr``
            (Dutch prefLabel, no native short code).
  * Combiterm = ``rnce:ArtefactAbr`` node that has a ``hasCeramicCategoryAbr`` link; its
            ``skos:notation`` is the code (e.g. ``TSKOM.DR37``), prefLabel the Dutch label.
  * Form  = first ``skos:broader`` ancestor of the combiterm that has NO ceramic-category link
            (the generic vessel form, e.g. ``KOM.KOM`` / "kom").
  * Status: keep only ``definitief`` (skip vervallen / kandidaat / gidsterm).
  * Periods are intentionally NOT extracted (the pipeline owns dating).

Run:  .venv/bin/python3 tools/build_abr_maps.py
"""
from __future__ import annotations

import csv
import glob
import gzip
import os
import re
import sys

import rdflib
from rdflib import Namespace, RDF, Literal, URIRef

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
RNCE = Namespace("https://data.cultureelerfgoed.nl/id/rnce#")
STATUS_DEFINITIEF = URIRef(
    "https://data.cultureelerfgoed.nl/term/id/abr/aad68581-3960-4faf-9758-8ff6d65810d3"
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ABR_DIR = os.path.join(ROOT, "data", "vocabularies", "standards", "abr")
SOURCE_GLOB = os.path.join(ABR_DIR, "source", "abr_dump_*.trig.gz")


def load_graph() -> rdflib.Graph:
    """Load the newest frozen ABR ``.trig.gz`` dump into a single flattened rdflib.Graph."""
    paths = sorted(glob.glob(SOURCE_GLOB))
    if not paths:
        sys.exit(f"No ABR dump found at {SOURCE_GLOB}")
    dump = paths[-1]
    print(f"Loading {os.path.relpath(dump, ROOT)} ...")
    ds = rdflib.Dataset()
    with gzip.open(dump, "rt", encoding="utf-8") as fh:
        ds.parse(fh, format="trig")
    g = rdflib.Graph()
    for q in ds.quads((None, None, None, None)):
        g.add(q[:3])
    print(f"  {len(g)} triples")
    return g


# rdflib iterates multi-valued properties in an unstable order, so every "take one value" below
# sorts first: the build is then byte-reproducible (the chosen label/category/notation never depends
# on iteration order). Nodes normally carry a single value here; sorting only fixes the rare node
# that carries several.
def pref_label(g, s):
    labels = sorted(str(o) for o in g.objects(s, SKOS.prefLabel))
    return labels[0] if labels else ""


def notation(g, s):
    vals = sorted(str(o) for o in g.objects(s, SKOS.notation))
    return vals[0] if vals else ""


def ceramic_category(g, s):
    cats = sorted(g.objects(s, RNCE.hasCeramicCategoryAbr), key=str)
    return cats[0] if cats else None


def is_definitief(g, s):
    return STATUS_DEFINITIEF in set(g.objects(s, RNCE.hasConceptStatus))


def form_of(g, s):
    """First broader-ancestor without a ceramic-category link = the generic vessel form."""
    cur, seen = s, set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        broaders = sorted(g.objects(cur, SKOS.broader), key=str)
        if not broaders:
            return None
        nxt = broaders[0]
        if ceramic_category(g, nxt) is None:
            return nxt
        cur = nxt
    return None


# Typology spelled out in the combiterm label, e.g.
#   "Terra sigillata kom - Dragendorff 37" -> "Dragendorff 37"
#   "Terra sigillata bord- Curle 15, Midden-Oostgallisch" -> "Curle 15, Midden-Oostgallisch"
def typology_from_label(label: str) -> str:
    # split on the first dash that separates "<ware> <form>" from "<typology>"
    m = re.search(r"-\s+", label)
    if not m:
        return ""
    return label[m.end():].strip()


# Generic open-vessel umbrella forms. ABR files specific open shapes (kom, bord, kop) under the
# broad "bak" category, so form_of() (which walks to the first category-less ancestor) lands on the
# umbrella instead of the specific shape the combiterm itself names. Refine those from the label.
_GENERIC_FORMS = {"BAK", "VAATWERK"}


def _label_form_word(label: str) -> str:
    """The form shape named in a combiterm label, e.g. 'Terra sigillata kom - Dragendorff 27' -> 'kom',
    'Belgisch grijs:bord - Holwerda 161' -> 'bord'."""
    base = re.split(r"\s+-\s+", label)[0].split(",")[0]
    seg = base.split(":")[-1] if ":" in base else base
    toks = seg.split()
    return toks[-1].lower() if toks else ""


def build_rows(g):
    """Extract the three map tables from the graph as ``(combined, ware_rows, form_rows)``.

    ``combined`` has one row per *definitief* ceramic combiterm (code, label, URI, and the ware /
    form / typology it decomposes into); ``ware_rows`` and ``form_rows`` are the distinct ABR
    ceramic categories and vessel forms it references, ready for the SIKB-code/alias overrides.
    Generic open-vessel "bak"/"vaatwerk" forms are refined to the specific shape (kom/bord/kop) the
    combiterm's own label names.
    """
    # iterate subjects in a stable (sorted) order so the build is reproducible
    subjects = sorted(g.subjects(RDF.type, RNCE.ArtefactAbr), key=str)
    ceramic = [
        s for s in subjects
        if ceramic_category(g, s) is not None and is_definitief(g, s)
    ]
    # index every category-less form node by its plain label, so a generic-BAK combiterm can be
    # refined to the specific open shape (kom/bord/kop) its own label names.
    form_by_label = {}
    for s in subjects:
        if ceramic_category(g, s) is None:
            l = pref_label(g, s).lower().strip()
            if l:
                form_by_label.setdefault(l, s)
    combined, wares, forms = [], {}, {}
    for s in ceramic:
        cc = ceramic_category(g, s)
        fm = form_of(g, s)
        # refine the generic open-vessel umbrella to the specific shape the label names
        if fm is not None and notation(g, fm) in _GENERIC_FORMS:
            spec = form_by_label.get(_label_form_word(pref_label(g, s)))
            if spec is not None and notation(g, spec) not in _GENERIC_FORMS:
                fm = spec
        ware_label = pref_label(g, cc) if cc else ""
        ware_uri = str(cc) if cc else ""
        form_code = notation(g, fm) if fm else ""
        form_label = pref_label(g, fm) if fm else ""
        form_uri = str(fm) if fm else ""
        combined.append({
            "abr_combined_code": notation(g, s),
            "combined_label_nl": pref_label(g, s),
            "combined_uri": str(s),
            "ware_label_nl": ware_label,
            "ware_uri": ware_uri,
            "form_code": form_code,
            "form_label_nl": form_label,
            "typology_abr": typology_from_label(pref_label(g, s)),
        })
        if ware_uri and ware_uri not in wares:
            wares[ware_uri] = {
                "abr_ware_code": "",          # filled from SIKB concordance via overrides
                "ware_label_nl": ware_label,
                "ware_uri": ware_uri,
                "en_aliases": "",             # filled via overrides (pipeline ware_type strings)
                "needs_review": "",           # set per-alias by overrides; blank = no alias to review
            }
        if form_uri and form_uri not in forms:
            forms[form_uri] = {
                "abr_form_code": form_code,
                "form_label_nl": form_label,
                "form_uri": form_uri,
                "en_aliases": "",             # filled via overrides (pipeline vessel_form strings)
                "needs_review": "",
            }
    combined.sort(key=lambda r: r["abr_combined_code"])
    ware_rows = sorted(wares.values(), key=lambda r: r["ware_label_nl"])
    form_rows = sorted(forms.values(), key=lambda r: (r["form_label_nl"], r["abr_form_code"]))
    return combined, ware_rows, form_rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"  wrote {os.path.relpath(path, ROOT)}  ({len(rows)} rows)")


def _read_overrides(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _merge_aliases(existing, new):
    seen = [a for a in existing.split("|") if a]
    for a in (new or "").split("|"):
        a = a.strip()
        if a and a not in seen:
            seen.append(a)
    return "|".join(seen)


def merge_ware(generated, overrides_path):
    """Merge ware overrides (keyed by ware_label_nl) onto generated ware rows.

    Override rows with a blank ware_label_nl are English terms that don't map to any ABR
    ware; they are appended as orphan rows so the unresolved cases stay visible for review.
    """
    by_label = {r["ware_label_nl"]: r for r in generated}
    orphans = []
    for ov in _read_overrides(overrides_path):
        label = ov.get("ware_label_nl", "").strip()
        target = by_label.get(label) if label else None
        if target is None:
            orphans.append({
                "abr_ware_code": ov.get("abr_ware_code", ""),
                "ware_label_nl": label,
                "ware_uri": "",
                "en_aliases": ov.get("en_aliases", ""),
                "needs_review": ov.get("needs_review", "1"),
                "notes": ov.get("notes", ""),
            })
            continue
        if ov.get("abr_ware_code"):
            target["abr_ware_code"] = ov["abr_ware_code"]
        target["en_aliases"] = _merge_aliases(target.get("en_aliases", ""), ov.get("en_aliases", ""))
        # needs_review: a row stays flagged if any contributing override flags it
        nr = ov.get("needs_review", "")
        if nr == "1" or target.get("needs_review", "") == "1":
            target["needs_review"] = "1"
        elif nr == "0":
            target["needs_review"] = "0"
        notes = ov.get("notes", "")
        if notes:
            target["notes"] = (target.get("notes", "") + "; " + notes).strip("; ")
    return generated + orphans


def merge_form(generated, overrides_path):
    """Merge form overrides (keyed by abr_form_code) onto generated form rows."""
    by_code = {r["abr_form_code"]: r for r in generated}
    orphans = []
    for ov in _read_overrides(overrides_path):
        code = ov.get("abr_form_code", "").strip()
        target = by_code.get(code) if code else None
        if target is None:
            orphans.append({
                "abr_form_code": code, "form_label_nl": "", "form_uri": "",
                "en_aliases": ov.get("en_aliases", ""),
                "needs_review": ov.get("needs_review", "1"), "notes": ov.get("notes", ""),
            })
            continue
        target["en_aliases"] = _merge_aliases(target.get("en_aliases", ""), ov.get("en_aliases", ""))
        if ov.get("needs_review") == "1":
            target["needs_review"] = "1"
        notes = ov.get("notes", "")
        if notes:
            target["notes"] = (target.get("notes", "") + "; " + notes).strip("; ")
    return generated + orphans


def main():
    """Build all six map CSVs: the three ``*_generated.csv`` extracts, then the three runtime maps
    (``ware_map.csv`` / ``form_map.csv`` / ``combined_map.csv``) = generated + manual overrides."""
    g = load_graph()
    combined, wares, forms = build_rows(g)
    print(f"ceramic combiterms: {len(combined)} | wares: {len(wares)} | forms: {len(forms)}")

    # 1. pure extract from the frozen dump
    write_csv(
        os.path.join(ABR_DIR, "ware_map_generated.csv"), wares,
        ["abr_ware_code", "ware_label_nl", "ware_uri", "en_aliases", "needs_review"],
    )
    write_csv(
        os.path.join(ABR_DIR, "form_map_generated.csv"), forms,
        ["abr_form_code", "form_label_nl", "form_uri", "en_aliases", "needs_review"],
    )
    write_csv(
        os.path.join(ABR_DIR, "combined_map_generated.csv"), combined,
        ["abr_combined_code", "combined_label_nl", "combined_uri",
         "ware_label_nl", "ware_uri", "form_code", "form_label_nl", "typology_abr"],
    )

    # 2. final maps = generated + manual overrides (the runtime reads these)
    ware_final = merge_ware([dict(r, notes="") for r in wares],
                            os.path.join(ABR_DIR, "ware_map_overrides.csv"))
    form_final = merge_form([dict(r, notes="") for r in forms],
                            os.path.join(ABR_DIR, "form_map_overrides.csv"))
    write_csv(
        os.path.join(ABR_DIR, "ware_map.csv"), ware_final,
        ["abr_ware_code", "ware_label_nl", "ware_uri", "en_aliases", "needs_review", "notes"],
    )
    write_csv(
        os.path.join(ABR_DIR, "form_map.csv"), form_final,
        ["abr_form_code", "form_label_nl", "form_uri", "en_aliases", "needs_review", "notes"],
    )
    write_csv(
        os.path.join(ABR_DIR, "combined_map.csv"), combined,
        ["abr_combined_code", "combined_label_nl", "combined_uri",
         "ware_label_nl", "ware_uri", "form_code", "form_label_nl", "typology_abr"],
    )


if __name__ == "__main__":
    main()

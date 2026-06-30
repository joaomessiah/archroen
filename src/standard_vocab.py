"""Layer 7 tail: map each pottery find to a standard controlled vocabulary (ABR).

Deterministic, mode-independent post-processing. It reads the find's typology / pottery /
text — all already present in the produced summary — and appends standardised columns:

    std_vocabulary, std_ware_code, std_ware_label,
    std_form_code, std_form_label, std_combined_code, std_combined_label

These columns are *unscored* (interoperability only) and never affect the pipeline's accuracy
metrics. The whole step is gated by ``config.STANDARD_VOCAB_USE`` and the active standard by
``config.STANDARD_VOCAB_STYLE`` (only ``"abr"`` is implemented). The runtime reads plain CSV
maps under ``data/vocabularies/standards/<style>/`` and never imports rdflib (that is a
build-time concern of ``tools/build_abr_maps.py``).

Resolution per find:
  * ware  — typology -> master vocab ware_type -> ABR ware; else multilingual text fallback.
  * form  — typology -> master vocab vessel_form -> ABR form; else text fallback.
  * combined — (ware, form, typology) -> ABR combiterm. Typology crosswalk (exact full match, or
               one "/"-separated equivalent); among the matches prefer a region-agnostic combiterm,
               else one whose region the text names, else the sole variant; otherwise fall back to
               the ware+form-level combiterm, else blank.
A find that resolves nothing gets blank std_* columns (graceful, never raises).
"""
from __future__ import annotations

import csv
import os
import re
from typing import Dict, List, Optional

STD_COLUMNS = [
    "std_vocabulary", "std_ware_code", "std_ware_label",
    "std_form_code", "std_form_label", "std_combined_code", "std_combined_label",
]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MASTER = os.path.join(_ROOT, "data", "vocabularies", "pottery_vocab_master.csv")

_cache: Dict[str, "_Maps"] = {}

# Non-vessel / kiln-feature ABR forms (figurine, kiln grate, waster). In a context quote these words
# almost always refer to something other than the find's own shape ("vergelijkend beeld" = an image,
# "op het rooster" = the kiln grate, neighbouring wasters), so they are trusted only when the find's
# own (English-normalised) NAME names them, never when inferred from the context quote.
_NAME_ONLY_FORMS = {"BEELD", "ROOSTER", "MISBAKSL"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# Production-region hints: text keywords -> the Dutch qualifier as it appears in an ABR
# combiterm's typology label (e.g. "Dragendorff 37, Zuidgallisch"). Used only to disambiguate
# when a typology has several region-qualified ABR combiterms and no region-agnostic one.
_REGION_HINTS = [
    (("zuid-gallisch", "zuidgallisch", "south gaulish", "la graufesenque", "graufesenque", "montans"), "zuidgallisch"),
    (("oost-gallisch", "oostgallisch", "central gaulish", "east gaulish", "lezoux", "rheinzabern", "mittelgallisch"), "oostgallisch"),
    (("argonne", "argonnen"), "argonnen"),
    (("arretine", "arretijns", "arezzo", "arretina"), "arretijns"),
]


def _detect_region(text: str):
    t = (text or "").lower()
    for kws, qualifier in _REGION_HINTS:
        if any(k in t for k in kws):
            return qualifier
    return None


class _Maps:
    """Loaded, indexed map data for one standard style."""

    def __init__(self, style: str):
        base = os.path.join(_ROOT, "data", "vocabularies", "standards", style)
        self.ware_alias: Dict[str, dict] = {}      # english/other alias -> ware row
        self.ware_fallback: List[tuple] = []       # (keyword, ware row) for text scan
        self.ware_by_nl: Dict[str, dict] = {}      # norm(full NL ware label) -> ware row (exact)
        self.ware_by_nlbase: Dict[str, dict] = {}  # norm(base NL label) -> ware row (plain wares only)
        self.form_alias: Dict[str, dict] = {}
        self.form_fallback: List[tuple] = []
        self.form_by_code: Dict[str, dict] = {}    # ABR form code -> form row
        self.comb_by_typ: Dict[str, List[dict]] = {}      # norm(full region-stripped typ) -> rows (exact)
        self.comb_by_typ_part: Dict[str, List[dict]] = {}  # norm(one "/"-separated equivalent) -> rows
        self.comb_wf: Dict[tuple, dict] = {}           # (norm base ware label, form_code) -> ware+form combiterm
        self.master: Dict[str, tuple] = {}             # typology_code -> (ware_type, vessel_form)
        self._load_ware(os.path.join(base, "ware_map.csv"))
        self._load_form(os.path.join(base, "form_map.csv"))
        self._load_combined(os.path.join(base, "combined_map.csv"))
        self._load_master()
        # Drop fallback keywords that are ambiguous (map to more than one ware code, e.g. the bare
        # "terra" shared by terra sigillata/nigra/rubra). Real cases still match the longer explicit
        # aliases ("terra sigillata", ...); we just never guess on the ambiguous root.
        by_kw = {}
        for kw, rec in self.ware_fallback:
            by_kw.setdefault(kw, set()).add(rec["code"])
        self.ware_fallback = [(kw, rec) for kw, rec in self.ware_fallback if len(by_kw[kw]) == 1]

    @staticmethod
    def _rows(path):
        if not os.path.exists(path):
            return []
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def _load_ware(self, path):
        for r in self._rows(path):
            code, label = r.get("abr_ware_code", ""), r.get("ware_label_nl", "")
            if not code:
                continue
            rec = {"code": code, "label": label}
            # Index the FULL label for an exact match; only PLAIN wares (no regional/variant
            # qualifier after a comma) go into the generic base index, so a regional variant
            # (e.g. "...Eifel...", "African red slip ware") can never win a generic base lookup.
            self.ware_by_nl[_norm(label)] = rec
            if "," not in label:
                self.ware_by_nlbase[_norm(label.split(",")[0])] = rec
            keys = set()
            for a in r.get("en_aliases", "").split("|"):
                a = a.strip().lower()
                if a:
                    self.ware_alias[a] = rec
                    keys.add(a)
            # text-fallback keywords: english aliases (incl. variant-specific ones like "Eifel ware")
            # plus the distinctive NL label root, but the root only for PLAIN wares.
            first = label.lower().split()[0] if (label and "," not in label) else ""
            if len(first) >= 5:
                keys.add(first)
            for k in keys:
                self.ware_fallback.append((k, rec))

    def _load_form(self, path):
        for r in self._rows(path):
            code, label = r.get("abr_form_code", ""), r.get("form_label_nl", "")
            if not code:
                continue
            rec = {"code": code, "label": label}
            self.form_by_code[code] = rec
            keys = set()
            for a in r.get("en_aliases", "").split("|"):
                a = a.strip().lower()
                if a:
                    self.form_alias[a] = rec
                    keys.add(a)
            if label and len(label) >= 4:
                keys.add(label.lower())
            for k in keys:
                self.form_fallback.append((k, rec))

    def _load_combined(self, path):
        for r in self._rows(path):
            typ = r.get("typology_abr", "")
            ware_label = r.get("ware_label_nl", "")
            form_code = r.get("form_code", "")
            if typ:
                # strip the regional qualifier (after the first comma). Index the FULL typology
                # for an exact match, and each "/"-separated equivalent separately so a find that
                # names just one of a compound combiterm's typologies (e.g. "Niederbieber 104" of
                # "Niederbieber 104/Brunsting 9/Stuart 211") still matches — but only as a fallback
                # to an exact match, so "Dragendorff 18" is not confused by "Dragendorff 18/31".
                # ABR also appends a descriptive shape qualifier after ':' (e.g. "Holwerda 25:flesvormig",
                # "Niederbieber 89:dekselgeul") that is NOT part of the typology code; index both the
                # raw and the qualifier-stripped form so a find naming the bare typology still matches.
                base = typ.split(",")[0]

                def _qual_variants(s):
                    s = s.strip()
                    out = [s]
                    if ":" in s:
                        out.append(s.split(":", 1)[0].strip())
                    return [x for x in out if x]

                base_keys = {_norm(v) for v in _qual_variants(base)} - {""}
                for k in base_keys:
                    self.comb_by_typ.setdefault(k, []).append(r)
                parts = base.split("/")
                if len(parts) > 1:
                    for part in parts:
                        for k in {_norm(v) for v in _qual_variants(part)} - {""}:
                            if k and k not in base_keys:
                                self.comb_by_typ_part.setdefault(k, []).append(r)
            elif "," not in ware_label:
                # region-agnostic ware+form-level combiterm (no typology, no regional qualifier) —
                # the only safe fallback target. Keep the first seen; never assert a region.
                self.comb_wf.setdefault((_norm(ware_label), form_code), r)

    def _load_master(self):
        if not os.path.exists(_MASTER):
            return
        with open(_MASTER, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                k = (r.get("typology_code") or "").strip().lower()
                if k:
                    self.master[k] = (
                        (r.get("ware_type") or "").strip().lower(),
                        (r.get("vessel_form") or "").strip().lower(),
                    )


def _get_maps(style: str) -> Optional["_Maps"]:
    if style not in _cache:
        try:
            _cache[style] = _Maps(style)
        except Exception as e:  # missing/broken maps: degrade to no-op, never crash a run
            print(f"[std-vocab] could not load '{style}' maps ({type(e).__name__}: {e}); skipping")
            _cache[style] = None
    return _cache[style]


def _text_match(haystack: str, fallback: List[tuple]):
    hay = haystack.lower()
    best = None
    for kw, rec in fallback:
        if not kw:
            continue
        # Anchor the keyword to a word START (string start or after a non-letter), but allow trailing
        # characters so Dutch inflections still match (beker -> bekers/bekertje). This stops a label
        # matching inside an unrelated longer word (e.g. "beeld" inside "bijvoorbeeld"/"standbeeldje").
        i = hay.find(kw)
        while i != -1:
            if i == 0 or not hay[i - 1].isalpha():
                if best is None or len(kw) > best[0]:
                    best = (len(kw), rec)
                break
            i = hay.find(kw, i + 1)
    return best[1] if best else None


_CORK_RE = re.compile(r"\bcork urn\b|\bkurkurn|cork-tempered")


def _cand_ware_code(maps, ware_label_nl):
    wl = ware_label_nl or ""
    rec = maps.ware_by_nl.get(_norm(wl)) or maps.ware_by_nlbase.get(_norm(wl.split(",")[0]))
    return rec["code"] if rec else None


def _prefer_by_name(cands, name, maps):
    """Among equally region-agnostic combiterm candidates, pick the one whose derived ware/form best
    agrees with the find's own name; fall back to the first when nothing agrees (preserves old behavior)."""
    nm_ware = _text_match(name, maps.ware_fallback)
    nm_form = _text_match(name, maps.form_fallback)
    if not nm_ware and not nm_form:
        return cands[0]
    best, best_score = cands[0], -1
    for c in cands:
        score = 0
        if nm_ware and _cand_ware_code(maps, c.get("ware_label_nl")) == nm_ware["code"]:
            score += 1
        if nm_form and c.get("form_code") == nm_form["code"]:
            score += 1
        if score > best_score:
            best, best_score = c, score
    return best


def resolve(maps: "_Maps", typology: str, name: str, context: str = "", trust_context: bool = True) -> Dict[str, str]:
    """Resolve one find to its ABR std_* columns, returned as a dict of the seven STD_COLUMNS.

    ``typology``, ``name``, and ``context`` are the find's typology code, name, and source-text
    quote; every column is blank when nothing resolves (the step never raises). When
    ``trust_context`` is False (a quote shared by several finds, so unreliable per-find), only the
    name is text-matched.
    """
    # Text matching uses the find's own name plus its context quote (original_text) -- the quote often
    # carries the find's own precise Dutch term (e.g. "kruikamfoor", "spreukbeker"). But when the quote
    # is SHARED by several finds (trust_context=False), a sibling's ware/form in it could leak in, so we
    # then match the find's own name only. Region detection always uses the full text.
    out = {c: "" for c in STD_COLUMNS}
    typ = (typology or "").strip()
    full = (name + " " + context).strip()
    haystack = full if trust_context else name

    def _fb(index):
        return _text_match(haystack, index)

    def _fb_guarded(index):
        # Like _fb, but rejects sibling-form leakage from a multi-find quote. The quote (haystack) may
        # name several finds, so its longest match can belong to a sibling. If the find's own NAME
        # names a different family that the quote-derived match does NOT refine (the chosen label does
        # not contain the name term's label), trust the name. Real refinements survive because the
        # refined label contains the base term (spreukbeker contains beker; kruikamfoor contains amfoor).
        chosen = _text_match(haystack, index)
        nm = _text_match(name, index)
        if nm and chosen and nm["code"] != chosen["code"] and nm["label"].lower() not in chosen["label"].lower():
            return nm
        return chosen

    # 1. A typology-specific combiterm is ABR's authoritative ware+form+typology bundle.
    #    Match the typology (exact, or a "/"-equivalent), then prefer a region-agnostic combiterm,
    #    else a text-named region, else the sole variant; never guess a region.
    combiterm = None
    if typ:
        # exact full-typology match first; fall back to a "/"-equivalent part match
        ntyp = _norm(typ)
        cands = maps.comb_by_typ.get(ntyp) or maps.comb_by_typ_part.get(ntyp, [])
        if not cands:
            # a find may carry a sub-variant letter the base combiterm lacks (e.g. "Dragendorff 27g"
            # vs ABR's "Dragendorff 27"). Retry with a trailing number+letter variant reduced to its base.
            stripped = re.sub(r"(\d+)\s*[a-z]$", r"\1", ntyp)
            if stripped != ntyp:
                cands = maps.comb_by_typ.get(stripped) or maps.comb_by_typ_part.get(stripped, [])
        if cands:
            region_agnostic = [c for c in cands if "," not in (c.get("typology_abr") or "")]
            if region_agnostic:
                # a typology can be a "/"-equivalent of several combiterms with different wares/forms
                # (e.g. Brunsting 9 is both a gladwandige kruik and a ruwwandige kom). Prefer the
                # candidate whose ware/form agrees with the find's own name; tie-break to the first.
                combiterm = _prefer_by_name(region_agnostic, name, maps)
            else:
                # no region-agnostic combiterm. Prefer one whose region the text names;
                # else, if there is only ONE ABR variant, it is unambiguous (the type is
                # region-specific, e.g. Dragendorff 29 = Zuidgallisch). Otherwise fall back.
                reg = _detect_region(full)
                matched = [c for c in cands if reg and reg in (c.get("typology_abr") or "").lower()]
                if len(matched) == 1:
                    combiterm = matched[0]
                elif len(cands) == 1:
                    combiterm = cands[0]

    ware = form = None
    if combiterm:
        # derive ware+form FROM the combiterm so all three columns agree. Match the combiterm's full
        # ware label exactly first (so a regional variant like "...Eifel..." resolves to its own code);
        # else fall back to the plain-ware base. A regional/variant ware never wins a generic base lookup.
        _wl = combiterm.get("ware_label_nl") or ""
        ware = maps.ware_by_nl.get(_norm(_wl)) or maps.ware_by_nlbase.get(_norm(_wl.split(",")[0]))
        form = maps.form_by_code.get(combiterm.get("form_code"))
        out["std_combined_code"] = combiterm.get("abr_combined_code", "")
        out["std_combined_label"] = combiterm.get("combined_label_nl", "")
        # the combiterm's ware may be an ABR category outside our coded set; recover a ware code
        # from the master vocab / text so the combined => ware invariant still holds.
        if ware is None:
            tl = typ.lower()
            if tl in maps.master:
                ware = maps.ware_alias.get(maps.master[tl][0])
            if ware is None:
                ware = _fb(maps.ware_fallback)
    else:
        # 2. no typology-specific combiterm: ware/form via the master vocab, then text fallback
        tl = typ.lower()
        if tl in maps.master:
            wt, vf = maps.master[tl]
            ware = maps.ware_alias.get(wt)
            form = maps.form_alias.get(vf)
        if ware is None:
            ware = _fb_guarded(maps.ware_fallback)
        if form is None:
            form = _fb_guarded(maps.form_fallback)
        # a non-vessel/feature form is only trustworthy when the find's own NAME names it; if it came
        # only from the context quote (where "beeld"/"rooster"/"misbaksel" usually mean an image, a
        # kiln grate, or neighbouring wasters), drop it rather than mislabel the find's shape.
        if form is not None and form["code"] in _NAME_ONLY_FORMS:
            nm = _text_match(name, maps.form_fallback)
            if nm is None or nm["code"] != form["code"]:
                form = None
        # 3. ware+form-level combiterm as the region-agnostic fallback
        if ware and form:
            wf = maps.comb_wf.get((_norm(ware["label"].split(",")[0]), form["code"]))
            if wf:
                out["std_combined_code"] = wf.get("abr_combined_code", "")
                out["std_combined_label"] = wf.get("combined_label_nl", "")

    # cork urn is a distinctive ware (kurkurnaardewerk) whose name cue ("cork urn") loses the longest
    # match to the co-occurring fabric descriptor "coarse ware" (-> RUW). When a cork-urn find resolved
    # to a generic RUW only via the text fallback (no authoritative ABR combiterm), prefer KURKURN.
    # If a combiterm fixed the ware (e.g. RUWKURK = ruwwandig kurkurn), respect ABR and leave it.
    if (ware is not None and ware.get("code") == "RUW" and not out["std_combined_code"]
            and _CORK_RE.search(name.lower())):
        kurk = maps.ware_alias.get("cork urn")
        if kurk:
            ware = kurk

    if ware:
        out["std_ware_code"], out["std_ware_label"] = ware["code"], ware["label"]
    if form:
        out["std_form_code"], out["std_form_label"] = form["code"], form["label"]
    if out["std_ware_code"] or out["std_form_code"] or out["std_combined_code"]:
        out["std_vocabulary"] = "ABR"
    return out


def enrich_csv(path, style: str = "abr") -> int:
    """Append the std_* columns to an existing summary CSV in place. Returns rows resolved."""
    maps = _get_maps(style)
    if maps is None or not os.path.exists(path):
        return 0
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    out_fields = fieldnames + [c for c in STD_COLUMNS if c not in fieldnames]
    n = 0
    # An original_text quote shared by more than one find in this report is unreliable as per-find
    # context (it describes several finds), so it is not trusted for those finds.
    q_counts = {}
    for r in rows:
        q_counts[str(r.get("original_text", ""))] = q_counts.get(str(r.get("original_text", "")), 0) + 1
    for r in rows:
        name = " ".join(str(r.get(k, "")) for k in ("pottery", "term_found_normalized_en"))
        q = str(r.get("original_text", ""))
        std = resolve(maps, r.get("typology", ""), name, q, trust_context=(q_counts.get(q, 0) == 1))
        r.update(std)
        if std["std_vocabulary"]:
            n += 1
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return n

"""Deterministic site-name canonicalization.

Chunked extraction calls the model once per window, so the SAME place can come back spelled
several ways across windows ("Tempsplein", "Heerlen, Tempsplein", "Heerlen (Coriovallum)", …).
This collapses spelling/format variants of one place to a single canonical label, so finds group
by site correctly. Purely string-based (no LLM) and reproducible:

  normalise each name -> token set -> union-find (link if one token set ⊆ the other, or
  Jaccard ≥ 0.5) -> canonical = the most frequent member (tie: the longest, i.e. most complete).

A small Roman↔modern alias map handles equivalences a string method can't infer (e.g.
Coriovallum = Roman Heerlen); it's explicit and extensible — no risky guessing.

Caveat: a place named by ONLY a shared city token (e.g. a bare "Heerlen (Coriovallum)" -> {heerlen})
is merged into the same-city cluster — correct for a single-site report, but in a multi-site doc
with two distinct same-city sites it could over-merge. Distinctive sub-names keep sites apart.
"""
import re

# Roman / Latin -> modern place equivalences (lowercase). Extend as the corpus needs.
_SITE_ALIASES = {
    "coriovallum": "heerlen",
    "trajectum": "maastricht",
    "mosae": "maastricht",
    "ulpia": "xanten",
    "noviomagus": "nijmegen",
    "atuatuca": "tongeren",
    "tongres": "tongeren",
}
# Generic words to drop so they don't link unrelated sites or bloat the token set.
_SITE_STOP = {
    "de", "het", "een", "te", "aan", "bij", "in", "op", "der", "den", "van",
    "villa", "site", "vindplaats", "nederzetting", "opgraving", "gem", "gemeente",
    "the", "at", "of", "and", "fig", "figuur",
}


def _site_tokens(name: str) -> frozenset:
    s = re.sub(r"[(),/\-.;:]", " ", (name or "").lower())
    toks = set()
    for t in s.split():
        t = _SITE_ALIASES.get(t, t)
        if len(t) >= 3 and t not in _SITE_STOP:
            toks.add(t)
    return frozenset(toks)


def canonicalize_sites(names) -> dict:
    """Map each distinct non-empty site string to its canonical label (variants of one place share
    a label). Returns {original_name: canonical_name}. Empty/blank names are left untouched."""
    from collections import Counter
    freq = Counter(n for n in names if n and n.strip())
    uniq = list(freq)
    toks = {n: _site_tokens(n) for n in uniq}

    parent = {n: n for n in uniq}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(uniq):
        ta = toks[a]
        if not ta:
            continue
        for b in uniq[i + 1:]:
            tb = toks[b]
            if not tb:
                continue
            if ta <= tb or tb <= ta or len(ta & tb) / len(ta | tb) >= 0.5:
                union(a, b)

    clusters = {}
    for n in uniq:
        clusters.setdefault(find(n), []).append(n)

    mapping = {}
    for members in clusters.values():
        canon = max(members, key=lambda m: (freq[m], len(m)))   # most frequent, then most complete
        for m in members:
            mapping[m] = canon
    return mapping


_SITE_CANON_PROMPT = """\
You are an expert in the historical geography and archaeology of the Low Countries (Netherlands,
Belgium, Germany). Below is a numbered list of SITE / PLACE names extracted from ONE document;
they may contain OCR noise, spelling/word-order/format variants, abbreviations, or Roman-vs-modern
names. Group the names that refer to the SAME archaeological site/place and give each group ONE
clean canonical name; keep genuinely DIFFERENT places separate.
- Roman/Latin and modern names of the SAME place are the same (e.g. "Coriovallum" = "Heerlen").
- Spelling / OCR / word-order / punctuation variants are the same
  ("Heerlen, Tempsplein" = "Tempsplein, Heerlen" = "Heerlen-Tempsplein").
- DIFFERENT sub-sites/locations within the same town are DIFFERENT places (do NOT merge them just
  because they share the town name).

Names:
{items}

Return ONLY a JSON object mapping each input index to its canonical name (same canonical string for
names in the same group):
{{"results": [{{"index": <int>, "canonical": "<canonical site name>"}}]}}
"""
_SITE_CANON_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {"index": {"type": "integer"}, "canonical": {"type": "string"}},
        "required": ["index", "canonical"], "additionalProperties": False,
    }}},
    "required": ["results"], "additionalProperties": False,
}


def _extract_json_obj(raw):
    import json
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
    try:
        return json.loads(s[s.index("{"): s.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def _canonicalize_sites_llm(names):
    """One LLM call to group same-place site strings -> {original: canonical}. Returns None on any
    failure (no LLM key, parse error, or not every name mapped) so the caller falls back to the
    deterministic method. Uses the run's configured provider (Claude schema when anthropic)."""
    uniq = [n for n in dict.fromkeys(names) if n and n.strip()]
    if len(uniq) <= 1:
        return {n: n for n in uniq}
    items = "\n".join(f'[{i}] "{n}"' for i, n in enumerate(uniq))
    try:
        from config import LLM_PROVIDER
        from src.llm_client import call_llm
        schema = _SITE_CANON_SCHEMA if LLM_PROVIDER == "anthropic" else None
        raw = call_llm(_SITE_CANON_PROMPT.format(items=items),
                       max_tokens=max(2000, len(uniq) * 40), output_schema=schema)
    except Exception:
        return None
    obj = _extract_json_obj(raw)
    results = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(results, list):
        return None
    mapping = {}
    for o in results:
        try:
            i = int(o.get("index"))
        except (TypeError, ValueError):
            continue
        c = str(o.get("canonical", "")).strip()
        if 0 <= i < len(uniq) and c:
            mapping[uniq[i]] = c
    return mapping if len(mapping) == len(uniq) else None   # require all mapped, else fall back


def collapse_compound_sites(rows, field: str = "site_name") -> int:
    """Deterministic, list-free settlement collapse (no curated gazetteer): when a COMPOUND site
    ("Heerlen, Promenade", "Uilegats, Heerlen", "Nijmegen, second fortress") shares a comma-part with
    a BARE settlement that also appears on another row of the SAME report ("Heerlen", "Nijmegen"),
    rewrite the compound to that bare settlement. Matches on token signature so case/word-order/Roman
    aliases line up. Only fires when the bare form is actually present, so it needs no place list and
    is fully reproducible. Returns the number of rows rewritten."""
    def _sig(s):
        return " ".join(sorted(_site_tokens(s)))
    names = [(r.get(field) or "").strip() for r in rows]
    present = {n for n in names if n}
    bare_by_sig = {}
    for n in present:
        if "," not in n:                       # a bare (single-place) site name
            bare_by_sig.setdefault(_sig(n), n)
    mapping = {}
    for n in present:
        if "," in n:
            for part in n.split(","):
                sig = _sig(part)
                if sig and sig in bare_by_sig and bare_by_sig[sig] != n:
                    mapping[n] = bare_by_sig[sig]
                    break
    n_collapsed = 0
    for r in rows:
        v = (r.get(field) or "").strip()
        if v in mapping:
            r[field] = mapping[v]
            n_collapsed += 1
    return n_collapsed


def fill_singleton_site(rows, field: str = "site_name") -> int:
    """If a report has exactly ONE distinct non-blank site, give blank rows that site (a single-site
    report → every find belongs to it). Deterministic and safe: with two or more distinct sites it
    does nothing (can't guess which a blank row belongs to). Returns the number of rows filled."""
    distinct = {(r.get(field) or "").strip() for r in rows}
    distinct = {d for d in distinct if d}
    if len(distinct) != 1:
        return 0
    site = next(iter(distinct))
    n = 0
    for r in rows:
        if not (r.get(field) or "").strip():
            r[field] = site
            n += 1
    return n


_FIG_LINE = re.compile(r"^\s*(?:fig(?:ure)?|afb(?:eelding)?|pl(?:ate)?|tab(?:le|el)?|foto|photo)\b\.?\s*[\dIVXLCM]",
                       re.IGNORECASE)

_SITE_FROM_CONTEXT_PROMPT = """You are reading excerpts (title, headings, and figure/plate captions) \
from ONE archaeological report. Identify the SINGLE site where the finds described in this report were \
EXCAVATED — NOT places named only for comparison, parallels, or the provenance of imports.

Choose the name in this PRIORITY order:
1. The town/village/settlement where the excavation took place (preferred).
2. If the report names NO settlement, the EXCAVATION'S OWN designation — its project, trench, tracé,
   campaign, or established site name (e.g. a gas-pipeline trench "GasUnie sleuf" -> "GasUnie trench").

NEVER return something that only LOOKS like a place but is not one: NOT a building/house type (e.g.
"Alphen-Ekeren" / "Alphen-Ekeren huizen" is a HOUSE TYPE), NOT a pottery ware/typology, NOT an
archaeological period/culture, NOT a person's name. If the only candidates are such non-place,
non-excavation terms, return "".

Rules for the name:
- Settlement level: strip a comma findspot/street/feature qualifier down to the town ("Heerlen, Promenade" -> "Heerlen").
- KEEP an established hyphenated site name (Municipality-Toponym) intact ("Voerendaal-Ten Hove", "Kerkrade-Holzkuil").
- Keep the proper noun AS WRITTEN (do not translate a Roman<->modern town name), but you MAY render a
  generic descriptor in English ("sleuf" -> "trench", "tracé" -> "route").
- Return "" only if NO settlement AND no project/trench/campaign/site designation is identifiable.

EXCERPTS:
{context}

Return ONLY JSON: {{"site": "<site name or empty string>"}}"""
_SITE_FROM_CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {"site": {"type": "string"}},
    "required": ["site"], "additionalProperties": False,
}


def _focus_site_context(report_text: str, max_chars: int = 3000) -> str:
    """Assemble a tiny, focused context for the site backstop: the report's opening (title/intro)
    plus its figure/plate caption lines. Caption lines are short, so this stays small even for a huge
    report — the backstop is immune to the chunking/truncation that the main per-window extraction faces."""
    text = re.sub(r"\[\[p\d+\]\]", " ", report_text or "")
    head = text[:1500]
    captions = [ln.strip() for ln in text.split("\n") if _FIG_LINE.match(ln.strip())]
    parts = [head]
    if captions:
        parts.append("FIGURE/PLATE CAPTIONS:\n" + "\n".join(dict.fromkeys(captions)))
    return "\n\n".join(parts)[:max_chars]


def infer_site_from_captions(report_text: str) -> str:
    """LLM backstop for a report that extracted NO site: read its title + figure captions and return
    the single excavation site (settlement-level, hyphenated names kept), or "" if none / on any
    failure. One small focused call, so it is chunking/truncation-immune and never sees the bulk text."""
    ctx = _focus_site_context(report_text)
    if not ctx.strip():
        return ""
    try:
        from config import LLM_PROVIDER
        from src.llm_client import call_llm
        schema = _SITE_FROM_CONTEXT_SCHEMA if LLM_PROVIDER == "anthropic" else None
        raw = call_llm(_SITE_FROM_CONTEXT_PROMPT.format(context=ctx), max_tokens=200, output_schema=schema)
    except Exception:
        return ""
    obj = _extract_json_obj(raw)
    return str(obj.get("site", "")).strip() if isinstance(obj, dict) else ""


def apply_site_canonicalization(rows, field: str = "site_name", use_llm: bool = False) -> int:
    """Canonicalize `field` across row dicts in place. When use_llm, try the LLM canonicalizer first
    (domain knowledge: Roman↔modern names, distinguishing distinct same-town sites) and fall back to
    the deterministic string method on any failure. Returns how many distinct spellings were merged."""
    names = [r.get(field, "") for r in rows]
    mapping = _canonicalize_sites_llm(names) if use_llm else None
    if mapping is None:
        mapping = canonicalize_sites(names)
    if not mapping:
        return 0
    for r in rows:
        v = r.get(field, "")
        if v in mapping:
            r[field] = mapping[v]
    return len(set(mapping)) - len(set(mapping.values()))

"""
Layer 7.4 — Find consolidation (entity resolution / coreference).

The extractor and classifier judge each pottery mention in ISOLATION, so they cannot
tell that a later mention refers to the SAME physical find as an earlier one. A report
routinely names a find more than once: a detailed finds table lists it, then the
conclusions summarise it, an Archis/registration appendix re-lists it citing its
"vondstnummer", and prose discusses it. Counting each mention inflates the find list.

This pass groups mentions of the same ware (per site) and asks the LLM, seeing the
whole group at once, which mentions are DISTINCT finds and which are recaps/references
of finds already listed. It is deliberately conservative — when unsure, keep separate —
so a duplicate slips through rather than a real find being lost. Deterministic anchors
keep it stable: numbered finds-table rows are always distinct finds and are never
dropped; the LLM only adjudicates the ambiguous (mostly prose) mentions.

Gated by config.POTTERY_CONSOLIDATE_LLM_USE.

Scope (deliberately conservative — under-merging is safer than erasing a real find):
  - Only groups that contain a finds-TABLE cell consolidate: recaps are collapsed INTO a
    structured find. Pure-prose groups are left alone (merging two narrative mentions on
    meaning alone is unanchored and error-prone).
  - TYPED finds never consolidate (a code = a specific vessel; repeats are distinct).
  - GENERIC wares ("Pottery"/"aardewerk") consolidate on LLM judgement.
  - NAMED wares (terra nigra, geverfd aardewerk) consolidate ONLY when the row carries an
    explicit recap marker ("vondstnummer N", "fig.", "zie", "dit type", …), so distinct
    same-named finds are never merged on resemblance alone.
"""
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Generic ware names that should all share one consolidation group, so every
# "aardewerk"/"Pottery"/"keramiek" mention at a site is reasoned over together.
_GENERIC = {"pottery", "aardewerk", "ceramics", "ceramic", "keramiek", "scherf",
            "sherd", "scherven", "aardewerkscherven"}

# A find-number citation ("vondstnummer 7", "vondstnr. 32") — a hard back-reference to a
# catalogued find. Complements _REFERENCE_MARKER_RE (fig./zie/dit type/…) which omits it.
_FINDNUM_CITE_RE = re.compile(r"(?i)\bvondstnr\.?\b|\bvondstnummer")


def _untyped(row: Dict) -> bool:
    """Typed finds never consolidate: a typology code identifies a specific vessel, so
    the same code listed several times is several DISTINCT finds (as every other
    suppressor in the pipeline already treats them)."""
    return not (row.get("typology") or "").strip()


def _ware_key(row: Dict) -> str:
    """Generic ware names share one bucket; each named ware is its own bucket."""
    name = (row.get("pottery") or "").strip().lower()
    return "generic" if name in _GENERIC else name


def _has_recap_marker(text: str) -> bool:
    """An explicit textual back-reference marker (figure/table/'zie'/'dit type'/… or a
    'vondstnummer N' citation). Required before a NAMED ware may be dropped as a recap."""
    from src.pottery_summary import _has_reference_marker
    return _has_reference_marker(text) or bool(_FINDNUM_CITE_RE.search(text or ""))


_PROMPT = """\
You are an archaeologist consolidating one report's pottery finds. Below are several
MENTIONS of the same ware ({ware}) at the site "{site}", listed in document order.
Some are DISTINCT finds; others are the SAME find mentioned again — a conclusions
summary, an Archis/registration recap, a figure caption, or a back-reference such as
"vondstnummer 7" or "dit type".

Decide which mentions are RECAPS (the same find named again), not new finds.

Rules:
- Rows marked [table] from the report's MAIN, detailed finds table — each carrying its
  own per-row dating/period (e.g. "aardewerk Romeinse tijd") — are DISTINCT finds. Keep
  every one, even when several look identical (they are separate numbered finds).
- A SECONDARY summary/registration table (e.g. an Archis appendix that lists vague rows
  like "aardewerk, ondetermineerbaar" and cites find-numbers such as "vondstnummer 7, 21,
  24") merely re-lists the main table — mark ITS rows as RECAPS, even if marked [table].
- A mention that cites find-numbers ("vondstnummer(s) N", "vondstnr. N") or refers back
  ("dit type", "zoals genoemd", "zie fig.", "see fig.") is a RECAP.
- A prose statement that merely summarises finds already listed ("aardewerk uit de
  Romeinse tijd is aangetroffen", "pottery from the Roman period was found") is a RECAP.
- Call something a NEW find only if it clearly introduces a separate object/assemblage
  (a new find-number, a different feature/context/layer, or a different form).
- When unsure, treat it as a NEW find (do NOT merge).

Mentions:
{mentions}

Return ONLY a JSON object, nothing else:
{{"recaps": [<mention numbers that are recaps>], "reasoning": "<one sentence>"}}
"""


def _resolve_group(rows: List[Dict]) -> Set[int]:
    """Return the LOCAL indices (into ``rows``) that are recaps. Conservative on any
    failure (returns empty = keep all). Table-cell rows are never returned."""
    from src.llm_client import call_llm
    from src.pottery_summary import _extract_json_object

    lines = []
    for i, r in enumerate(rows, start=1):
        kind = "table" if r.get("_table_cell") else "prose"
        ds, de = r.get("start_date", ""), r.get("end_date", "")
        date = f"{ds}..{de}" if (ds != "" or de != "") else "no date"
        ctx = " ".join((r.get("original_text") or "").split())[:160]
        lines.append(f'[{i}] [{kind}] page {r.get("page", "?")} | {date} | "{ctx}"')

    prompt = _PROMPT.format(
        ware=(rows[0].get("pottery") or "pottery"),
        site=(rows[0].get("site_name") or "—"),
        mentions="\n".join(lines),
    )
    try:
        parsed = _extract_json_object(call_llm(prompt))
    except Exception:
        return set()
    if not parsed or not isinstance(parsed.get("recaps"), list):
        return set()

    recaps: Set[int] = set()
    for n in parsed["recaps"]:
        try:
            idx = int(n) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(rows):
            recaps.add(idx)
    return recaps


def consolidate_finds(rows: List[Dict], use_llm: bool = True) -> Tuple[List[Dict], int]:
    """Collapse recap/duplicate mentions of the same find. Returns (kept, n_dropped)."""
    if not use_llm:
        return rows, 0

    # Group untyped mentions per (site, ware). Generic wares share one bucket; each named
    # ware (terra nigra, geverfd aardewerk, …) is its own bucket.
    groups: Dict[Tuple, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        if _untyped(r):
            groups[(r.get("site_name", ""), _ware_key(r))].append(i)

    drop: Set[int] = set()
    for key, idxs in groups.items():
        if len(idxs) < 2:
            continue
        # Require an authoritative finds-table cell in the group: recaps are only collapsed
        # INTO a structured find. Pure-prose groups (no table) are left alone — merging two
        # narrative mentions on meaning alone is the unanchored, error-prone case (it cost a
        # real find on ocr_5: "…zoals dus deze beker" merged away a gold cup).
        if not any(rows[i].get("_table_cell") for i in idxs):
            continue
        is_generic = key[1] == "generic"
        local_recaps = _resolve_group([rows[i] for i in idxs])
        group_drop: Set[int] = set()
        for li in local_recaps:
            gi = idxs[li]
            # Generic wares carry no identity, so an LLM-judged recap is trusted. A NAMED
            # ware is dropped ONLY with an explicit recap marker in its own text (B): hard
            # evidence it's a back-reference, so distinct same-named finds (e.g. two terra
            # nigra of different date) are never merged on resemblance alone.
            if is_generic or _has_recap_marker(rows[gi].get("original_text", "")):
                group_drop.add(gi)
        # Never empty a group: if every mention would go, keep the first (document order)
        # so a genuinely-present find is never erased by over-eager merging.
        if group_drop and len(group_drop) == len(idxs):
            group_drop.discard(idxs[0])
        drop |= group_drop

    kept = [r for i, r in enumerate(rows) if i not in drop]
    return kept, len(drop)

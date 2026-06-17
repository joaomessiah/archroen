"""Layer 4 — normalization.

Maps each detected candidate's surface form to its canonical label (e.g. spelling
variants and synonyms collapse to one term) so later layers reason over a stable
vocabulary.
"""
import re
from typing import List, Dict


def surface_normalize(term: str) -> str:
    value = term.lower().strip()
    value = value.replace("dragendorff", "drag")
    value = re.sub(r"\bdr\.?", "drag", value)
    value = re.sub(r"\bdrag\.?", "drag", value)
    value = re.sub(r"[^a-z0-9\s-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_candidates(candidates: List[Dict]) -> List[Dict]:
    """Attach the canonical label to each candidate: adopt the pattern's `canonical_hint`
    as `term_canonical` (or `UNMAPPED` when none), plus a surface form and the method used.
    Thin by design — synonym/abbreviation grouping is done offline in the vocabularies."""
    normalized = []
    for candidate in candidates:
        canonical = candidate.get("canonical_hint") or "UNMAPPED"
        normalization_method = "canonical_hint" if canonical != "UNMAPPED" else "unmapped"

        out = dict(candidate)
        out["term_surface_normalized"] = surface_normalize(candidate["term_raw"])
        out["term_canonical"] = canonical
        out["normalization_method"] = normalization_method
        normalized.append(out)

    return normalized

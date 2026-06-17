"""Layer 7 (output) — record assembly.

Turns flat per-match records into the structured output records. Site attribution is done
per-find by the pottery extractor (LLM / section headings), not at this layer; the `sites`
field is kept as a null placeholder for schema stability.
"""
from typing import Dict, List, Optional


def _composite_confidence(context_conf: Optional[float], chrono_conf: Optional[float]) -> Optional[float]:
    c = context_conf if context_conf is not None else 0.0
    ch = chrono_conf if chrono_conf is not None else 0.0
    if context_conf is None and chrono_conf is None:
        return None
    return round(0.6 * c + 0.4 * ch, 4)


def build_output_record(flat: Dict) -> Dict:
    """Assemble one flat pipeline record into the nested Layer 7 output schema, grouping its
    fields into term / context / chronology / confidence / evidence / metadata blocks. Also
    derives the composite confidence and the `fallback_applied` flag (true if any LLM was used)."""
    report_id = flat.get("report_id") or None
    context_conf = flat.get("context_confidence")
    chrono_conf = flat.get("chrono_confidence")

    if context_conf is not None:
        context_conf = float(context_conf)
    if chrono_conf is not None:
        chrono_conf = float(chrono_conf)

    chrono_start = flat.get("chrono_start")
    chrono_end = flat.get("chrono_end")

    interp_method = flat.get("interpretation_method") or "unknown"
    chrono_extraction = flat.get("chrono_extraction_method") or "none"
    fallback_applied = interp_method == "llm" or chrono_extraction == "llm"

    return {
        "record_id": flat.get("record_id"),
        "report_id": report_id,
        "sites": [{"site_id": None, "site_name": None, "location": None}],

        "term": {
            "raw": flat.get("term_raw"),
            "surface_normalized": flat.get("term_surface_normalized"),
            "canonical": flat.get("term_canonical"),
        },

        "context": {
            "label": flat.get("context_label"),
            "confidence": context_conf,
        },

        "chronology": {
            "start": int(chrono_start) if chrono_start is not None else None,
            "end": int(chrono_end) if chrono_end is not None else None,
            "label": flat.get("chrono_date_label") or None,
            "status": flat.get("chrono_status"),
            "conflict": bool(flat.get("chrono_conflict", False)),
        },

        "confidence": {
            "context": context_conf,
            "chronology": chrono_conf,
            "composite": _composite_confidence(context_conf, chrono_conf),
        },

        "evidence": {
            "source_text": flat.get("context_window") or None,
            "context_sentence": flat.get("context_sentence") or None,
            "page": flat.get("page"),
            "section_id": flat.get("section_id") or None,
            "section_title": flat.get("section_title") or None,
        },

        "metadata": {
            "detection_method": flat.get("match_type") or "unknown",
            "normalization_method": flat.get("normalization_method") or "unknown",
            "interpretation_method": interp_method,
            "interpretation_reasoning": flat.get("interpretation_reasoning") or None,
            "chronology_method": flat.get("chrono_method") or "none",
            "chronology_extraction_method": chrono_extraction,
            "fallback_applied": fallback_applied,
            "conflict_detected": bool(flat.get("chrono_conflict", False)),
            "chrono_trace": flat.get("chrono_trace") or None,
        },
    }


def build_output_records(flat_records: List[Dict]) -> List[Dict]:
    return [build_output_record(r) for r in flat_records]

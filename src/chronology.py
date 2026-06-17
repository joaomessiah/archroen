"""Layer 6 — chronology assignment.

Assigns a date range to each eligible candidate: an eligibility gate, typology
lookup, regex date extraction from context, an optional LLM date fallback, then
conflict detection and reconciliation across the date signals.
"""
from typing import Dict, List, Optional, Tuple

from src.date_parser import extract_date_signals, extract_dates_llm

_SKIP_LABELS = {"absent", "irrelevant"}
_ELIGIBLE_LABELS = {"present", "comparison"}

# ---------------------------------------------------------------------------
# Eligibility gate (unchanged from Part 1)
# ---------------------------------------------------------------------------

def _eligibility_gate(
    record: Dict, process_uncertain: bool, uncertain_threshold: float
) -> Tuple[bool, str]:
    """Decide whether a record gets a chronology attempt, by context label: `present`/`comparison`
    are eligible, `absent`/`irrelevant` are skipped, and `uncertain` qualifies only when
    `process_uncertain` is on and its confidence clears `uncertain_threshold`. Returns
    (eligible?, human-readable reason for the trace)."""
    label = record.get("context_label", "")
    confidence = record.get("context_confidence", 0.0)

    if label in _SKIP_LABELS:
        return False, f"skipped: context_label={label}"

    if label == "comparison":
        return True, f"eligible: context_label=comparison (date extraction only)"

    if label in _ELIGIBLE_LABELS:
        return True, f"eligible: context_label={label}"

    if label == "uncertain":
        if process_uncertain and confidence >= uncertain_threshold:
            return True, (
                f"eligible: context_label=uncertain, confidence={confidence}"
                f" >= threshold={uncertain_threshold}"
            )
        return False, (
            f"skipped: context_label=uncertain, confidence={confidence}"
            f" (processing disabled or below threshold)"
        )

    return False, f"skipped: unrecognized context_label={label}"


# ---------------------------------------------------------------------------
# Typology lookup (unchanged from Part 1)
# ---------------------------------------------------------------------------

def _typology_lookup(record: Dict) -> Tuple[bool, Optional[int], Optional[int], str]:
    """Return the typological date signal carried on the record (the vocabulary range attached at
    detection), as (found?, start, end, note). The dates originate from the pottery vocabulary —
    this layer only reads them, never derives its own."""
    date_start = record.get("date_start")
    date_end = record.get("date_end")
    canonical = record.get("term_canonical", "")

    if date_start is not None and date_end is not None:
        return (
            True,
            int(date_start),
            int(date_end),
            f"canonical_term={canonical} matched vocabulary range {date_start}–{date_end}",
        )

    return False, None, None, f"canonical_term={canonical} has no chronology in vocabulary"


# ---------------------------------------------------------------------------
# Conflict detection and reconciliation (new in Part 2)
# ---------------------------------------------------------------------------

def _ranges_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
    return s1 <= e2 and s2 <= e1


def _reconcile(
    typo_start: Optional[int],
    typo_end: Optional[int],
    signals: List[Dict],
    context_confidence: float,
) -> Dict:
    """
    Combine typology range and extracted text signals into one chronology decision.

    Reconciliation rules (conservative, thesis-first):
      - No typology, no signals  → unassigned
      - No signals               → typological_direct (Part 1 baseline)
      - No typology, signals     → text_only
      - Text fully within typo   → combined_narrowed (text adds precision)
      - Text same or broader     → typological_direct (text adds nothing new)
      - Partial overlap          → typological_direct (conservative; don't extend)
      - No overlap               → conflict_flagged (keep typology, flag for review)
    """
    has_typo = typo_start is not None and typo_end is not None
    has_signals = bool(signals)

    if not has_typo and not has_signals:
        return {
            "status": "unassigned",
            "start": None, "end": None,
            "method": "none",
            "confidence": 0.0,
            "conflict_detected": False,
            "conflict_notes": "",
        }

    if not has_signals:
        conf = round(min(float(context_confidence), 0.9), 2)
        return {
            "status": "assigned",
            "start": typo_start, "end": typo_end,
            "method": "typological_direct",
            "confidence": conf,
            "conflict_detected": False,
            "conflict_notes": "",
        }

    # Aggregate all text signals into one envelope
    text_start = min(s["start"] for s in signals)
    text_end = max(s["end"] for s in signals)

    if not has_typo:
        # Scale confidence to the best signal precision available.
        _PREC_RANK = {"high": 2, "medium": 1, "low": 0}
        best_prec = max((s.get("precision", "low") for s in signals), key=lambda p: _PREC_RANK[p])
        conf = {"high": 0.85, "medium": 0.70, "low": 0.55}[best_prec]
        return {
            "status": "assigned",
            "start": text_start, "end": text_end,
            "method": "text_only",
            "confidence": conf,
            "conflict_detected": False,
            "conflict_notes": "",
        }

    # Both typology and text signals present

    # Use full signal envelope for conflict/overlap detection
    if not _ranges_overlap(typo_start, typo_end, text_start, text_end):
        # If every text signal is high-precision (explicit year), trust the text over typology
        all_high = all(s.get("precision") == "high" for s in signals)
        if all_high:
            return {
                "status": "assigned_with_conflict_note",
                "start": text_start, "end": text_end,  # prefer explicit date
                "method": "text_overrides_typology",
                "confidence": 0.70,
                "conflict_detected": True,
                "conflict_notes": (
                    f"Typology {typo_start}–{typo_end} does not overlap with"
                    f" text date {text_start}–{text_end};"
                    f" explicit text date used"
                ),
            }
        return {
            "status": "assigned_with_conflict_note",
            "start": typo_start, "end": typo_end,  # keep typology; flag for review
            "method": "conflict_flagged",
            "confidence": 0.30,
            "conflict_detected": True,
            "conflict_notes": (
                f"Typology {typo_start}–{typo_end} does not overlap with"
                f" text date {text_start}–{text_end}"
            ),
        }

    # Ranges overlap — check whether text genuinely narrows typology.
    # Only high/medium-precision signals are used for narrowing; low-precision
    # broad-period labels alone are not specific enough to narrow a typology range.
    hi_med_signals = [s for s in signals if s.get("precision") in ("high", "medium")]
    if not hi_med_signals:
        # Only low-precision signals present: conservative, keep typology
        conf = round(min(float(context_confidence), 0.9), 2)
        return {
            "status": "assigned",
            "start": typo_start, "end": typo_end,
            "method": "typological_direct",
            "confidence": conf,
            "conflict_detected": False,
            "conflict_notes": "",
        }

    narrow_start = min(s["start"] for s in hi_med_signals)
    narrow_end   = max(s["end"]   for s in hi_med_signals)

    if narrow_start >= typo_start and narrow_end <= typo_end:
        if narrow_start == typo_start and narrow_end == typo_end:
            # Identical ranges — text confirms but adds nothing
            conf = round(min(float(context_confidence), 0.9), 2)
            return {
                "status": "assigned",
                "start": typo_start, "end": typo_end,
                "method": "typological_direct",
                "confidence": conf,
                "conflict_detected": False,
                "conflict_notes": "",
            }
        # Text is a proper subset — narrow
        conf = round(min(float(context_confidence), 0.95), 2)
        return {
            "status": "assigned",
            "start": narrow_start, "end": narrow_end,
            "method": "combined_narrowed",
            "confidence": conf,
            "conflict_detected": False,
            "conflict_notes": "",
        }

    # Hi/med signals extend beyond typology on one or both sides — conservative: keep typology
    conf = round(min(float(context_confidence), 0.9), 2)
    return {
        "status": "assigned",
        "start": typo_start, "end": typo_end,
        "method": "typological_direct",
        "confidence": conf,
        "conflict_detected": False,
        "conflict_notes": "",
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_year(value: int) -> str:
    value = int(value)
    return f"{abs(value)} BCE" if value < 0 else f"AD {value}"


def _date_label(start: int, end: int) -> str:
    return f"{_format_year(start)}–{_format_year(end)}"


def _build_trace(steps: List[str]) -> str:
    return " | ".join(s for s in steps if s)


def _summarise_signals(signals: List[Dict]) -> str:
    if not signals:
        return "none"
    return " ; ".join(
        f"{s['expression']} → {_format_year(s['start'])}–{_format_year(s['end'])} [{s['date_type']}]"
        for s in signals
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def assign_chronology(
    records: List[Dict],
    process_uncertain: bool = False,
    uncertain_threshold: float = 0.6,
    use_llm: bool = True,
    use_date_llm: bool = False,
) -> List[Dict]:
    """Layer 6 entry point: assign a date range to each record. Per record — eligibility gate →
    typology lookup → regex date extraction from the widest available context (optional LLM date
    fallback) → conservative reconciliation of the typology and text signals. Comparison records
    are dated only when explicit text dates exist. Writes the `chrono_*` fields incl. a trace.

    Note: `use_llm` currently only labels the log line; the date-LLM fallback is gated
    separately by `use_date_llm`."""
    total = len(records)
    llm_calls = 0
    result = []

    print(f"[Layer 6] Assigning chronology to {total} records (LLM={'on' if use_llm else 'off'}, date-LLM={'on' if use_date_llm else 'off'}) ...")

    for i, record in enumerate(records, start=1):
        out = dict(record)
        eligible, eligibility_note = _eligibility_gate(
            record, process_uncertain, uncertain_threshold
        )

        if not eligible:
            out["chrono_status"] = "skipped"
            out["chrono_start"] = None
            out["chrono_end"] = None
            out["chrono_date_label"] = ""
            out["chrono_method"] = "none"
            out["chrono_confidence"] = 0.0
            out["chrono_conflict"] = False
            out["chrono_extracted_dates"] = ""
            out["chrono_extraction_method"] = "none"
            out["chrono_trace"] = eligibility_note
            result.append(out)
            continue

        is_comparison = (record.get("context_label") == "comparison")

        typo_found, typo_start, typo_end, lookup_note = _typology_lookup(record)

        # Use the widest available context for date extraction:
        #   date_context (±2 sentences, set by pottery_extractor)
        #   > context_window (±CONTEXT_WINDOW_CHARS characters)
        #   > context_sentence (single sentence, narrowest fallback)
        context_text = (
            record.get("date_context", "")
            or record.get("context_window", "")
            or record.get("context_sentence", "")
        )
        signals = extract_date_signals(context_text)
        extraction_method = "regex"

        if not signals and use_date_llm:
            llm_signals = extract_dates_llm(context_text, record.get("term_raw", ""))
            if llm_signals:
                signals = llm_signals
                extraction_method = "llm"
                llm_calls += 1

        # Comparison records only get chronology if there are explicit text signals;
        # a typology-only date for a comparison mention is not informative.
        if is_comparison and not signals:
            out["chrono_status"] = "skipped"
            out["chrono_start"] = None
            out["chrono_end"] = None
            out["chrono_date_label"] = ""
            out["chrono_method"] = "none"
            out["chrono_confidence"] = 0.0
            out["chrono_conflict"] = False
            out["chrono_extracted_dates"] = ""
            out["chrono_extraction_method"] = "none"
            out["chrono_trace"] = f"skipped: context_label=comparison, no text signals found"
            result.append(out)
            continue

        signals_summary = _summarise_signals(signals)
        extraction_note = f"text signals [{extraction_method}]: {signals_summary}"

        context_confidence = float(record.get("context_confidence", 0.9))
        decision = _reconcile(
            typo_start if typo_found else None,
            typo_end if typo_found else None,
            signals,
            context_confidence,
        )

        # For comparison records with signals: mark the method and cap confidence.
        if is_comparison and decision["start"] is not None:
            decision["status"] = "assigned_comparison"
            decision["method"] = "comparison_" + decision["method"]
            decision["confidence"] = round(min(decision["confidence"], 0.60), 2)

        assigned_start = decision["start"]
        assigned_end = decision["end"]

        out["chrono_status"] = decision["status"]
        out["chrono_start"] = assigned_start
        out["chrono_end"] = assigned_end
        out["chrono_date_label"] = _date_label(assigned_start, assigned_end) if assigned_start is not None else ""
        out["chrono_method"] = decision["method"]
        out["chrono_confidence"] = decision["confidence"]
        out["chrono_conflict"] = decision["conflict_detected"]
        out["chrono_extracted_dates"] = signals_summary
        out["chrono_extraction_method"] = extraction_method

        trace_steps = [
            eligibility_note,
            lookup_note,
            extraction_note,
        ]
        if decision["conflict_detected"]:
            trace_steps.append(f"CONFLICT: {decision['conflict_notes']}")
        trace_steps.append(
            f"assignment_method={decision['method']}, confidence={decision['confidence']}"
        )
        out["chrono_trace"] = _build_trace(trace_steps)

        result.append(out)

        print(f"[Layer 6] {i}/{total} records | LLM calls so far: {llm_calls}")

    print(f"[Layer 6] Done. {llm_calls}/{total} records used LLM date extraction.")
    return result

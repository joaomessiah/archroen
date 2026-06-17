"""Layer 7 (validation) — structural validation.

Checks each output record has the required fields and well-formed values, returning a
validation summary (run as a console sanity count). Validates record structure only,
not correctness against a gold standard (see evaluation/evaluate.py for scoring).
"""
from typing import Dict, List, Tuple


def _check(condition: bool, message: str, issues: List[str]) -> None:
    if not condition:
        issues.append(message)


def validate_record(record: Dict) -> Tuple[Dict, List[str]]:
    """Structurally validate one output record: required fields are present, blocks are
    objects, confidences are numeric, and an *assigned* chronology carries a numeric range.
    Returns (record + `validation` block, list of issue strings). Structure only — not
    correctness; accuracy is scored in evaluation/evaluate.py."""
    issues = []

    # Required top-level fields
    _check(bool(record.get("record_id")), "missing: record_id", issues)
    _check(bool(record.get("report_id")), "missing: report_id", issues)

    # term block
    term = record.get("term") or {}
    _check(isinstance(term, dict), "type_error: term must be an object", issues)
    if isinstance(term, dict):
        _check(bool(term.get("canonical")), "missing: term.canonical", issues)

    # context block
    ctx = record.get("context") or {}
    _check(isinstance(ctx, dict), "type_error: context must be an object", issues)
    if isinstance(ctx, dict):
        _check(ctx.get("label") is not None, "missing: context.label", issues)
        _check(
            isinstance(ctx.get("confidence"), (int, float)),
            "type_error: context.confidence must be numeric",
            issues,
        )

    # chronology block
    chrono = record.get("chronology") or {}
    _check(isinstance(chrono, dict), "type_error: chronology must be an object", issues)
    if isinstance(chrono, dict):
        status = chrono.get("status")
        _check(bool(status), "missing: chronology.status", issues)
        if status not in ("skipped", "unassigned", None):
            _check(
                chrono.get("start") is not None and chrono.get("end") is not None,
                f"missing: chronology range (start/end) for status='{status}'",
                issues,
            )
            _check(
                isinstance(chrono.get("start"), (int, float)),
                "type_error: chronology.start must be numeric",
                issues,
            )
            _check(
                isinstance(chrono.get("end"), (int, float)),
                "type_error: chronology.end must be numeric",
                issues,
            )

    # confidence block
    conf = record.get("confidence") or {}
    _check(isinstance(conf, dict), "type_error: confidence must be an object", issues)
    if isinstance(conf, dict):
        _check(
            conf.get("context") is not None or conf.get("chronology") is not None,
            "missing: confidence (both context and chronology are null)",
            issues,
        )
        for key in ("context", "chronology", "composite"):
            val = conf.get(key)
            if val is not None:
                _check(
                    isinstance(val, (int, float)),
                    f"type_error: confidence.{key} must be numeric",
                    issues,
                )

    # evidence block
    ev = record.get("evidence") or {}
    _check(isinstance(ev, dict), "type_error: evidence must be an object", issues)
    if isinstance(ev, dict):
        _check(ev.get("page") is not None, "missing: evidence.page", issues)

    out = dict(record)
    out["validation"] = {
        "valid": len(issues) == 0,
        "issues": issues,
    }
    return out, issues


def validate_records(records: List[Dict]) -> Tuple[List[Dict], Dict]:
    """Validate every record and return (annotated records, summary). The summary counts
    valid/invalid records and total issues for the validation log."""
    validated = []
    total_issues = 0
    invalid_ids = []

    for record in records:
        out, issues = validate_record(record)
        validated.append(out)
        if issues:
            total_issues += len(issues)
            invalid_ids.append(record.get("record_id", "unknown"))

    summary = {
        "total_records": len(records),
        "valid_records": len(records) - len(invalid_ids),
        "invalid_records": len(invalid_ids),
        "total_issues": total_issues,
        "invalid_record_ids": invalid_ids,
    }
    return validated, summary

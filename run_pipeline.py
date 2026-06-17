"""Pipeline orchestrator.

Runs all layers in sequence on a single PDF report and writes the outputs:
  1-2  extract + clean       (extractor, cleaner)
  3    structure + detect    (structure, detection)
  3b   pottery extraction    (pottery_extractor)
  4    normalize             (normalization)
  5    interpret context     (interpretation)
  6    assign chronology     (chronology)
  7    build/validate + summary (output_builder, validator, pottery_summary)

Behaviour is driven entirely by the toggles in config.py. Run with:
    .venv/bin/python3 run_pipeline.py
which processes config.DEFAULT_PDF_PATH; or call main(Path(...)) for another report.
"""
import shutil
import tempfile
import time
from pathlib import Path

from config import (
    DEFAULT_PDF_PATH,
    DEFAULT_REPORTS_DIR,
    BATCH_WORKERS,
    CHRONOLOGY_PATTERNS_PATH,
    POTTERY_PATTERNS_PATH,
    POTTERY_TRIGGERS_PATH,
    CENTURY_PATTERNS_PATH,
    OUTPUT_REPORTS_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CONTEXT_WINDOW_CHARS,
    LLM_USE,
    CHRONO_PROCESS_UNCERTAIN,
    CHRONO_UNCERTAIN_THRESHOLD,
    CHRONO_LLM_USE,
    CHRONO_DATE_LLM_USE,
    POTTERY_EXTRACT_LLM_USE,
    POTTERY_CONTEXT_LLM_USE,
    POTTERY_DATE_LLM_USE,
    POTTERY_DEDUP_LLM_USE,
    POTTERY_CONSOLIDATE_LLM_USE,
    POTTERY_HYBRID_LLM_USE,
    POTTERY_CSV_REF_PATH,
)
from src.io_utils import load_json
from src.extractor import extract_pdf_pages
from src.cleaner import clean_pages
from src.structure import split_into_sections, chunk_sections
from src.detection import detect_candidates, merge_dual_typologies, build_code_date_lookup
from src.pottery_extractor import extract_pottery_mentions, extract_figure_catalogue_finds
from src.normalization import normalize_candidates
from src.interpretation import interpret_candidates
from src.chronology import assign_chronology
from src.output_builder import build_output_records
from src.validator import validate_records
from src.pottery_summary import build_csv_lookup, load_chron_vocab, export_pottery_summary


def add_record_ids(records):
    enriched = []
    for i, record in enumerate(records, start=1):
        item = dict(record)
        item["record_id"] = f"record_{i}"
        enriched.append(item)
    return enriched


def _stage(name: str, t0: float) -> float:
    t1 = time.time()
    print(f"[{name}] done in {t1 - t0:.1f}s")
    return t1


def main(pdf_path: Path = DEFAULT_PDF_PATH) -> None:
    """Run the full pipeline on one PDF and write all outputs. Loads the pattern/vocabulary files,
    then runs Layers 1-7 in sequence (extract+clean → structure → detect → pottery extract →
    normalize → interpret → chronology → output/validate), writes the per-record exports and the
    pottery summary, and — when `POTTERY_HYBRID_LLM_USE` is on — the optional Claude-hybrid summary.
    Each layer's behaviour is driven by config.py toggles; timings are printed per stage."""
    run_start = time.time()
    print(f"PDF: {pdf_path}")

    t = time.time()
    pattern_specs = (
        load_json(CHRONOLOGY_PATTERNS_PATH)
        + load_json(POTTERY_PATTERNS_PATH)
        + load_json(CENTURY_PATTERNS_PATH)
    )
    pottery_triggers = load_json(POTTERY_TRIGGERS_PATH)
    pottery_csv_lookup = build_csv_lookup(POTTERY_CSV_REF_PATH)
    chron_vocab = load_chron_vocab()   # built from src/periods.py (single source of truth)
    pages = extract_pdf_pages(pdf_path)
    cleaned_pages = clean_pages(pages)
    t = _stage("Layer 1-2 extract+clean", t)

    sections = split_into_sections(cleaned_pages)
    chunks = chunk_sections(sections, CHUNK_SIZE, CHUNK_OVERLAP)
    t = _stage("Layer 3 structure+chunk", t)

    candidates = detect_candidates(
        chunks=chunks,
        pattern_specs=pattern_specs,
        window_chars=CONTEXT_WINDOW_CHARS,
        report_id=pdf_path.stem,
    )
    print(f"  → {len(candidates)} candidates detected")
    code_dates = build_code_date_lookup(POTTERY_CSV_REF_PATH.parent / "pottery_vocab_master.csv")
    candidates = merge_dual_typologies(candidates, chunks, code_dates)
    t = _stage("Layer 3 detection", t)

    pottery_candidates = extract_pottery_mentions(
        chunks=chunks,
        existing_candidates=candidates,
        triggers=pottery_triggers,
        use_llm=POTTERY_EXTRACT_LLM_USE,
        report_id=pdf_path.stem,
        section_texts={s["section_id"]: s["text"] for s in sections},
    )
    candidates = candidates + pottery_candidates
    # Figure plates of vessel drawings labelled only by find/catalogue numbers (gated on
    # a figure marker + a vessel/pottery word in the caption).
    catalogue_candidates = extract_figure_catalogue_finds(chunks, report_id=pdf_path.stem)
    if catalogue_candidates:
        print(f"  → {len(catalogue_candidates)} figure-catalogue finds")
    candidates = candidates + catalogue_candidates
    print(f"  → {len(candidates)} candidates after pottery extraction")
    t = _stage("Layer 3b pottery extraction", t)

    normalized = normalize_candidates(candidates)
    t = _stage("Layer 4 normalization", t)

    interpreted = interpret_candidates(normalized, use_llm=LLM_USE)
    t = _stage("Layer 5 interpretation", t)

    chronologised = assign_chronology(
        interpreted,
        process_uncertain=CHRONO_PROCESS_UNCERTAIN,
        uncertain_threshold=CHRONO_UNCERTAIN_THRESHOLD,
        use_llm=CHRONO_LLM_USE,
        use_date_llm=CHRONO_DATE_LLM_USE,
    )
    t = _stage("Layer 6 chronology", t)

    final_records = add_record_ids(chronologised)
    output_records = build_output_records(final_records)
    validated_records, validation_summary = validate_records(output_records)
    t = _stage("Layer 7 output+validation", t)

    # Single output per report: <report>.csv under output_files/reports/<folder>/, where <folder>
    # mirrors the input batch folder (input_files/reports/<folder>/<report>.pdf).
    out_dir = OUTPUT_REPORTS_DIR / pdf_path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    output_csv = out_dir / f"{pdf_path.stem}.csv"

    def _write_pottery_summary(dest: Path) -> None:
        export_pottery_summary(final_records, pottery_csv_lookup, dest, chron_vocab,
                               use_llm=POTTERY_CONTEXT_LLM_USE or POTTERY_DATE_LLM_USE,
                               ref_dedup_llm=POTTERY_DEDUP_LLM_USE,
                               section_texts={s["section_id"]: s["text"] for s in sections},
                               consolidate_llm=POTTERY_CONSOLIDATE_LLM_USE)

    if POTTERY_HYBRID_LLM_USE:
        # Claude-hybrid: a frontier LLM reads the whole report and produces the summary directly.
        # The rule-based rows are still needed as input (confirm-merge + reg#-union recovery), so we
        # write them to a TEMP file the hybrid reads, then discard it — no _rulebased.csv sidecar.
        from src.hybrid_extractor import extract_pottery_hybrid
        with tempfile.TemporaryDirectory() as tmp:
            rule_tmp = Path(tmp) / f"{pdf_path.stem}_rulebased.csv"
            _write_pottery_summary(rule_tmp)
            try:
                extract_pottery_hybrid(
                    cleaned_pages, output_csv, report_id=pdf_path.stem,
                    csv_lookup=pottery_csv_lookup, code_dates=code_dates,
                    pdf_path=pdf_path, rule_csv=rule_tmp)
            except Exception as e:
                # Graceful degradation: if the hybrid step fails (e.g. a rate-limit storm under heavy
                # parallelism on an oversized report), fall back to the rule-based output so the
                # report still completes with results instead of crashing/hanging the run.
                print(f"[Hybrid] FAILED ({type(e).__name__}: {e}); keeping rule-based output")
                shutil.copyfile(rule_tmp, output_csv)
    else:
        _write_pottery_summary(output_csv)
    _stage("Export", t)

    total = time.time() - run_start
    print(f"\nPages: {len(pages)} | Sections: {len(sections)} | Chunks: {len(chunks)}")
    print(f"Records: {len(final_records)} | Valid/Invalid: {validation_summary['valid_records']}/{validation_summary['invalid_records']}")
    print(f"Total time: {total:.1f}s ({total/60:.1f} min)")
    print(f"Output → {output_csv}")


def _run_one(pdf_path_str: str):
    """Parallel-batch worker: run the pipeline on one PDF, capturing its console output to a
    per-report log file (so parallel runs don't interleave). Returns (stem, status, seconds)."""
    import contextlib
    import traceback
    pdf = Path(pdf_path_str)
    log_dir = OUTPUT_REPORTS_DIR / pdf.parent.name / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(log_dir / f"{pdf.stem}.log", "w") as f, \
            contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        try:
            main(pdf)
            return (pdf.stem, "ok", time.time() - t0)
        except Exception as e:                       # isolate: one bad report can't kill the batch
            traceback.print_exc(file=f)
            return (pdf.stem, f"ERROR {type(e).__name__}: {e}", time.time() - t0)


def run_batch(reports_dir: Path = DEFAULT_REPORTS_DIR, workers: int = BATCH_WORKERS) -> None:
    """Process every PDF in `reports_dir` (a folder under input_files/reports/), writing one
    `<report>.csv` per report to `output_files/reports/<folder>/`. Runs `workers` reports in
    parallel (1 = sequential with live console output; >1 redirects each report to logs/<report>.log)."""
    pdfs = sorted(reports_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {reports_dir}")
        return
    print(f"Batch: {len(pdfs)} report(s) from '{reports_dir.name}', {workers} at a time "
          f"→ output_files/reports/{reports_dir.name}/\n")
    t0 = time.time()
    results = []
    if workers <= 1:
        for pdf in pdfs:
            print(f"\n===== {pdf.stem} =====")
            try:
                main(pdf)
                results.append((pdf.stem, "ok"))
            except Exception as e:
                print(f"  ERROR {type(e).__name__}: {e}")
                results.append((pdf.stem, "ERROR"))
    else:
        from multiprocessing import Pool
        with Pool(workers) as pool:
            for stem, status, secs in pool.imap_unordered(_run_one, [str(p) for p in pdfs]):
                print(f"  {stem}: {status} ({secs:.0f}s)", flush=True)
                results.append((stem, status))
    ok = sum(1 for _, s in results if s == "ok")
    elapsed = time.time() - t0
    print(f"\nBatch done: {ok}/{len(pdfs)} ok in {elapsed:.0f}s ({elapsed/60:.1f} min)."
          f"  Per-report logs: output_files/reports/{reports_dir.name}/logs/")


if __name__ == "__main__":
    run_batch()

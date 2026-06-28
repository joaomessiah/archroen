# Layer specifications

One spec per layer, describing what it does, what it consumes and produces, the modules that implement
it, and the `config.py` settings that steer it. These are **as-built** specs: they describe the
current code, verified against the modules in `src/` and `evaluation/`. The eight layers match the
thesis's Layers 1-8 structure.

Read [../overview.md](../overview.md) and [../architecture.md](../architecture.md) first for the big
picture, then dive into any layer below.

| Spec | Layer | Implemented by |
|---|---|---|
| [layer_1.md](layer_1.md) | 1. Extraction | `src/extractor.py` |
| [layer_2.md](layer_2.md) | 2. Cleaning | `src/cleaner.py`, `src/structure.py` |
| [layer_3.md](layer_3.md) | 3. Detection | `src/detection.py`, `src/pottery_extractor.py` |
| [layer_4.md](layer_4.md) | 4. Normalization | `src/normalization.py` |
| [layer_5.md](layer_5.md) | 5. Context interpretation | `src/interpretation.py` |
| [layer_6.md](layer_6.md) | 6. Chronology assignment | `src/chronology.py`, `src/date_parser.py`, `src/periods.py` |
| [layer_7.md](layer_7.md) | 7. Output assembly, validation, deduplication, and consolidation | `src/pottery_summary.py` (Layer 7 orchestrator), with helpers `src/output_builder.py`, `src/validator.py`, `src/site_norm.py`, `src/consolidation.py`, `src/hybrid_extractor.py` |
| [layer_8.md](layer_8.md) | 8. Evaluation (standalone harness, not part of `run_pipeline.py`) | `evaluation/evaluate.py`, `evaluation/evaluate_granular.py` |

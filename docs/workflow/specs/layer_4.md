# Layer 4: Normalization

**Module:** `src/normalization.py`

## Purpose

Collapse spelling variants and synonyms of a detected term to **one canonical label**, so the later
layers reason over a stable vocabulary.

## What it does

- Adopts the pattern's `canonical_hint` as the candidate's `term_canonical` (or `UNMAPPED` when there
  is no hint), and records the normalization method used.
- Computes a **surface form**: lowercased, with punctuation stripped and common abbreviations unified
  (e.g. `Dragendorff` / `Dr.` / `Drag.` all collapse to `drag`).

## Input and output

- **In:** the candidate list from [Layer 3](layer_3.md).
- **Out:** the same candidates, each annotated with `term_canonical`, a surface form, and the method.

## Configuration

None.

## Notes

This layer is **thin by design.** The heavy work of grouping synonyms and abbreviations is done
*offline*, in the vocabulary files under `data/vocabularies/` (the single source of truth for canonical
names and dates). Layer 4 just applies the canonical label detection already carried.

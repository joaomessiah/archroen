# Claude mode + ABR standard vocabulary: validation outputs (frozen)

The **Claude mode** pottery-summary output for each of the 20 validation reports, one CSV per
report, with the **standard-vocabulary (`std_*`) columns** included. File names encode the source
type: `new_rep_*` (new reports), `old_rep_*` (old reports), `ocr_*` (OCR'd scans), and `table_*`
(finds-tables), five of each.

This folder demonstrates that the workflow can emit output compatible with the Dutch national
archaeological standard, the **Archeologisch Basisregister (ABR / Archis)**, across the full
validation set.

## What the columns add

Seven columns are appended to each find (full definitions in
[output_schema.md](../../../../../reference/output_schema.md)):

- `std_vocabulary`: names the standard (`ABR`) whenever any code is assigned.
- `std_ware_code` / `std_ware_label`: the ABR ware (fabric) code and its Dutch label.
- `std_form_code` / `std_form_label`: the ABR vessel-form code and its Dutch label.
- `std_combined_code` / `std_combined_label`: ABR's single combiterm that bundles ware, form, and typology.

Because the values are the actual ABR codes, a free-text pottery summary becomes data expressed in the
national standard's vocabulary, ready for use in the Archis ecosystem without manual re-coding.

## How the values are assigned

The mapping is a deterministic, mode-independent step: the same input row always yields the same
codes, in any run mode. Two paths produce the values:

- When a find's typology is one that ABR recognizes, its ware, form, and combined term are read from
  ABR's own definition of that typology (the authoritative combiterm), so they are fixed by the
  standard rather than inferred.
- Otherwise, the ware and form are resolved from the find's typology and terms via a controlled
  vocabulary, and the combined term is filled when that ware-and-form pair matches an ABR combiterm,
  otherwise left blank.

Finds too generic to place in ABR (for example an unqualified "pottery") are left blank rather than
assigned a guessed code.

The columns are always mutually consistent: every code is paired with its label, and a combined term
agrees with its ware and form. The layer is standard-agnostic by design; ABR is the first standard
implemented, selectable via configuration.

## Scope

These columns are an interoperability layer. They are not scored against a gold standard, so they sit
outside the accuracy figures reported for the pottery summary.

This is a frozen snapshot; the live copy is at `output_files/reports/workflow_evaluation_sample_std_abr/`.
To reproduce, see the [datasets overview](../../../README.md).

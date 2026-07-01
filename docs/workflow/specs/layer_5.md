# Layer 5: Context interpretation

**Module:** `src/interpretation.py`

## Purpose

Decide *how the report refers to* each detected term. A pottery name appearing in the text does not
mean that pot was found at the site. This label gates whether the term gets a date in
[Layer 6](layer_6.md).

## The labels

Each candidate is classified as one of:

| Label | Meaning |
|---|---|
| `present` | The find is reported as present at the site |
| `absent` | Explicitly *not* found / absent |
| `comparison` | Mentioned only to compare with finds elsewhere (e.g. "cf.", parallels, citations) |
| `uncertain` | The reference is ambiguous |
| `irrelevant` | Not a real find statement (and pre-/post-Roman terms outside the period of interest) |

## How it decides

1. **Deterministic cue rules first.** Linguistic cues (presence/absence phrasing, comparison markers,
   citation patterns) classify the clear cases. Terms whose canonical label is clearly **pre-Roman** or
   **post-Roman** are marked `irrelevant` up front.
2. **AI fallback for low-confidence cases.** Where the rules aren't confident, an AI step makes the
   call. This fallback runs only in the AI modes.

## Input and output

- **In:** normalized candidates from [Layer 4](layer_4.md).
- **Out:** the same candidates, each with a `context_label` and a `context_confidence`.

## Configuration (`config.py`)

| Setting | Role |
|---|---|
| `LLM_USE` (via `WORKFLOW_MODE`) | Gates the AI fallback. In **Rules-only mode** only the deterministic cue rules run. |

## Notes

The label controls the next layer: `present`/`comparison` are eligible for dating; `absent`/`irrelevant`
are skipped; `uncertain` is processed only under the Layer 6 eligibility gate.

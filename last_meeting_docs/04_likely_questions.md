# 4 · Likely Questions & Talking Points

*Anticipated questions for a ~1-hour meeting that will lean toward the thesis and the general
picture rather than code. Have a one-paragraph answer ready for each.*

## On the design

**Q. Why LLM-led instead of pure rules?**
The rules-only approach hits a hard ceiling on real grey literature (47.9 % overall, and only 3.3 %
on site name). Reports describe finds in prose, tables, and captions, across multiple sites, in two
languages, the kind of context-dependent reading rules can't do. The LLM reads the whole report and
makes those judgments; the rules then ground and verify it. The numbers justify the switch.

**Q. Doesn't using an LLM risk hallucination?**
That's exactly why the rules stay in a supporting role. Dates come from typology/period **tables**,
names from a controlled **vocabulary**, sites from **string matching**, never from the model's own
numbers. And every model-produced find must carry a **verbatim quote** from the report, so claims are
traceable to the text.

**Q. Why Claude over Llama? Is the comparison fair?**
Same hybrid design, only the backend differs, that's what makes it a fair comparison. Claude scored
95.6 % vs Llama's 77.3 %; Llama's main weakness is recall (it misses more genuine finds). It's a real
"frontier model vs open model" data point, not a rigged one. Trade-off: Claude is paid and not fully
reproducible; Llama is the open-model option; rules-only is free and deterministic.

**Q. Are the AI results reproducible?**
Not exactly. The AI modes run at low temperature but aren't deterministic across runs. Only
rules-only is fully reproducible. The validation outputs and scores are **frozen in the repo** so the
reported numbers can always be re-checked, even if a fresh run varies slightly.

## On the evaluation

**Q. How were the gold standards made, and is the metric fair?**
Gold standards are hand-made, one per report, and **deliberately conservative** ("silver gold"), they
don't try to be exhaustive. The metric is field-level correctness (exact + acceptable) across five
fields per finding, over the union of gold and workflow findings. Because the gold is conservative,
some workflow "extras" are actually real, so the AI modes' recall is if anything **understated**.

**Q. Why only 20 reports?**
Each gold standard is hand-built, which is expensive. 20 reports is enough to show clear, consistent
separation between the three modes across all five fields. Broader generalization is acknowledged as
future work.

**Q. Does it generalize beyond the validation set?**
Open question, honestly stated. The set spans Dutch and English reports, prose/tables/captions, and
scanned PDFs (handled via OCR), so it's varied, but it's not a guarantee for every report style.

## On scope and method

**Q. Why restrict to the Roman period?**
It's the thesis scope. Finds clearly outside the Roman window (≈ 52 BCE to 450 CE) are filtered out.
The window is deliberately generous and undated finds are kept, to avoid dropping borderline real
finds, but it's a known small risk worth naming.

**Q. What about scanned / image-only PDFs?**
Handled by OCR (Google Cloud Vision) at Layer 1, including re-OCR of pages with corrupted text layers,
with language hints for English and Dutch.

## On positioning (thesis framing)

**Q. How does this relate to existing tools (e.g. ArcheoBERTje)?**
This is an LLM-led extraction-and-normalization workflow that produces a structured, dated find table,
rather than a fine-tuned domain language model. The contribution is the pipeline design + the grounded
hybrid + the measured three-mode comparison.

**Q. Why not just use ArcheoBERTje?**
ArcheoBERTje is a BERT-style model adapted to Dutch archaeological text, it's strong at *understanding*
that language, but on its own it doesn't do the job this workflow targets: read a whole messy report and
emit a clean, **dated, deduplicated, site-resolved find table**. Using it would still require building
most of this pipeline around it (date assignment from tables, normalization, consolidation, scope
filtering, anti-hallucination grounding). It's also Dutch-focused, whereas the reports here are Dutch
*and* English. So it solves a different, narrower piece of the problem.

**Q. How does your approach differ from ArcheoBERTje?**
Different *type* of system. ArcheoBERTje is a **domain-pretrained encoder** (a fine-tuned BERT) you'd
typically use for classification or token-level tasks, after training it on labeled data.
This workflow is a **generative-LLM-led pipeline** that reads the full report zero-shot and produces the
structured summary directly, with deterministic rules grounding the output (dates from tables, names
from vocab, verbatim-quote checks). One is a language model you adapt and attach a task head to; the
other is an end-to-end extraction workflow with the model as the reader and rules as the safety net.

**Q. ArcheoBERTje vs. this: pros and cons?**
- **ArcheoBERTje (pros):** domain-tuned to Dutch archaeology so it "speaks the dialect"; small and
  cheap to run; runs locally / offline; deterministic once trained.
- **ArcheoBERTje (cons):** Dutch-centric; needs labeled training data and a task head to do anything
  end-to-end; doesn't natively produce a dated, deduplicated find table; encoder models are weaker at
  the open-ended, whole-document reasoning this task needs.
- **This workflow (pros):** end-to-end (PDF → structured dated summary); works on Dutch *and* English;
  zero-shot (no task-specific training set required); rules ground it against hallucination; measured
  95.6 % in Claude mode; a free deterministic rules-only mode exists.
- **This workflow (cons):** best mode depends on a paid, online frontier API; AI modes aren't perfectly
  reproducible; per-report cost and rate limits; coverage of the rule layer is bounded by the
  vocabularies.

**Q. What's left before final delivery?**
Repo cleanup for public release (done/in progress), finishing the thesis write-up, and any final
polish the meeting surfaces. The workflow itself is feature-complete and evaluated.

## On the data and inputs

**Q. Where do the reports come from, and what kind are they?**
Real-world archaeological "grey literature", excavation reports, mostly Dutch and English, including
scanned PDFs. They describe finds inconsistently: in running prose, in tables, and in figure captions,
often covering several sites in one document. That variety is the whole challenge.

**Q. Where do the vocabularies and date tables come from?**
From source pottery/period vocabularies (CSV) in `data/vocabularies/`, which are the single source of
truth for canonical names and their date ranges. The regex detection patterns in `data/patterns/` are
generated from those vocabularies. So names and dates are anchored to a controlled reference, not
invented per run.

**Q. What happens to a pottery type that isn't in the vocabulary?**
The pure rule layer can miss it (coverage is bounded by the vocab). The LLM read mitigates this, it
can surface a find described in prose even if the term isn't in the pattern list, but its date still
has to come from the tables or stay undated, so it can't fabricate a chronology.

## On how findings are built (general, not code)

**Q. How is a date range actually assigned?**
By a strict **priority order** (Layer 6): a typology/period table lookup is preferred; explicit dates
read from the surrounding text come next; and there are conflict-detection and reconciliation steps
when sources disagree. The model's own numbers are never used directly as dates.

**Q. What do "present / absent / comparison / uncertain / irrelevant" mean?**
That's the context interpretation (Layer 5): whether the report says a find *was actually found here*
(present), *was not* (absent), is a *comparison* to another site, is *uncertain*, or is *irrelevant*.
Only genuinely present finds should end up in the summary, this filtering is a big reason the AI
modes over-claim far less than rules-only.

**Q. How are duplicates and repeated mentions handled?**
Layer 7 does conservative deduplication and consolidation, the same find mentioned in prose, a table,
and a caption is collapsed into one row, and recap re-mentions are dropped when the pot is also a
specific find. Doing this *without* an AI step is exactly where rules-only over-claims.

**Q. What are the certainty levels and the reasoning columns in the output?**
Each find carries certainty levels (for the name, presence, and dates) and short LLM-reasoning fields,
plus the verbatim quote. They make every row auditable, you can see *why* the workflow made a call,
which matters for a research deliverable.

## On robustness and operation

**Q. What if a report fails or the model errors out mid-batch?**
Failures are isolated, one bad report can't kill the batch, and each report's status is reported at
the end. In Claude mode, if the whole-report hybrid step fails (e.g. a rate-limit storm), it falls
back to the rule-based output so the report still completes rather than crashing.

**Q. How long / how expensive is a run?**
Rules-only is free and fast. The AI modes cost API calls and are slower (the model reads the whole
report). Cost scales with report length and count; the validation set of 20 reports is a manageable
size. You can run reports in parallel (`BATCH_WORKERS`).

**Q. Does it scale to hundreds of reports?**
The batch runner already processes a whole folder and parallelises across reports, so it scales
operationally. The practical limits are API cost/rate limits in the AI modes and gold-standard effort
for *evaluating* at larger scale, not the pipeline itself.

## On output and reuse

**Q. Why a CSV per report rather than a database?**
A flat, one-row-per-find CSV is the simplest portable form for a thesis deliverable, easy to read,
diff, score against gold, and load into any analysis tool. The per-report grouping mirrors the inputs
and keeps provenance obvious.

**Q. Could someone else reproduce your results?**
Yes for rules-only (deterministic). For the AI modes, the exact outputs vary slightly run-to-run, but
the inputs, gold standards, and **frozen outputs + scores** are all in the repo, so the reported
figures can be re-checked directly.

**Q. Is the output tied to your own naming, or does it map to a standard?**
Each find is also mapped to the Dutch national standard (ABR/Archis) via the `std_*` columns, so the
output drops into national heritage workflows (Archis) without re-coding. The mapping is deterministic
and default-on, and is interoperability only (not part of the five scored fields).

## Things you should be able to state confidently from memory

- **The deliverable:** one pottery-summary CSV per report.
- **The five scored fields:** site name, pottery name, typology, start date, end date.
- **The three modes and their headline scores:** Claude 95.6 %, Llama 77.3 %, Rules-only 47.9 %.
- **The one-line design pitch:** *the LLM reads and judges; the rules constrain and verify.*
- **The single most convincing result:** site name goes from 3.3 % (rules-only) to 95.9 % (Claude).

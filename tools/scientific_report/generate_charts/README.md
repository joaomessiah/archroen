# Thesis chart generator

`generate_charts.py` produces the seven figures used in the thesis evaluation chapter,
comparing the three workflow modes - **Rules-only**, **Claude** and **Llama** - on the
granular evaluation results.

## What it does

The script reads the per-report granular evaluation summaries (one `granular_summary.csv`
per mode) and renders seven publication-ready charts. It is:

- **Read-only.** It never runs the pipeline and never regenerates or modifies `granular_detail.csv` or
  `granular_summary.csv`; it only reads existing summaries.
- **Deterministic.** All computation (matching counts into verdicts, percentages, medians) is
  plain Python - no AI/LLM involvement - so the same inputs always produce the same charts.
- **Self-contained.** It carries its own copies of the helpers it needs (font setup, palette,
  summary loading, statistics, figure helpers), so it has no dependency on any other script.

### The seven charts

| # | Chart | Shows |
|---|-------|-------|
| 1 | Overall Correctness by Workflow Mode | Correct (Exact + Acceptable) share, Rules-only vs Claude vs Llama |
| 2 | Extraction Performance by Source Type - Claude | 4 verdicts per source type |
| 3 | Extraction Performance by Source Type - Llama | 4 verdicts per source type |
| 4 | Correctness by Source Type - Claude vs Llama | Correct share per source type |
| 5 | Extraction Performance by Field - Claude | 4 verdicts per field |
| 6 | Extraction Performance by Field - Llama | 4 verdicts per field |
| 7 | Per-Report Correctness Distribution - Claude vs Llama | Spread of per-report Correct scores |

**Verdicts:** `Correct` (= Exact + Acceptable) / `Incorrect` / `Missing` / `Overclaim`.
**Source types:** New reports / Old reports / OCR reports / Tables (inferred from the report id).

## Requirements

- Python with `matplotlib`, `numpy`, `pandas`. These are in the repo's `requirements.txt`, so a
  one-time `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (from the repo
  root) installs everything the tool needs. If the repo's `.venv` is already set up, you're ready.
- **Fonts: nothing to install.** The charts use a Times New Roman style. The script picks a font
  automatically and never stops over fonts:
  1. a real **Times New Roman** if your computer already has one (typical on Windows/macOS), else
  2. the **Liberation Serif** font bundled in this folder (`fonts/`) - a free, look-alike of Times
     New Roman that is used automatically with no setup, else
  3. another Times-like serif, or finally Matplotlib's built-in serif (with a short notice).

  In short: it just works. It prints a `[fonts]` line telling you which font it used.

## Inputs

Three `granular_summary.csv` files, **all required** (the script fails if a flag is missing or a
file does not exist):

| Flag | Points to |
|------|-----------|
| `--claude` | the Claude run's `granular_summary.csv` |
| `--llama` | the Llama run's `granular_summary.csv` |
| `--rules_only` | the Rules-only run's `granular_summary.csv` |

These summaries are produced by the evaluation script (`evaluation/evaluate_granular.py`) for
each mode's pipeline output. There are intentionally **no default paths** - you always state
which summaries to chart.

## Output

Seven PNG files. By default they are written to a `charts_output/` folder next to the script
(`tools/scientific_report/generate_charts/charts_output/`). Override with `--output-dir`.

## Fonts

All chart text is rendered in a **Times New Roman style**. You do not need to install
anything - the script resolves a font automatically and never fails over fonts.

**Which font it uses (first match wins):**

1. A real **Times New Roman** if your operating system already provides one (usual on
   Windows and macOS).
2. Otherwise the **Liberation Serif** font bundled in this folder under `fonts/` (usual on
   Linux, where Times New Roman is rarely present).
3. Otherwise another Times-like serif found on the system (e.g. Tinos, Nimbus Roman).
4. As a last resort, Matplotlib's built-in serif - with a short `[fonts]` notice.

The script prints a `[fonts]` line on every run stating which font was chosen.

**How they are loaded.** The bundled fonts are *not* installed into your operating system.
The script hands the `.ttf` files in `fonts/` directly to Matplotlib
(`font_manager.addfont`), which reads them with its own built-in engine. Because `.ttf` is a
universal format and this path is identical on every platform, the bundled font works the same
on **Linux, Windows and macOS**, with no system install and no admin rights.

**Why Liberation Serif is the bundled fallback.** Times New Roman is Microsoft-proprietary and
cannot be legally bundled or downloaded with this project. Liberation Serif is a free font under
the **SIL Open Font License 1.1** (so it *can* be redistributed here) that is **metrically
compatible** with Times New Roman - same character widths and spacing, near-identical look. It
therefore preserves the Times New Roman appearance on any machine that lacks the real font. See
`fonts/NOTICE.txt` for the license.

## Usage (step by step)

You do not need to be a programmer to run this. Follow these steps.

### Step 1 - Open a terminal in the project folder

A "terminal" is a window where you type commands.

- **Windows:** open the project folder in File Explorer, click the address bar, type `cmd`, and
  press Enter.
- **macOS:** open the **Terminal** app, type `cd ` (with a space), drag the project folder onto
  the window, and press Enter.
- **Linux:** right-click the project folder and choose "Open in Terminal".

You should now be "inside" the project folder (the one that contains the `tools/` and
`output_files/` folders). Everything below is run from there.

### Step 2 - Have the three evaluation files ready

The tool needs **one `granular_summary.csv` file for each of the three modes** (Rules-only,
Claude, Llama). These are produced by the evaluation step of the project for each run. You just
need to know where they are on disk. In a typical project they live under
`output_files/evaluation/`, for example:

- `output_files/evaluation/workflow_evaluation_sample_mode_claude/granular_summary.csv`
- `output_files/evaluation/workflow_evaluation_sample_mode_llama/granular_summary.csv`
- `output_files/evaluation/workflow_evaluation_sample_mode_rules_only/granular_summary.csv`

If you reviewed and hand-corrected a `granular_summary.csv`, the charts will use your corrected
numbers - the tool reads the file exactly as it is and never overwrites it.

### Step 3 - Run the command

Copy the whole block below and paste it into the terminal, then press Enter. (The `\` at the end
of each line just lets one command span several lines - keep them.)

```bash
.venv/bin/python3 tools/scientific_report/generate_charts/generate_charts.py \
  --claude     output_files/evaluation/workflow_evaluation_sample_mode_claude/granular_summary.csv \
  --llama      output_files/evaluation/workflow_evaluation_sample_mode_llama/granular_summary.csv \
  --rules_only output_files/evaluation/workflow_evaluation_sample_mode_rules_only/granular_summary.csv
```

On **Windows**, replace `.venv/bin/python3` with `.venv\Scripts\python` and put everything on a
single line (remove the `\` line-breaks).

If your three files are somewhere else, just replace the three paths after `--claude`,
`--llama` and `--rules_only` with the locations of your files.

### Step 4 - Find your charts

When it finishes you will see lines like:

```
[fonts] using Times New Roman.
.../tools/scientific_report/generate_charts/charts_output/1_overall_correctness_by_mode_grayscale.png
... (seven files) ...
Done: 7 thesis charts generated.
```

The seven `.png` images are now in the **`charts_output/`** folder next to the script
(`tools/scientific_report/generate_charts/charts_output/`). Open that folder to view or insert them
into the thesis.

To save the charts in a different folder, add `--output-dir` at the end, e.g.:

```bash
.venv/bin/python3 tools/scientific_report/generate_charts/generate_charts.py \
  --claude     <claude_summary.csv> \
  --llama      <llama_summary.csv> \
  --rules_only <rules_only_summary.csv> \
  --output-dir my_charts
```

### If something goes wrong

- **"the following arguments are required: ..."** - one of the three `--claude` / `--llama` /
  `--rules_only` files was not given. Add the missing one.
- **"Input file not found: ..."** - a path is wrong or the file was moved. Check the path you
  typed points to a real `granular_summary.csv`.
- **A `[fonts]` notice about a fallback font** - this is not an error; the charts are still
  produced, just in a slightly different (still serif) font.

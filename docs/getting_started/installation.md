# Installation

This takes about 10 minutes. First make sure you've done the one-time setup in
[prerequisites.md](prerequisites.md) (you need **Python 3.11 or newer**; 3.12 is recommended).

Open the terminal you set up in [prerequisites.md](prerequisites.md) (**PowerShell** on Windows,
**Terminal** on macOS/Linux). Commands are given for **macOS / Linux** and **Windows** separately: run
the block for **your** operating system, and run every command from inside the project folder. macOS and
Linux use the same commands throughout.

---

## 1. Get the project onto your computer

Two ways; pick **one**.

**Option A: Download a ZIP** (simplest, no Git needed)

1. Open the project's [GitHub page](https://github.com/joaomessiah/archroen) in your web browser.
2. Click the green **`< > Code`** button, then **Download ZIP**.
3. Find the downloaded `.zip` file and **unzip** (extract) it. You can put the resulting folder
   anywhere, for example your Desktop.

**Option B: Clone with Git** (best if you'll pull updates later)

```bash
git clone https://github.com/joaomessiah/archroen.git
```

(This downloads the project into a new `archroen/` folder in your current location.)

---

## 2. Go into the project folder

In the terminal, type `cd ` (with a trailing space), then drag the project folder onto the terminal
window to fill in its path, and press Enter. For example:

```bash
cd path/to/archroen
```

(The folder is named `archroen` if you cloned it, or `archroen-main` if you downloaded the ZIP.)

The remaining steps are the same for both download options.

---

## 3. Create a virtual environment

A **virtual environment** is an isolated Python setup just for this project. It keeps this project's
packages from interfering with anything else on your computer. You only do this once.

**macOS / Linux:**

```bash
python3 -m venv .venv
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
```

This creates a hidden `.venv/` folder inside the project.

---

## 4. Install the dependencies

This installs the extra packages the project needs, into the environment you just created.

**macOS / Linux:**

```bash
.venv/bin/pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\pip install -r requirements.txt
```

Only three packages are needed to **run the pipeline**; the rest power the optional figure/map tools
and the case study:

| Package | What it's for |
|---|---|
| **PyMuPDF** | reads text out of PDF reports |
| **requests** | talks to the cloud AI models and the OCR service over the internet |
| **python-dotenv** | auto-loads your API keys from a local `.env` file (see [api_keys.md](api_keys.md)) |
| **ollama** *(optional)* | only if you run a local AI model (*local-llama* mode) |
| **matplotlib, numpy, pandas** | the evaluation charts |
| **geopandas, shapely, pyproj** | the Roman-villa maps |
| **seaborn** | the aoristic / Monte Carlo case-study figures |
| **rdflib** *(maintenance only)* | rebuilding the ABR maps; never imported at runtime |

> The geospatial packages (**geopandas**, **pyproj**) are occasionally slow or awkward to install. If
> they fail, the **core pipeline still runs** perfectly; you just can't regenerate the maps. See
> [Troubleshooting](#troubleshooting) below.

---

## 5. Check it worked

**macOS / Linux:**

```bash
.venv/bin/python3 -c "import fitz, requests; print('OK')"
```

**Windows (PowerShell):**

```powershell
.venv\Scripts\python -c "import fitz, requests; print('OK')"
```

If it prints `OK`, the core installation is complete.

> **Tip: shorter commands.** The guides here always spell out the full `.venv/...` path so the commands
> work whether or not you've "activated" the environment. If you'd rather type just `python` and `pip`,
> you can **activate** the environment once per terminal window:
> - **macOS / Linux:** `source .venv/bin/activate`
> - **Windows (PowerShell):** `.venv\Scripts\Activate.ps1` (in Command Prompt instead, use `.venv\Scripts\activate.bat`)
>
> After activating, `python run_pipeline.py …` works directly. Opening a new terminal later means
> activating again (or just keep using the full-path form).

---

## Next steps

- If you want to use the AI-assisted modes, set up your keys: [api_keys.md](api_keys.md).
- To run the workflow for the first time: [quickstart.md](quickstart.md) (works with **no key** in
  Rules-only mode).

---

## Troubleshooting

| Symptom | What to do |
|---|---|
| `python3: command not found` (macOS / Linux) | Install Python 3.12 (see [prerequisites.md](prerequisites.md)). On a few systems the command is `python`, not `python3`. |
| `py` or `python` not recognized (Windows) | Reinstall Python from [python.org](https://www.python.org/downloads/) and tick **"Add Python to PATH"** during setup, then open a **new** terminal. |
| `Activate.ps1 … running scripts is disabled on this system` (Windows) | PowerShell blocks scripts by default. Either run `Set-ExecutionPolicy -Scope Process RemoteSigned` in that window and try again, or simply use the full-path commands (no activation needed), or use Command Prompt with `.venv\Scripts\activate.bat`. |
| `ModuleNotFoundError: No module named 'fitz'` (or similar) | You ran your system Python instead of the project's. Use the `.venv/bin/python3` (macOS/Linux) or `.venv\Scripts\python` (Windows) form, or activate the environment first. |
| `pip: command not found` | Use the module form instead: `.venv/bin/python3 -m pip install -r requirements.txt` (macOS/Linux) or `.venv\Scripts\python -m pip install -r requirements.txt` (Windows). |
| `geopandas` / `pyproj` fails to build or install | Those are only for the maps. The core pipeline runs without them, so you can continue; reinstall them later if you need the map figures. |
| The install is very slow | The geospatial and plotting packages are large. Give it a few minutes; it's a one-time download. |

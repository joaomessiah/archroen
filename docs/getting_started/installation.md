# Installation

This takes about 10 minutes. First make sure you've done the one-time setup in
[prerequisites.md](prerequisites.md) (you need **Python 3.12**).

There are two ways to get the project onto your computer. Pick **one**:

- **Option A — Download a ZIP** (simplest; no Git needed)
- **Option B — Clone with Git** (best if you'll pull updates later)

---

## Option A — Download a ZIP

1. Open the project's page on GitHub in your web browser.
2. Click the green **`< > Code`** button, then **Download ZIP**.
3. Find the downloaded `.zip` file and **unzip** (extract) it. You can put the resulting folder
   anywhere — for example your Desktop.
4. Note the folder's location; you'll point the terminal at it in the next step.

## Option B — Clone with Git

In the terminal, run (replace the URL with the project's actual address):

```bash
git clone <REPOSITORY-URL>
```

This creates a project folder in your current location.

---

## Set up the project

The remaining steps are the same for both options.

**1. Go into the project folder.** In the terminal, type `cd ` (with a space), then drag the project
folder onto the terminal window to fill in its path, and press Enter. For example:

```bash
cd ~/Desktop/JM-Thesis/Workflow
```

**2. Create a "virtual environment"** — an isolated, project-specific Python setup, so this project's
packages don't interfere with anything else on your computer:

```bash
python3 -m venv .venv
```

This creates a hidden `.venv/` folder inside the project. You only do this once.

**3. Install the project's dependencies** (the extra packages it needs) into that environment:

```bash
.venv/bin/pip install -r requirements.txt
```

> **Windows note:** on Windows the path uses a backslash — use `.venv\Scripts\pip install -r requirements.txt`.

This installs:

| Package | What it's for |
|---|---|
| **PyMuPDF** | reads text out of PDF reports |
| **requests** | talks to the cloud AI models and OCR service over the internet |
| **ollama** *(optional)* | only needed if you run a local AI model (*local-llama* mode) |

## Check it worked

From the project folder, run:

```bash
.venv/bin/python3 -c "import fitz, requests; print('OK')"
```

If it prints `OK`, the installation is complete.

## Next steps

- If you want to use the AI-assisted modes, set up your keys: [api_keys.md](api_keys.md).
- To run the workflow for the first time: [quickstart.md](quickstart.md) (works with **no key** in
  Rules-only mode).

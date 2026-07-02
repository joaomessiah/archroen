# Prerequisites

This page assumes **no programming background**. It explains the few things you need on your computer
before you install the workflow. If you already work with Python, skip ahead to
[installation.md](installation.md).

## What you'll need

- A computer running **Windows, macOS, or Linux**.
- About **20 minutes** total for the one-time setup (this page plus [installation.md](installation.md)).
- **Python 3.12** (a free programming language the workflow is written in; 3.11 or newer also works). See below.
- *(Optional)* an **AI model API key**, only if you want to run the AI-assisted modes. The workflow
  also runs with no key at all in *Rules-only mode*, except for OCR of scanned PDFs (a Google Vision
  key). See [api_keys.md](api_keys.md).

You do **not** need to know how to program. You'll copy and paste a handful of commands.

## The terminal

A **terminal** (also called a "command line" or "console") is a window where you type commands
instead of clicking buttons. You'll use it both to set things up and to run the workflow.

- **Windows:** press the Start button, type `PowerShell`, and open it.
- **macOS:** press `Cmd + Space`, type `Terminal`, and press Enter.
- **Linux:** press `Ctrl + Alt + T`, or search for `Terminal` in your applications.

When you see a box like the one below, copy the command inside it into the terminal and press Enter to
run it:

```bash
python3 --version
```

(On Windows, the command is `py --version` instead.)

## Python 3.12

**Python** is the language the workflow is written in; you need it installed to run anything.

Check whether you already have it. Paste this into the terminal.

**macOS / Linux:**

```bash
python3 --version
```

**Windows (PowerShell):**

```powershell
py --version
```

If it prints `Python 3.12.x` (or 3.11 or newer), you're ready. If it says the command was not
found, or shows an older version (3.10 or below), install Python 3.12:

- **Windows / macOS:** download the installer from [python.org/downloads](https://www.python.org/downloads/).
  On Windows, tick **"Add Python to PATH"** during installation.
- **Linux:** install it with your package manager, e.g. `sudo apt install python3.12 python3.12-venv`
  on Ubuntu/Debian.

## Git (optional)

**Git** is a tool for downloading and tracking code. It's the tidiest way to get the project, but it's
**optional**. [installation.md](installation.md) also explains how to download the project as a ZIP
file, with no Git needed at all. If you'd like to use Git, get it from [git-scm.com/downloads](https://git-scm.com/downloads).

## Next step

Once Python 3.12 is installed, continue to [installation.md](installation.md).

# API keys

The workflow can use a cloud **AI model** to improve its reading of the reports. To do that, it needs
an **API key** — a private password-like string that identifies your account with the AI provider and
lets the workflow make requests on your behalf.

> **You can skip this entirely.** In **Rules-only mode** the workflow uses no AI and needs no key — it
> runs fully offline and free. Set this up only if you want to run **Claude mode** or **Llama mode**.
> See [how_to_run.md](how_to_run.md) for choosing a mode.

## Which key for which mode

| Mode | Key you need | Where to get it |
|---|---|---|
| **Rules-only mode** | *none* | — |
| **Claude mode** | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| **Llama mode** | `LLM_API_KEY` | [Together AI](https://api.together.xyz) (the host used in the thesis) |

There is also an optional key for reading **scanned** (image-only) PDFs:

| Purpose | Key | Where to get it |
|---|---|---|
| OCR for scanned PDFs | `GOOGLE_VISION_API_KEY` | [Google Cloud Vision](https://cloud.google.com/vision) |

## How to set your keys

The workflow reads keys from your computer's **environment variables**, not from inside the code, so
your keys are never written into the project files.

1. In the project folder there's a template called **`.env.example`**. Make a copy named **`.env`**:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` in any text editor and fill in the key(s) you have. It looks like this — paste your key
   after the `=` sign (no quotes, no spaces):

   ```
   GOOGLE_VISION_API_KEY=your-google-vision-key-here
   ANTHROPIC_API_KEY=your-anthropic-key-here
   LLM_API_KEY=your-together-key-here
   ```

   Leave blank any key you don't need.

3. Before running the workflow, **load** the keys into your terminal session:

   ```bash
   set -a && . ./.env && set +a
   ```

   (You do this once per terminal window, before running the workflow.)

## Cost

- **Rules-only mode is free** — no AI, no key, no charge.
- **Claude mode** and **Llama mode** call a paid cloud service. Costs are usage-based (you pay the AI
  provider per amount of text processed). For a small batch of reports this is typically modest, but
  check your provider's pricing before running large batches.

## Keep your keys private

Your `.env` file contains real keys — treat it like a password.

- **Never share it** or paste your keys into emails, chats, or issues.
- **Never commit it to Git.** The project is set up to ignore `.env`, so it won't be uploaded by
  accident — but don't move your keys into `config.py` or any tracked file.

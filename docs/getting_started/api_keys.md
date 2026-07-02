# API keys

The workflow can use a cloud **AI model** to improve its reading of the reports. To do that, it needs
an **API key**. A key is a private, password-like string. It identifies your account with the AI
provider and lets the workflow make requests on your behalf.

> **You can skip this entirely.** In **Rules-only mode** the workflow uses no AI and needs no key. It
> runs fully offline and free. (One exception: OCR of scanned PDFs uses the Google Vision API, so it
> needs a key; turn it off with `OCR_ENABLED=False`.) Set this up only if you want to run **Claude
> mode** or **Llama mode**.
> See [how_to_run.md](how_to_run.md) for choosing a mode.

## Which key for which mode

| Mode | Key you need | Where to get it |
|---|---|---|
| **Rules-only mode** | *none* | *not applicable* |
| **Claude mode** | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| **Llama mode** | `LLM_API_KEY` | [Together AI](https://api.together.xyz) (the host used in the research) |

There is also an optional key for reading **scanned** (OCR) PDFs:

| Purpose | Key | Where to get it |
|---|---|---|
| OCR for scanned PDFs | `GOOGLE_VISION_API_KEY` | [Google Cloud Vision](https://cloud.google.com/vision) |

## How to set your keys

The workflow reads keys from your computer's **environment variables**, not from inside the code. This
means your keys are never written into the project files.

1. In the project folder there's a template called **`.env.example`**. Make a copy of that file and name it **`.env`**:

   **macOS / Linux:**

   ```bash
   cp .env.example .env
   ```

   **Windows (PowerShell):**

   ```powershell
   Copy-Item .env.example .env
   ```

2. Open `.env` in any text editor and fill in the key(s) you have. It looks like this. Paste each key
   between the quotes, after the `=` sign:

   ```
   GOOGLE_VISION_API_KEY="your-google-vision-key-here"

   ANTHROPIC_API_KEY="your-anthropic-key-here"

   LLM_API_KEY="your-together-key-here"
   ```

   Leave any key you don't need as the empty `""`.

3. That's usually all you need: `config.py` **auto-loads** the `.env` file (via python-dotenv), so the
   keys are picked up automatically when you run the workflow.

> **Claude mode without an API key:** if you set `HYBRID_USE_CLAUDE_CLI=True` in `config.py`, Claude
> mode runs through the Claude Code CLI (using your Claude subscription) and does **not** need
> `ANTHROPIC_API_KEY`.

## Cost

- **Rules-only mode is free:** no AI, no key, no charge (apart from OCR of scanned PDFs, which uses the paid Google Vision API).
- **Claude mode** and **Llama mode** call a paid cloud service. Costs are usage-based: you pay the AI
  provider for the amount of text processed. For a small batch of reports the cost is typically modest,
  but check your provider's pricing before running large batches.

## Keep your keys private

Your `.env` file contains real keys. Treat it like a password.

- **Never share it** or paste your keys into emails, chats, or issues.
- **Never commit it to Git.** The project is set up to ignore `.env`, so it won't be uploaded by
  accident. Just don't move your keys into `config.py` or any tracked file.

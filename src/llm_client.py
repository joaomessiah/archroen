"""
LLM abstraction layer. Call call_llm(prompt) anywhere in the pipeline.
To switch providers, change LLM_PROVIDER in config.py.

Providers:
  - "ollama":    local models. Uses config.LLM_MODEL.
  - "cloud":     any OpenAI-compatible cloud API (Together / OpenRouter / Fireworks /
                 Groq / Cerebras / ...). Uses config.LLM_API_BASE_URL, LLM_API_MODEL and
                 the key from config.LLM_API_KEY or the LLM_API_KEY env var.
  - "anthropic": Claude via the Anthropic API. Uses config.ANTHROPIC_MODEL and the key
                 from config.ANTHROPIC_API_KEY or the ANTHROPIC_API_KEY env var.
"""

import ollama as _ollama


def call_llm(prompt: str, model: str = None, max_tokens: int = None,
             output_schema: dict = None) -> str:
    # max_tokens caps the OUTPUT length. Pass a large value for big structured outputs
    # (e.g. the hybrid finds list); leave None for short sub-task replies (a safe default
    # is applied per backend). Without it, hosts like Together truncate at a tiny default.
    # output_schema enforces a JSON shape — only the 'anthropic' (Claude) backend supports it;
    # 'cloud'/'ollama' ignore it and rely on the prompt + best-effort parsing.
    from config import LLM_PROVIDER

    if LLM_PROVIDER == "ollama":
        from config import LLM_MODEL
        return _call_ollama(prompt, model or LLM_MODEL, max_tokens)

    if LLM_PROVIDER == "cloud":
        import os
        from config import LLM_API_BASE_URL, LLM_API_MODEL, LLM_API_KEY
        api_key = LLM_API_KEY or os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No cloud API key found. Set LLM_API_KEY in config.py or the "
                "LLM_API_KEY environment variable (required when LLM_PROVIDER='cloud')."
            )
        return _call_openai_compatible(prompt, model or LLM_API_MODEL,
                                       LLM_API_BASE_URL, api_key, max_tokens)

    if LLM_PROVIDER == "anthropic":
        # Route the sub-task LLM (Layers 5/6, pottery context/dedup/consolidation) through
        # Claude, so the whole pipeline can run on a single provider (no Together/Claude mix).
        return call_claude(prompt, model=model, max_tokens=max_tokens or 4096,
                           output_schema=output_schema)

    raise ValueError(
        f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}. Supported: 'ollama', 'cloud', 'anthropic'."
    )


def _call_ollama(prompt: str, model: str, max_tokens: int = None) -> str:
    # temperature=0 + fixed seed → greedy, reproducible decoding (no run-to-run jitter
    # in context labels/dates). Important for a thesis where results must be repeatable.
    options = {"temperature": 0, "seed": 0}
    if max_tokens:
        options["num_predict"] = max_tokens   # cap output length (Ollama's max_tokens equivalent)
    try:
        response = _ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options=options,
        )
    except Exception as e:                     # server down, or model not pulled: make it actionable
        raise RuntimeError(
            f"local-llama mode could not reach Ollama ({type(e).__name__}: {e}). Make sure the "
            f"Ollama server is running and the model is pulled: `ollama pull {model}`. "
            f"See https://ollama.com."
        ) from e
    return response["message"]["content"].strip()


def _call_openai_compatible(prompt: str, model: str, base_url: str, api_key: str,
                            max_tokens: int = None) -> str:
    """OpenAI-compatible chat-completions call (works for Together / OpenRouter /
    Fireworks / Groq / Cerebras). Retry/backoff on rate limits (429) and transient
    5xx. temperature=0 + seed for reproducibility.

    max_tokens caps the OUTPUT; it defaults to 4096 so a large structured reply (e.g. the
    hybrid finds list) is not silently truncated by the host's small default (Together's is
    ~512), which would corrupt the JSON and yield zero parsed finds on big reports."""
    import time
    import requests

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "seed": 0,
        "max_tokens": max_tokens or 4096,
    }

    delay = 2.0
    last_err = None
    deadline = time.time() + 240   # total budget: a wedged endpoint can't freeze a worker for >~4 min
    for _ in range(6):
        if time.time() > deadline:
            break
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=90)
        except requests.RequestException as e:  # network hiccup → retry
            last_err = e
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        if resp.status_code in (402, 429) or resp.status_code >= 500:
            # 402 is retried too: Together returns transient/spurious 402s under concurrent load
            # (the same request succeeds on retry). A genuinely exhausted balance keeps returning
            # 402 and eventually raises below at the deadline, with the body surfaced.
            wait = resp.headers.get("retry-after")
            time.sleep(float(wait) if wait else delay)
            delay = min(delay * 2, 30)
            last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            continue
        if resp.status_code >= 400:
            # Non-retryable client error — surface the provider's reason instead of a bare HTTPError.
            raise RuntimeError(f"Cloud LLM HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()["choices"][0]["message"]["content"].strip()

    raise RuntimeError(f"Cloud LLM request failed after retries: {last_err}")


def _resolve_claude_cli(path: str) -> str:
    """Resolve the Claude Code CLI executable. Uses `path` if it's on PATH or a real file;
    otherwise auto-discovers the native binary bundled with the VS Code / Cursor extension
    (so it works without `claude` being on PATH, e.g. in a sandboxed runner). Picks the
    newest version found."""
    import os
    import glob
    import shutil
    if shutil.which(path) or os.path.isfile(path):
        return path
    globs = [
        "~/.vscode*/extensions/anthropic.claude-code-*/resources/native-binary/claude",
        "~/.cursor*/extensions/anthropic.claude-code-*/resources/native-binary/claude",
        "~/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude",
    ]
    cands = []
    for g in globs:
        cands += glob.glob(os.path.expanduser(g))
    if cands:
        return max(cands, key=os.path.getmtime)
    return path  # let subprocess raise a clear FileNotFoundError


def call_claude_cli(prompt: str, model: str = None) -> str:
    """Drive Claude through the Claude Code CLI in headless/print mode (`claude -p`),
    which authenticates with the user's CLAUDE **Max/Pro subscription** — no API key, no
    per-token charge. Lets the hybrid extractor run on a Max plan instead of the paid API.

    Note: subject to Claude Code's subscription usage limits and slower than the REST API
    (each call starts a CLI session). The prompt is passed on stdin to avoid arg-length
    limits. Requires the `claude` CLI installed + logged in on the machine running this."""
    import subprocess
    from config import CLAUDE_CLI_PATH, CLAUDE_CLI_MODEL
    cmd = [_resolve_claude_cli(CLAUDE_CLI_PATH or "claude"), "-p", "--output-format", "text"]
    mdl = model or CLAUDE_CLI_MODEL
    if mdl:
        cmd += ["--model", mdl]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Claude CLI not found ({CLAUDE_CLI_PATH or 'claude'}). Install Claude Code and "
            "log in with your Max plan, or set CLAUDE_CLI_PATH in config.py."
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI failed (rc={proc.returncode}): {proc.stderr[:300]}")
    return proc.stdout.strip()


def call_claude(prompt: str, model: str = None, max_tokens: int = 4096,
                output_schema: dict = None, timeout: int = 180) -> str:
    """Anthropic Messages API (REST, no SDK dependency). Used by the Claude-hybrid
    full-report extractor. Key from config.ANTHROPIC_API_KEY or the ANTHROPIC_API_KEY env
    var. temperature=0 for reproducibility; retry/backoff on 429/5xx.

    If `output_schema` is given, request structured outputs (output_config.format) so the API
    GUARANTEES valid JSON matching the schema — this removes the brittle hand-parsing and the
    silent data loss when a verbatim quote contains a `"` (which broke raw-text JSON)."""
    import os
    import time
    import requests
    from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_ENDPOINT, ANTHROPIC_VERSION

    api_key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No Anthropic API key. Set ANTHROPIC_API_KEY in config.py or the environment "
            "to use the Claude-hybrid extractor (POTTERY_HYBRID_LLM_USE)."
        )
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    mdl = model or ANTHROPIC_MODEL
    payload = {
        "model": mdl,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Opus 4.7/4.8 removed the sampling params (temperature/top_p/top_k) — sending any
    # returns HTTP 400. Older models (sonnet-4-6, opus-4-6, …) accept temperature=0 for
    # reproducible decoding, so only add it when the model isn't opus-4-7/4-8.
    if "opus-4-8" not in mdl and "opus-4-7" not in mdl:
        payload["temperature"] = 0
    if output_schema is not None:
        payload["output_config"] = {"format": {"type": "json_schema", "schema": output_schema}}
    delay = 2.0
    last_err = None
    # `timeout` is the per-request read timeout. Big non-streaming generations (the hybrid's
    # ~16k-token finds list) finish server-side before any byte returns, so they need a generous
    # read timeout; short sub-task calls keep the small default. The total deadline bounds a
    # rate-limit storm while still allowing one full long request.
    deadline = time.time() + max(360, timeout + 120)
    for _ in range(6):
        if time.time() > deadline:
            break
        try:
            resp = requests.post(ANTHROPIC_ENDPOINT, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_err = e; time.sleep(delay); delay = min(delay * 2, 30); continue
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = resp.headers.get("retry-after")
            time.sleep(float(wait) if wait else delay); delay = min(delay * 2, 30)
            last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}"); continue
        if resp.status_code >= 400:
            # Non-retryable client error (e.g. 400 "prompt is too long: N tokens > 200000 maximum").
            # Surface Anthropic's reason instead of a bare HTTPError so the cause is visible in logs.
            raise RuntimeError(f"Anthropic HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        # messages API returns content as a list of blocks; concatenate the text blocks
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text").strip()
    raise RuntimeError(f"Anthropic request failed after retries: {last_err}")

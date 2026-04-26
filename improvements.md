# Making Recall Model-Agnostic

This document describes the exact changes needed to support local models
(Ollama, LM Studio, vLLM, etc.) alongside Anthropic Claude.

---

## Overview

| Mode | Env Vars Required | Client Used |
|---|---|---|
| Anthropic (default) | `ANTHROPIC_API_KEY` | `anthropic` |
| Local / OpenAI-compatible | `RECALL_API_BASE` + `RECALL_MODEL` | `openai` |
| OpenAI | `OPENAI_API_KEY` + `RECALL_MODEL` | `openai` |

---

## Step 1 — Install the `openai` package

Add `openai` to your dependencies.

**File: `pyproject.toml`**

```toml
# BEFORE
dependencies = [
    "typer>=0.12.0",
    "anthropic>=0.25.0",
    "rich>=13.7.0",
    "python-dotenv>=1.0.0",
]

# AFTER
dependencies = [
    "typer>=0.12.0",
    "anthropic>=0.25.0",
    "openai>=1.30.0",        # ← add this
    "rich>=13.7.0",
    "python-dotenv>=1.0.0",
]
```

Then run:
```bash
pip install -e .
```

---

## Step 2 — Update `config.py`

Add three new env var helpers to detect which mode the user is running.

**File: `recall/config.py`**

```python
# BEFORE
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path.home() / ".recall"
DB_PATH = APP_DIR / "recall.db"
ENV_PATH = Path(".env")

def ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)

def get_api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")

def get_model() -> str:
    return os.getenv("RECALL_MODEL", "claude-sonnet-4-20250514")


# AFTER
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path.home() / ".recall"
DB_PATH = APP_DIR / "recall.db"
ENV_PATH = Path(".env")

def ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)

def get_anthropic_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")

def get_openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")

def get_api_base() -> str | None:
    """Base URL for local/custom OpenAI-compatible servers."""
    return os.getenv("RECALL_API_BASE")          # e.g. http://localhost:11434/v1

def get_model() -> str:
    return os.getenv("RECALL_MODEL", "claude-sonnet-4-20250514")

def get_local_api_key() -> str:
    """Some local servers (Ollama) need any non-empty string as the key."""
    return os.getenv("RECALL_API_KEY", "recall")

def is_local_mode() -> bool:
    """True when user has set a local API base URL."""
    return get_api_base() is not None

def is_openai_mode() -> bool:
    """True when user has set an OpenAI API key but no local base."""
    return get_openai_key() is not None and not is_local_mode()

def get_api_key() -> str | None:
    """
    Backward-compatible: returns whichever key is relevant for the current mode.
    Used in main.py for the 'missing key' check.
    """
    if is_local_mode():
        return get_local_api_key()          # always set (has default)
    if is_openai_mode():
        return get_openai_key()
    return get_anthropic_key()
```

---

## Step 3 — Rewrite `ai.py`

Replace the single Anthropic client with a router that picks the right
client based on config. The system prompts stay exactly the same.

**File: `recall/ai.py`**

```python
# FULL REPLACEMENT — paste this as the new ai.py

import json
import anthropic
from openai import OpenAI
from recall.config import (
    get_anthropic_key,
    get_api_base,
    get_model,
    get_local_api_key,
    get_openai_key,
    is_local_mode,
    is_openai_mode,
)

# ── System prompts (unchanged) ────────────────────────────────────────────────

ASK_SYSTEM = """You are Recall, an expert CLI assistant for developers.
When given a natural language description, return the exact shell command(s) to accomplish it.

Respond ONLY with valid JSON in this format:
{
  "command": "the exact command",
  "explanation": "brief one-line explanation of what it does",
  "tool": "the primary CLI tool (git/docker/azure/kubectl/pip/npm/etc)",
  "tags": ["tag1", "tag2"],
  "alternatives": ["optional alternative command if relevant"]
}

Rules:
- command must be copy-pasteable as-is (use <placeholder> for values the user must fill in)
- Keep explanation under 15 words
- tags should be 1-3 short keywords
- alternatives array can be empty []
- Respond ONLY with JSON, no markdown, no preamble"""


EXPLAIN_SYSTEM = """You are Recall, an expert CLI assistant for developers.
When given a shell command, explain it clearly for a developer.

Respond ONLY with valid JSON in this format:
{
  "summary": "one sentence summary of what this command does",
  "breakdown": [
    {"part": "command_part", "meaning": "what this part does"}
  ],
  "tool": "primary CLI tool name",
  "tags": ["tag1", "tag2"],
  "warning": "optional gotcha or danger to be aware of, or empty string"
}

Rules:
- breakdown should cover the base command + each significant flag/argument
- warning should be non-empty only if there's a real risk (data loss, destructive ops, etc.)
- Respond ONLY with JSON, no markdown, no preamble"""


# ── Client factory ─────────────────────────────────────────────────────────────

def _call_openai_compatible(system: str, user: str) -> str:
    """Handles both local models (Ollama, LM Studio) and OpenAI."""
    if is_local_mode():
        client = OpenAI(
            base_url=get_api_base(),
            api_key=get_local_api_key(),
        )
    else:
        client = OpenAI(api_key=get_openai_key())

    response = client.chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=700,
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(system: str, user: str) -> str:
    client = anthropic.Anthropic(api_key=get_anthropic_key())
    response = client.messages.create(
        model=get_model(),
        max_tokens=700,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text.strip()


def _call(system: str, user: str) -> str:
    """Route to the right backend based on config."""
    if is_local_mode() or is_openai_mode():
        return _call_openai_compatible(system, user)
    return _call_anthropic(system, user)


# ── Public API (unchanged signatures) ─────────────────────────────────────────

def ask_command(natural_language: str) -> dict:
    raw = _call(ASK_SYSTEM, natural_language)
    return json.loads(raw)


def explain_command(command: str) -> dict:
    raw = _call(EXPLAIN_SYSTEM, command)
    return json.loads(raw)
```

---

## Step 4 — Update `.env.example`

**File: `.env.example`**

```env
# ── Option 1: Anthropic Claude (default) ──────────────────────────────────────
ANTHROPIC_API_KEY=your_key_here

# ── Option 2: Local model via Ollama ──────────────────────────────────────────
# RECALL_API_BASE=http://localhost:11434/v1
# RECALL_MODEL=llama3.2

# ── Option 3: Local model via LM Studio ───────────────────────────────────────
# RECALL_API_BASE=http://localhost:1234/v1
# RECALL_MODEL=mistral-7b-instruct
# RECALL_API_KEY=lm-studio        # LM Studio needs any non-empty string

# ── Option 4: OpenAI ──────────────────────────────────────────────────────────
# OPENAI_API_KEY=sk-...
# RECALL_MODEL=gpt-4o

# ── Option 5: Any other OpenAI-compatible API (Together, Groq, etc.) ──────────
# RECALL_API_BASE=https://api.groq.com/openai/v1
# RECALL_API_KEY=your_groq_key
# RECALL_MODEL=llama3-8b-8192
```

---

## No changes needed in

- `main.py` — already calls `get_api_key()` for the missing-key check, which is updated above
- `db.py` — no AI involvement
- `models.py` — no AI involvement

---

## Quick test after changes

```bash
# Test with Ollama (make sure ollama is running: ollama serve)
export RECALL_API_BASE=http://localhost:11434/v1
export RECALL_MODEL=llama3.2
unset ANTHROPIC_API_KEY

recall ask "list all docker containers including stopped ones"

# Switch back to Claude
unset RECALL_API_BASE
unset RECALL_MODEL
export ANTHROPIC_API_KEY=your_key_here

recall ask "list all docker containers including stopped ones"
```

---

## How it works (summary)

```
User runs: recall ask "..."
                │
                ▼
         config.py checks:
         ┌─────────────────────────────────┐
         │ RECALL_API_BASE set?  → local   │
         │ OPENAI_API_KEY set?   → openai  │
         │ else                  → anthropic│
         └─────────────────────────────────┘
                │
                ▼
         ai.py routes to correct client
         (same system prompts, same output)
                │
                ▼
         main.py renders result (unchanged)
```

Total lines changed: ~60
Files changed: `pyproject.toml`, `config.py`, `ai.py`, `.env.example`
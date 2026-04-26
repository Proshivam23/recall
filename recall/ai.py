import json
import re
import anthropic
from openai import OpenAI
from recall.config import (
    get_anthropic_key,
    get_api_base,
    get_model,
    get_local_api_key,
    get_openai_key,
    get_gemini_key,
    is_local_mode,
    is_openai_mode,
    is_gemini_mode,
)

# ── System prompts ─────────────────────────────────────────────────────────────

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


def _call_gemini(system: str, user: str) -> str:
    """Gemini via its OpenAI-compatible endpoint."""
    client = OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=get_gemini_key(),
    )
    model = get_model() if get_model() != "claude-sonnet-4-20250514" else "gemini-2.0-flash"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=700,
    )
    return response.choices[0].message.content.strip()


def _call(system: str, user: str) -> str:
    """Route to the right backend based on config."""
    try:
        if is_local_mode() or is_openai_mode():
            return _call_openai_compatible(system, user)
        if is_gemini_mode():
            return _call_gemini(system, user)
        return _call_anthropic(system, user)
    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "quota" in err_str or "rate limit" in err_str or "resource_exhausted" in err_str:
            raise RuntimeError(
                "API quota or rate limit exceeded. Please check your billing details, verify your free tier limits, or wait before trying again."
            )
        if "401" in err_str or "unauthorized" in err_str or "invalid_api_key" in err_str:
            raise RuntimeError(
                "API Key is invalid or unauthorized. Please verify your .env file."
            )
        # Re-raise anything else but strip massive JSON objects if they exist
        raise RuntimeError(str(e).split("[{")[0].strip())


# ── JSON helpers ───────────────────────────────────────────────────

_HTML_TAG = re.compile(r'<[^>]+>')

def _strip_html(obj):
    """Recursively strip HTML tags from all string values in a parsed JSON structure."""
    if isinstance(obj, dict):
        return {k: _strip_html(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_html(item) for item in obj]
    if isinstance(obj, str):
        return _HTML_TAG.sub('', obj).strip()
    return obj


def _parse_json(raw: str) -> dict | list:
    """Robust JSON parser to handle small-model quirks.

    Strategy:
    1. Strip markdown code fences.
    2. Find the outermost JSON bracket pair ([...] or {...}) to discard
       any prose the model added before/after.
    3. Fix the most common tiny-model syntax errors via regex.
    4. Parse with strict=False to allow unescaped control characters.
    """
    # 1. Strip markdown code fences
    if "```" in raw:
        # Remove opening fence line (```json, ``` etc.)
        raw = re.sub(r"```[a-z]*\n?", "", raw)
        raw = raw.replace("```", "")

    raw = raw.strip()

    # 2. Extract just the JSON structure (first [ to last ] or { to })
    start_bracket = raw.find("[")
    start_brace = raw.find("{")
    if start_bracket == -1 and start_brace == -1:
        raise ValueError("No JSON found in AI response")

    if start_bracket != -1 and (start_brace == -1 or start_bracket < start_brace):
        opener, closer = "[", "]"
        start = start_bracket
    else:
        opener, closer = "{", "}"
        start = start_brace

    depth = 0
    end = start
    for i, ch in enumerate(raw[start:], start):
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                end = i
                break

    raw = raw[start : end + 1]

    # 3. Fix common tiny-model syntax errors
    raw = re.sub(r"}\s*{", "}, {", raw)   # missing comma between objects
    raw = re.sub(r",\s*]", "]", raw)       # trailing comma before ]
    raw = re.sub(r",\s*}", "}", raw)       # trailing comma before }

    # 4. Parse with strict=False (allows raw newlines/tabs inside strings)
    result = json.loads(raw, strict=False)
    # 5. Strip any HTML tags the model may have embedded in string values
    return _strip_html(result)


def ask_command(natural_language: str) -> dict:
    """Convert natural language to a CLI command."""
    raw = _call(ASK_SYSTEM, natural_language)
    return _parse_json(raw)


def explain_command(command: str) -> dict:
    """Explain what a CLI command does."""
    raw = _call(EXPLAIN_SYSTEM, command)
    return _parse_json(raw)


PIPELINE_SYSTEM = """You are Recall, an expert CLI assistant for developers.
When given a high-level goal that requires multiple shell commands, return an ordered list of steps to achieve it.

Respond ONLY with valid JSON in this format:
[
  {
    "step": "short step title (e.g. Create Docker network)",
    "command": "the exact shell command",
    "explanation": "one-line explanation of what this step does",
    "tool": "primary CLI tool"
  }
]

Rules:
- Each command must be copy-pasteable as-is.
- CRITICAL: Any command that WRITES or SETS a user-specific value (name, email, password, username, path, token, IP, etc.)
  MUST include a <placeholder> for that value. Example: `git config --global user.name "<Your Name>"`.
  A command like `git config --global user.name` with NO value is WRONG — it only reads, not writes.
- Use <placeholder> ONLY for user-supplied values, never for the CLI tool name itself.
- NEVER use placeholders for the CLI tool itself. Use concrete, real tools only (e.g. `docker`, `powershell`, `curl`).
- NEVER invent URLs, scripts, or packages that don't exist. Use well-known tools and official images.
- For container/server workloads, use `docker` commands with official Docker Hub images.
- Assume the user is on Windows with Docker Desktop installed unless otherwise stated.
- Order steps so each one builds on the previous ones.
- Keep each explanation under 15 words.
- Respond ONLY with the JSON array, no text or markdown outside it."""


# ── Pipeline step validator ────────────────────────────────────────────────────

# Patterns: (regex that matches a bare setter, placeholder to append)
_SETTER_FIXES: list[tuple[re.Pattern, str]] = [
    # git config --global user.name  (no value)
    (re.compile(r'^git\s+config\s+--global\s+user\.name\s*$'),   'git config --global user.name "<Your Name>"'),
    # git config --global user.email  (no value)
    (re.compile(r'^git\s+config\s+--global\s+user\.email\s*$'),  'git config --global user.email "<your@email.com>"'),
    # git config --global <any-key>  (no value)
    (re.compile(r'^(git\s+config\s+(?:--global\s+|--local\s+|--system\s+)?[\w.]+)\s*$'),
     None),   # generic fallback — handled below
    # npm config set <key>  (no value)
    (re.compile(r'^npm\s+config\s+set\s+(\S+)\s*$'), None),
]


def _fix_pipeline_steps(steps: list[dict]) -> list[dict]:
    """Post-process AI-generated steps to catch setter commands missing their value."""
    import re as _re

    # Matches an empty value: '' or "" or nothing at end
    _EMPTY_VAL = r"""(?:\s*(?:''|""|\s))?$"""

    for step in steps:
        cmd = step.get("command", "").strip()

        # git config [--scope] user.name  with no/empty value → inject placeholder
        if _re.match(
            r'''^git\s+config\s+(?:--\w+\s+)?user\.name(?:\s+(?:''|""))?$''', cmd
        ):
            base = _re.sub(r"""\s*(?:''|"")$""", "", cmd)
            step["command"] = base + ' "<Your Name>"'
            continue

        # git config [--scope] user.email  with no/empty value → inject placeholder
        if _re.match(
            r'''^git\s+config\s+(?:--\w+\s+)?user\.email(?:\s+(?:''|""))?$''', cmd
        ):
            base = _re.sub(r"""\s*(?:''|"")$""", "", cmd)
            step["command"] = base + ' "<your@email.com>"'
            continue

        # Generic: git config [--scope] <key>  with no/empty value → inject placeholder
        m = _re.match(
            r'''^(git\s+config(?:\s+--\w+)?\s+[\w.]+)(?:\s+(?:''|""))?$''', cmd
        )
        if m:
            step["command"] = m.group(1) + ' "<value>"'
            continue

    return steps


def ask_pipeline(goal: str) -> list[dict]:
    """Break a high-level goal into an ordered list of shell command steps."""
    last_err = None
    for attempt in range(3):
        raw = _call(PIPELINE_SYSTEM, goal)
        try:
            steps = _parse_json(raw)
            return _fix_pipeline_steps(steps)
        except Exception as e:
            last_err = e
    raise ValueError(f"AI returned invalid JSON after 3 attempts: {last_err}")

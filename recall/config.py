import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# App directories
APP_DIR = Path.home() / ".recall"
DB_PATH = APP_DIR / "recall.db"
ENV_PATH = Path(".env")

def ensure_app_dir():
    APP_DIR.mkdir(parents=True, exist_ok=True)

def get_anthropic_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")

def get_openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")

def get_gemini_key() -> str | None:
    return os.getenv("GEMINI_API_KEY")

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

def is_gemini_mode() -> bool:
    """True when user has set a Gemini API key but no local base or OpenAI key."""
    return get_gemini_key() is not None and not is_local_mode() and not is_openai_mode()

def get_api_key() -> str | None:
    """
    Backward-compatible: returns whichever key is relevant for the current mode.
    Used in main.py for the 'missing key' check.
    """
    if is_local_mode():
        return get_local_api_key()
    if is_openai_mode():
        return get_openai_key()
    if is_gemini_mode():
        return get_gemini_key()
    return get_anthropic_key()

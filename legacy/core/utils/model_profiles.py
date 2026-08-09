"""Model profile switching.

Lets you A/B between providers without editing .env. Each profile sets the
three env vars the existing agent_factory already reads:
  AGENTIC_BROWSER_TEXT_MODEL
  AGENTIC_BROWSER_TEXT_API_KEY
  AGENTIC_BROWSER_TEXT_BASE_URL

CLI:   python run_extension.py --model openai
ENV:   MODEL_PROFILE=openai python run_extension.py
"""

import os
from typing import Optional

# ---- profile registry ---------------------------------------------------
# Each profile is (model_name, api_key_env, base_url). Resolved at apply time
# so .env edits land without code changes.
_PROFILES: dict[str, dict] = {
    # OpenAI (generic, honors OPENAI_MODEL env override).
    "openai":   {"model_env": "OPENAI_MODEL",   "key_env": "OPENAI_API_KEY",   "base_url": "https://api.openai.com/v1",
                 "default_model": "gpt-4.1"},
    # Specific-model aliases pin the model regardless of env (so picking
    # `--model gpt-4o` always means gpt-4o, not whatever OPENAI_MODEL says).
    "gpt-4.1":  {"model_env": None, "key_env": "OPENAI_API_KEY",   "base_url": "https://api.openai.com/v1",
                 "default_model": "gpt-4.1"},
    "gpt-4o":   {"model_env": None, "key_env": "OPENAI_API_KEY",   "base_url": "https://api.openai.com/v1",
                 "default_model": "gpt-4o"},
    "gpt-4o-mini": {"model_env": None, "key_env": "OPENAI_API_KEY","base_url": "https://api.openai.com/v1",
                 "default_model": "gpt-4o-mini"},
    # Anthropic native (the existing get_text_model_instance path auto-detects
    # 'claude' prefix and switches client, so this is just convenient naming).
    "claude":   {"model_env": "ANTHROPIC_MODEL","key_env": "ANTHROPIC_API_KEY","base_url": "https://api.anthropic.com/v1",
                 "default_model": "claude-3-5-sonnet-20241022"},
}

AVAILABLE = sorted(_PROFILES.keys())


def apply_profile(name: Optional[str]) -> Optional[str]:
    """Apply a profile by overwriting AGENTIC_BROWSER_TEXT_* env vars.

    Returns the profile name actually used, or None if no profile was given
    (in which case the existing AGENTIC_BROWSER_TEXT_* env vars are honored
    as-is — backwards compatible).
    """
    if not name:
        return None
    name = name.lower().strip()
    if name not in _PROFILES:
        raise ValueError(f"Unknown profile {name!r}. Available: {AVAILABLE}")
    p = _PROFILES[name]
    # If model_env is set on the profile, honor that env override (e.g. the
    # generic 'openai' profile reads OPENAI_MODEL). If not, the profile pins
    # a specific model regardless of env.
    model = (p.get("model_env") and os.getenv(p["model_env"])) or p["default_model"]
    key   = os.getenv(p["key_env"])
    if not key:
        raise RuntimeError(
            f"Profile {name!r} needs env var {p['key_env']} set (your API key for that provider)."
        )
    os.environ["AGENTIC_BROWSER_TEXT_MODEL"]    = model
    os.environ["AGENTIC_BROWSER_TEXT_API_KEY"]  = key
    os.environ["AGENTIC_BROWSER_TEXT_BASE_URL"] = p["base_url"]
    return name


def describe_active() -> str:
    """One-line summary of the currently-active model wiring."""
    m = os.getenv("AGENTIC_BROWSER_TEXT_MODEL", "(unset)")
    b = os.getenv("AGENTIC_BROWSER_TEXT_BASE_URL", "(unset)")
    return f"model={m}  base={b}"

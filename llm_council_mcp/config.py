"""Configuration for the LLM Council MCP server.

All values can be overridden via environment variables, which is how the MCP
client (Claude Code) will pass them in through the server's `env` block.
"""

import os

# --- OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = os.getenv(
    "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
)

# Optional attribution headers OpenRouter recommends.
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "https://github.com/")
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "llm-council-mcp")


def _split_env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Council roster ---
# Override with COUNCIL_MODELS="openai/gpt-5.1,anthropic/claude-sonnet-4.5,..."
COUNCIL_MODELS = _split_env_list(
    "COUNCIL_MODELS",
    [
        "openai/gpt-5.1",
        "google/gemini-3-pro-preview",
        "anthropic/claude-sonnet-4.5",
        "x-ai/grok-4",
    ],
)

# The model that synthesizes the final answer.
CHAIRMAN_MODEL = os.getenv("CHAIRMAN_MODEL", "google/gemini-3-pro-preview")

# --- Request behavior ---
REQUEST_TIMEOUT = float(os.getenv("LLM_COUNCIL_TIMEOUT", "120"))
MAX_RETRIES = int(os.getenv("LLM_COUNCIL_MAX_RETRIES", "2"))

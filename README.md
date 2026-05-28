# LLM Council MCP

A hybrid of [Andrej Karpathy's LLM Council](https://github.com/karpathy/llm-council)
and the Model Context Protocol: real **multi-model** deliberation over OpenRouter,
exposed as an **MCP server** you call from inside Claude Code (or any MCP client).

Unlike the single-model "5 sub-agents" Claude Code skill, this runs genuine
cross-model deliberation — GPT, Claude, Gemini, Grok, etc. all answer, peer-review
each other's *anonymized* responses, and a chairman model synthesizes the verdict.

## The pipeline

1. **Stage 1 — First opinions.** Every council model answers your question independently (parallel).
2. **Stage 2 — Anonymized peer review.** Each model sees the others' responses as "Response A/B/C…" (identities hidden so no model favors its own family) and ranks them.
3. **Stage 3 — Chairman synthesis.** A designated chairman model reads all responses + rankings and produces the final answer.

You also get a **peer leaderboard** (average rank per model) computed from the parsed rankings.

## Tools exposed

| Tool | What it does |
|------|--------------|
| `council_deliberate` | Full 3-stage council on a hard question. Returns a markdown report (or `format="json"`). Optional `models` / `chairman_model` overrides. |
| `council_jury` | Fast go/no-go: each model gives `VERDICT: YES/NO`, returns a vote tally + chairman synthesis. |
| `council_config` | Shows the active roster, chairman, and whether the API key is set. |

## Prerequisites

- Python ≥ 3.10
- An [OpenRouter](https://openrouter.ai/) API key with credits (each council run hits N models + 1 chairman, so ≈ N+1× the tokens of a single query).

## Install

```bash
cd llm-council-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

This installs the `llm-council-mcp` console script (entry point `llm_council_mcp.server:main`).

## Register with Claude Code

Claude Code reads MCP servers from `~/.claude.json` (or a project `.mcp.json`). Easiest way:

```bash
claude mcp add llm-council \
  --env OPENROUTER_API_KEY=sk-or-v1-... \
  -- /ABSOLUTE/PATH/llm-council-mcp/.venv/bin/llm-council-mcp
```

Or add it manually to `~/.claude.json`:

```json
{
  "mcpServers": {
    "llm-council": {
      "command": "/ABSOLUTE/PATH/llm-council-mcp/.venv/bin/llm-council-mcp",
      "env": {
        "OPENROUTER_API_KEY": "sk-or-v1-...",
        "COUNCIL_MODELS": "openai/gpt-5.1,google/gemini-3-pro-preview,anthropic/claude-sonnet-4.5,x-ai/grok-4",
        "CHAIRMAN_MODEL": "google/gemini-3-pro-preview"
      }
    }
  }
}
```

Restart Claude Code. Then just ask it to use the tools, e.g.:

> Use the llm-council `council_deliberate` tool: should Remy v1 stay a single-agent reasoning loop or move to a multi-agent orchestrator before my Anthropic Fellowship demo?

## Configuration (env vars)

| Var | Default | Notes |
|-----|---------|-------|
| `OPENROUTER_API_KEY` | — | **Required.** |
| `COUNCIL_MODELS` | `openai/gpt-5.1,google/gemini-3-pro-preview,anthropic/claude-sonnet-4.5,x-ai/grok-4` | Comma-separated OpenRouter model IDs. |
| `CHAIRMAN_MODEL` | `google/gemini-3-pro-preview` | Synthesizer. |
| `LLM_COUNCIL_TIMEOUT` | `120` | Per-request seconds. |
| `LLM_COUNCIL_MAX_RETRIES` | `2` | Retries on 408/429/5xx. |

## Run the server directly (debug)

```bash
OPENROUTER_API_KEY=sk-or-v1-... .venv/bin/llm-council-mcp
# speaks MCP over stdio — Ctrl-C to exit
```

## Test offline (no API cost)

```bash
PYTHONPATH=. .venv/bin/python tests/test_pipeline_mock.py   # mocks OpenRouter
PYTHONPATH=. .venv/bin/python tests/test_mcp_boot.py        # boots server, lists tools
```

## Credits

3-stage methodology and prompts adapted from [karpathy/llm-council](https://github.com/karpathy/llm-council) (MIT). MCP wrapper, retries, jury mode, and leaderboard added here.

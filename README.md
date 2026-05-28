# LLM Council MCP

[![CI](https://github.com/JeremyGracey-AI/llm-council-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/JeremyGracey-AI/llm-council-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

## Usage example

<!-- Drop a screen recording here once you have one:
     ![LLM Council demo](docs/demo.gif) -->

A typical `council_deliberate` call returns a markdown report shaped like this:

```text
# LLM Council Verdict

**Question:** Should I cache embeddings in SQLite or Redis for a single-box demo?

## Final Answer (Chairman: google/gemini-3-pro-preview)
For a single-box demo, SQLite is the better default: zero extra services to run,
persistence for free, and ample throughput at demo scale. Reach for Redis only if
you later need sub-millisecond reads under concurrency or cross-process sharing.

## Peer Leaderboard (lower avg rank = better)
- **anthropic/claude-sonnet-4.5** — avg rank 1.33 (ranked by 4)
- **openai/gpt-5.1** — avg rank 1.67 (ranked by 4)
- **google/gemini-3-pro-preview** — avg rank 3.0 (ranked by 4)
- **x-ai/grok-4** — avg rank 4.0 (ranked by 4)

## Stage 1 — Individual Responses
### openai/gpt-5.1
...
## Stage 2 — Peer Reviews & Rankings
### anthropic/claude-sonnet-4.5
...
FINAL RANKING:
1. Response B
2. Response A
...
```

Fast go/no-go decisions use `council_jury` instead — each model returns
`VERDICT: YES/NO` and you get a tally plus the chairman's synthesis:

```text
# Council Jury Verdict

**Question:** Should we ship the v1 demo this Friday?

**Tally:** 3 YES / 1 NO
- openai/gpt-5.1: YES
- google/gemini-3-pro-preview: YES
- anthropic/claude-sonnet-4.5: YES
- x-ai/grok-4: NO

## Chairman Synthesis (google/gemini-3-pro-preview)
Ship it — three of four advisors agree the core path is solid. The lone NO flags
thin error handling on the upload route; gate the Friday release on that one fix.
```

Inspect the active roster any time with `council_config` (no API call, no cost).

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

## Contributing

Contributions are welcome. The project is small and the test suite runs offline
(no API key or credits needed), so the loop is fast:

```bash
git clone https://github.com/JeremyGracey-AI/llm-council-mcp.git
cd llm-council-mcp
python3 -m venv .venv && .venv/bin/pip install -e .
PYTHONPATH=. .venv/bin/python tests/test_pipeline_mock.py
PYTHONPATH=. .venv/bin/python tests/test_mcp_boot.py
```

Guidelines:

- Open an issue first for anything beyond a small fix, so we can align on approach.
- Branch off `main`, keep PRs focused, and make sure both tests pass — CI runs them on Python 3.10–3.12.
- Add or update a test for any behavior change. Keep tests **offline** by mocking OpenRouter (see `tests/test_pipeline_mock.py`); never commit real API keys or hit the live API in tests.
- Match the existing style: type hints, docstrings on public functions, and structured `{ok, error}` results rather than raised exceptions in the request path.
- New tools belong in `server.py`; core pipeline logic in `council.py`; provider/transport details in `openrouter.py`.

By contributing you agree your contributions are licensed under the MIT License.

## Credits

3-stage methodology and prompts adapted from [karpathy/llm-council](https://github.com/karpathy/llm-council) (MIT). MCP wrapper, retries, jury mode, and leaderboard added here.

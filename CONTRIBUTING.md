# Contributing to LLM Council MCP

Thanks for your interest in contributing. The project is small and its test
suite runs **fully offline** (no OpenRouter key or credits required), so the
feedback loop is fast.

## Dev setup

```bash
git clone https://github.com/JeremyGracey-AI/llm-council-mcp.git
cd llm-council-mcp
python3 -m venv .venv && .venv/bin/pip install -e .
```

## Run the tests

```bash
PYTHONPATH=. .venv/bin/python tests/test_pipeline_mock.py   # full pipeline, OpenRouter mocked
PYTHONPATH=. .venv/bin/python tests/test_mcp_boot.py        # boots the server, lists tools
```

CI runs both on Python 3.10, 3.11, and 3.12 for every push and pull request to `main`.

## Guidelines

- **Open an issue first** for anything beyond a small fix, so we can align on approach.
- Branch off `main`, keep pull requests focused, and ensure both tests pass.
- **Add or update a test** for any behavior change. Keep tests offline by mocking
  OpenRouter (see `tests/test_pipeline_mock.py`). Never commit real API keys or
  hit the live API in tests.
- Match the existing style: type hints, docstrings on public functions, and
  structured `{ok, error}` results rather than raised exceptions in the request path.
- Where things live:
  - new MCP tools → `llm_council_mcp/server.py`
  - core deliberation pipeline → `llm_council_mcp/council.py`
  - provider/transport details → `llm_council_mcp/openrouter.py`
  - configuration → `llm_council_mcp/config.py`

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).

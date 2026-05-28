"""Offline test: mock OpenRouter so we exercise the full pipeline with zero API cost."""

import asyncio
from unittest.mock import patch

from llm_council_mcp import council


# Fake per-model behavior. Stage 1 returns an answer; Stage 2 returns a ranking.
async def fake_query_model(model, messages, timeout=None, max_retries=None):
    content = messages[0]["content"]
    if "Chairman" in content:  # stage 3 (check first: chairman prompt also embeds ranking text)
        return {"ok": True, "model": model, "content": "SYNTHESIZED FINAL ANSWER.", "reasoning": None}
    if "FINAL RANKING:" in content:  # this is a ranking prompt (stage 2)
        return {
            "ok": True,
            "model": model,
            "content": "Eval text...\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C",
            "reasoning": None,
        }
    return {"ok": True, "model": model, "content": f"Answer from {model}.", "reasoning": None}


async def fake_parallel(models, messages):
    return [await fake_query_model(m, messages) for m in models]


def test_full_council():
    models = ["openai/gpt-5.1", "anthropic/claude-sonnet-4.5", "x-ai/grok-4"]
    with patch.object(council, "query_model", fake_query_model), patch.object(
        council, "query_models_parallel", fake_parallel
    ):
        result = asyncio.run(
            council.run_full_council("Should I ship X?", models=models, chairman_model="google/gemini-3-pro-preview")
        )

    assert "error" not in result, result
    assert len(result["stage1_responses"]) == 3
    assert len(result["stage2_rankings"]) == 3
    assert result["final_answer"]["response"] == "SYNTHESIZED FINAL ANSWER."
    # Response A maps to first model and is ranked #1 by everyone -> avg rank 1.0, top of leaderboard.
    assert result["leaderboard"][0]["model"] == "openai/gpt-5.1"
    assert result["leaderboard"][0]["average_rank"] == 1.0
    print("PASS: full council pipeline")
    print("Leaderboard:", result["leaderboard"])


def test_ranking_parser():
    txt = "blah\nFINAL RANKING:\n1. Response C\n2. Response A\n3. Response B"
    assert council._parse_ranking(txt) == ["Response C", "Response A", "Response B"]
    print("PASS: ranking parser")


def test_streaming_events():
    models = ["openai/gpt-5.1", "anthropic/claude-sonnet-4.5"]

    async def collect():
        events = []
        with patch.object(council, "query_model", fake_query_model), patch.object(
            council, "query_models_parallel", fake_parallel
        ):
            async for ev in council.run_council_stream("Q?", models=models):
                events.append(ev["event"])
        return events

    events = asyncio.run(collect())
    assert events == [
        "start",
        "stage1_complete",
        "stage2_complete",
        "stage3_complete",
        "done",
    ], events
    print("PASS: streaming events in order")


def test_html_report():
    from llm_council_mcp.report import render_html

    models = ["openai/gpt-5.1", "anthropic/claude-sonnet-4.5"]
    with patch.object(council, "query_model", fake_query_model), patch.object(
        council, "query_models_parallel", fake_parallel
    ):
        result = asyncio.run(council.run_full_council("Q?", models=models))
    html = render_html(result)
    assert html.startswith("<!doctype html>")
    assert "LLM Council Verdict" in html
    assert "SYNTHESIZED FINAL ANSWER." in html
    assert "Peer Leaderboard" in html
    print("PASS: HTML report renders")


if __name__ == "__main__":
    test_ranking_parser()
    test_full_council()
    test_streaming_events()
    test_html_report()
    print("\nALL TESTS PASSED")

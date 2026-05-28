"""MCP server exposing the LLM Council as callable tools (stdio transport).

Tools:
  - council_deliberate: run the full 3-stage multi-model council on a question.
  - council_jury:       run a fast go/no-go binary verdict across the council.
  - council_config:     inspect the current roster, chairman, and key status.

Designed to be launched by an MCP client (e.g. Claude Code) via stdio.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import config
from .council import run_full_council

mcp = FastMCP("llm-council")


def _format_report(result: dict[str, Any]) -> str:
    """Render a council result as readable markdown for the calling agent."""
    if result.get("error"):
        lines = [f"# LLM Council — ERROR\n\n{result['error']}"]
        for f in result.get("failures", []):
            lines.append(f"- {f['model']}: {f['error']}")
        return "\n".join(lines)

    out: list[str] = [f"# LLM Council Verdict\n\n**Question:** {result['query']}\n"]

    final = result["final_answer"]
    out.append(f"## Final Answer (Chairman: {final['model']})\n\n{final['response']}\n")

    out.append("## Peer Leaderboard (lower avg rank = better)\n")
    for row in result.get("leaderboard", []):
        out.append(
            f"- **{row['model']}** — avg rank {row['average_rank']} "
            f"(ranked by {row['rankings_count']})"
        )
    out.append("")

    out.append("## Stage 1 — Individual Responses\n")
    for r in result["stage1_responses"]:
        out.append(f"### {r['model']}\n\n{r['response']}\n")

    out.append("## Stage 2 — Peer Reviews & Rankings\n")
    for r in result["stage2_rankings"]:
        out.append(f"### {r['model']}\n\n{r['ranking_text']}\n")

    if result.get("failures"):
        out.append("## Failures\n")
        for f in result["failures"]:
            out.append(f"- {f['model']}: {f['error']}")

    return "\n".join(out)


@mcp.tool()
async def council_deliberate(
    question: str,
    models: list[str] | None = None,
    chairman_model: str | None = None,
    format: str = "markdown",
) -> str:
    """Run the full 3-stage LLM Council on a hard question.

    Multiple frontier models answer independently, peer-review each other's
    anonymized responses, and a chairman synthesizes a final answer.

    Args:
        question: The question or decision to deliberate.
        models: Optional override list of OpenRouter model IDs for the council.
        chairman_model: Optional override for the synthesizing model.
        format: "markdown" (default, human-readable report) or "json" (raw data).
    """
    result = await run_full_council(question, models=models, chairman_model=chairman_model)
    if format == "json":
        return json.dumps(result, indent=2)
    return _format_report(result)


@mcp.tool()
async def council_jury(
    question: str,
    models: list[str] | None = None,
    chairman_model: str | None = None,
) -> str:
    """Run a fast go/no-go binary verdict across the council.

    Reframes the question to demand a clear YES or NO from each model, then the
    chairman returns a single verdict with the vote tally and the deciding reason.

    Args:
        question: A decision phrased so YES/NO is meaningful (e.g. "Should we ship X now?").
        models: Optional override list of OpenRouter model IDs.
        chairman_model: Optional override for the synthesizing model.
    """
    framed = (
        f"{question}\n\n"
        "Answer with a clear verdict. Begin your response with exactly 'VERDICT: YES' "
        "or 'VERDICT: NO', then give your reasoning in 2-4 sentences."
    )
    result = await run_full_council(framed, models=models, chairman_model=chairman_model)
    if result.get("error"):
        return f"# Council Jury — ERROR\n\n{result['error']}"

    # Tally YES/NO from stage 1.
    yes = no = 0
    votes = []
    for r in result["stage1_responses"]:
        text = r["response"].upper()
        if "VERDICT: YES" in text:
            yes += 1
            votes.append(f"- {r['model']}: YES")
        elif "VERDICT: NO" in text:
            no += 1
            votes.append(f"- {r['model']}: NO")
        else:
            votes.append(f"- {r['model']}: (unclear)")

    final = result["final_answer"]
    return (
        f"# Council Jury Verdict\n\n**Question:** {question}\n\n"
        f"**Tally:** {yes} YES / {no} NO\n\n"
        + "\n".join(votes)
        + f"\n\n## Chairman Synthesis ({final['model']})\n\n{final['response']}"
    )


@mcp.tool()
def council_config() -> str:
    """Show the current council roster, chairman model, and API-key status."""
    return json.dumps(
        {
            "council_models": config.COUNCIL_MODELS,
            "chairman_model": config.CHAIRMAN_MODEL,
            "openrouter_api_key_set": bool(config.OPENROUTER_API_KEY),
            "request_timeout_s": config.REQUEST_TIMEOUT,
            "max_retries": config.MAX_RETRIES,
        },
        indent=2,
    )


def main() -> None:
    """Entry point — run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()

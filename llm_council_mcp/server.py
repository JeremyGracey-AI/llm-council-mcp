"""MCP server exposing the LLM Council as callable tools (stdio transport).

Tools:
  - council_deliberate:           run the full 3-stage council on a question.
  - council_deliberate_streaming: same, with live per-stage progress events.
  - council_jury:                 run a fast go/no-go binary verdict.
  - council_config:               inspect the roster, chairman, and key status.

Resources:
  - council://roster:      the active roster and request settings, as JSON.
  - council://methodology: how the 3-stage deliberation protocol works.

Prompts:
  - deliberate:      frame a hard decision for full council deliberation.
  - jury:            frame a go/no-go decision for a fast binary vote.
  - compare_options: ask the council to compare named options against criteria.

Designed to be launched by an MCP client (e.g. Claude Code) via stdio.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from . import config
from .council import run_council_stream, run_full_council
from .report import render_html

mcp = FastMCP("llm-council")


def _write_html_report(result: dict[str, Any], html_path: str | None) -> str | None:
    """Write an HTML report to html_path (or an auto-named file). Returns the path."""
    if html_path is None:
        return None
    path = html_path
    if path == "" or path.lower() == "auto":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(os.getcwd(), f"council-report-{stamp}.html")
    path = os.path.abspath(os.path.expanduser(path))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(result))
    return path


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
    html_path: str | None = None,
) -> str:
    """Run the full 3-stage LLM Council on a hard question.

    Multiple frontier models answer independently, peer-review each other's
    anonymized responses, and a chairman synthesizes a final answer.

    Args:
        question: The question or decision to deliberate.
        models: Optional override list of OpenRouter model IDs for the council.
        chairman_model: Optional override for the synthesizing model.
        format: "markdown" (default, human-readable report) or "json" (raw data).
        html_path: If set, also write a self-contained HTML report to this path.
            Use "auto" to auto-name it council-report-<timestamp>.html in the cwd.
    """
    result = await run_full_council(question, models=models, chairman_model=chairman_model)
    written = _write_html_report(result, html_path)
    out = json.dumps(result, indent=2) if format == "json" else _format_report(result)
    if written:
        out += f"\n\n_HTML report written to: {written}_"
    return out


@mcp.tool()
async def council_deliberate_streaming(
    question: str,
    ctx: Context,
    models: list[str] | None = None,
    chairman_model: str | None = None,
    html_path: str | None = None,
) -> str:
    """Run the council with live per-stage progress updates.

    Identical to council_deliberate but emits MCP progress + log events as each
    stage completes (dispatch -> peer review -> chairman), so the client can show
    a live status. Returns the final markdown report when done.

    Args:
        question: The question or decision to deliberate.
        ctx: MCP context (injected automatically) used for progress reporting.
        models: Optional override list of OpenRouter model IDs for the council.
        chairman_model: Optional override for the synthesizing model.
        html_path: If set, also write a self-contained HTML report ("auto" to auto-name).
    """
    stage_progress = {
        "start": (0.05, "Council convened; dispatching question to all members"),
        "stage1_complete": (0.40, "Stage 1 complete: individual responses collected"),
        "stage2_complete": (0.70, "Stage 2 complete: anonymized peer review & rankings"),
        "stage3_complete": (0.95, "Stage 3 complete: chairman synthesizing verdict"),
        "done": (1.0, "Done"),
    }
    result: dict[str, Any] = {}
    async for ev in run_council_stream(question, models=models, chairman_model=chairman_model):
        name = ev["event"]
        if name == "error":
            await ctx.info(f"Council error: {ev['error']}")
            return f"# LLM Council — ERROR\n\n{ev['error']}"
        if name in stage_progress:
            pct, msg = stage_progress[name]
            await ctx.report_progress(pct, 1.0, msg)
            await ctx.info(msg)
        if name == "done":
            result = ev["result"]

    written = _write_html_report(result, html_path)
    out = _format_report(result)
    if written:
        out += f"\n\n_HTML report written to: {written}_"
    return out


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


# --------------------------------------------------------------------------
# Resources — read-only context the client can attach to a conversation.
# --------------------------------------------------------------------------


@mcp.resource("council://roster")
def roster_resource() -> str:
    """The active council roster, chairman, and request settings, as JSON."""
    return json.dumps(
        {
            "council_models": config.COUNCIL_MODELS,
            "chairman_model": config.CHAIRMAN_MODEL,
            "openrouter_api_key_set": bool(config.OPENROUTER_API_KEY),
            "request_timeout_s": config.REQUEST_TIMEOUT,
            "max_retries": config.MAX_RETRIES,
            "council_size": len(config.COUNCIL_MODELS),
        },
        indent=2,
    )


@mcp.resource("council://methodology")
def methodology_resource() -> str:
    """How the council reaches a verdict — the 3-stage deliberation protocol."""
    return (
        "# LLM Council methodology\n\n"
        "## Stage 1 — First opinions\n"
        "Every council model answers the question independently and in parallel. "
        "No model sees another model's answer at this stage, so the responses are "
        "uncorrelated.\n\n"
        "## Stage 2 — Anonymized peer review\n"
        "Each model is shown the other responses relabeled as 'Response A/B/C...'. "
        "Identities are stripped so no model can favor its own family, and each "
        "model ranks the anonymized set.\n\n"
        "## Stage 3 — Chairman synthesis\n"
        "A designated chairman model reads every response plus every ranking and "
        "writes the final answer.\n\n"
        "## Peer leaderboard\n"
        "Average rank per model is computed from the Stage 2 rankings. Lower is "
        "better. It measures how the council rated each member on this question "
        "only — it is not a general capability benchmark.\n\n"
        "## Cost\n"
        "One run costs roughly N+1 times a single-model query, where N is the "
        "council size.\n"
    )


# --------------------------------------------------------------------------
# Prompts — reusable templates the user can invoke from the client.
# --------------------------------------------------------------------------


@mcp.prompt()
def deliberate(question: str, context: str = "") -> str:
    """Frame a hard decision for full 3-stage council deliberation.

    Args:
        question: The decision or question to put to the council.
        context: Optional background — constraints, prior attempts, deadlines.
    """
    parts = [
        "Put the following question to the LLM Council using the "
        "`council_deliberate` tool. Report the chairman's verdict first, then "
        "note any point where council members meaningfully disagreed.",
        f"\nQuestion: {question}",
    ]
    if context.strip():
        parts.append(f"\nContext to include: {context}")
    return "\n".join(parts)


@mcp.prompt()
def jury(question: str, stakes: str = "") -> str:
    """Frame a go/no-go decision for a fast binary council vote.

    Args:
        question: A decision phrased so YES/NO is meaningful.
        stakes: Optional note on what a wrong call costs.
    """
    parts = [
        "Put the following go/no-go decision to the LLM Council using the "
        "`council_jury` tool. Lead with the tally, then the chairman's reasoning. "
        "If the vote is not unanimous, say explicitly what the dissenters "
        "were worried about.",
        f"\nDecision: {question}",
    ]
    if stakes.strip():
        parts.append(f"\nStakes: {stakes}")
    return "\n".join(parts)


@mcp.prompt()
def compare_options(options: str, criteria: str = "") -> str:
    """Ask the council to compare several named options against criteria.

    Args:
        options: The options to compare, e.g. "Postgres, DynamoDB, SQLite".
        criteria: Optional criteria that matter, e.g. "write throughput, ops burden".
    """
    crit = criteria.strip() or "correctness, operational burden, and cost"
    return (
        "Use the `council_deliberate` tool to compare these options and "
        "recommend one.\n\n"
        f"Options: {options}\n"
        f"Judge them on: {crit}\n\n"
        "In your summary, state the recommendation, the single strongest "
        "argument against it, and what would change the answer."
    )


def main() -> None:
    """Entry point — run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()

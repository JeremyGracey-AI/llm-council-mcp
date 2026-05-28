"""3-stage LLM Council orchestration.

Stage 1: every council model answers the query independently (parallel).
Stage 2: every council model peer-reviews the anonymized responses and ranks them.
Stage 3: the chairman model synthesizes a final answer from responses + rankings.

Adapted from karpathy/llm-council. All functions return JSON-serializable
structures so the MCP layer can hand them straight to the client.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from . import config
from .openrouter import query_model, query_models_parallel


# --------------------------------------------------------------------------- #
# Stage 1 — first opinions
# --------------------------------------------------------------------------- #
async def stage1_collect_responses(
    user_query: str, models: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (successful_responses, failures)."""
    messages = [{"role": "user", "content": user_query}]
    results = await query_models_parallel(models, messages)

    responses, failures = [], []
    for r in results:
        if r.get("ok"):
            responses.append({"model": r["model"], "response": r["content"]})
        else:
            failures.append({"model": r["model"], "error": r.get("error", "unknown")})
    return responses, failures


# --------------------------------------------------------------------------- #
# Stage 2 — anonymized peer review + ranking
# --------------------------------------------------------------------------- #
RANKING_PROMPT = """You are evaluating different responses to the following question:

Question: {query}

Here are the responses from different models (anonymized):

{responses}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Now provide your evaluation and ranking:"""


def _parse_ranking(text: str) -> list[str]:
    """Extract the ordered list of 'Response X' labels from a ranking response."""
    section = text
    if "FINAL RANKING:" in text:
        section = text.split("FINAL RANKING:", 1)[1]
        numbered = re.findall(r"\d+\.\s*Response [A-Z]", section)
        if numbered:
            return [re.search(r"Response [A-Z]", m).group() for m in numbered]
    return re.findall(r"Response [A-Z]", section)


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    models: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Returns (rankings, label_to_model)."""
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...
    label_to_model = {
        f"Response {label}": res["model"]
        for label, res in zip(labels, stage1_results)
    }
    responses_text = "\n\n".join(
        f"Response {label}:\n{res['response']}"
        for label, res in zip(labels, stage1_results)
    )
    prompt = RANKING_PROMPT.format(query=user_query, responses=responses_text)
    messages = [{"role": "user", "content": prompt}]

    results = await query_models_parallel(models, messages)
    rankings = []
    for r in results:
        if r.get("ok"):
            full = r["content"]
            rankings.append(
                {
                    "model": r["model"],
                    "ranking_text": full,
                    "parsed_ranking": _parse_ranking(full),
                }
            )
    return rankings, label_to_model


def aggregate_rankings(
    rankings: list[dict[str, Any]], label_to_model: dict[str, str]
) -> list[dict[str, Any]]:
    """Average each model's rank position across all reviewers (lower = better)."""
    positions: dict[str, list[int]] = defaultdict(list)
    for r in rankings:
        for pos, label in enumerate(r["parsed_ranking"], start=1):
            if label in label_to_model:
                positions[label_to_model[label]].append(pos)

    out = [
        {
            "model": model,
            "average_rank": round(sum(p) / len(p), 2),
            "rankings_count": len(p),
        }
        for model, p in positions.items()
        if p
    ]
    out.sort(key=lambda x: x["average_rank"])
    return out


# --------------------------------------------------------------------------- #
# Stage 3 — chairman synthesis
# --------------------------------------------------------------------------- #
CHAIRMAN_PROMPT = """You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {query}

STAGE 1 - Individual Responses:
{stage1}

STAGE 2 - Peer Rankings:
{stage2}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""


async def stage3_synthesize(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    chairman_model: str,
) -> dict[str, Any]:
    stage1_text = "\n\n".join(
        f"Model: {r['model']}\nResponse: {r['response']}" for r in stage1_results
    )
    stage2_text = "\n\n".join(
        f"Model: {r['model']}\nRanking: {r['ranking_text']}" for r in stage2_results
    )
    prompt = CHAIRMAN_PROMPT.format(
        query=user_query, stage1=stage1_text, stage2=stage2_text
    )
    r = await query_model(chairman_model, [{"role": "user", "content": prompt}])
    if not r.get("ok"):
        return {
            "model": chairman_model,
            "response": f"Error: chairman synthesis failed ({r.get('error')}).",
            "ok": False,
        }
    return {"model": chairman_model, "response": r["content"], "ok": True}


# --------------------------------------------------------------------------- #
# Full pipeline
# --------------------------------------------------------------------------- #
async def run_full_council(
    user_query: str,
    models: list[str] | None = None,
    chairman_model: str | None = None,
) -> dict[str, Any]:
    models = models or config.COUNCIL_MODELS
    chairman_model = chairman_model or config.CHAIRMAN_MODEL

    stage1, failures = await stage1_collect_responses(user_query, models)
    if not stage1:
        return {
            "query": user_query,
            "error": "All council models failed to respond.",
            "failures": failures,
        }

    stage2, label_to_model = await stage2_collect_rankings(user_query, stage1, models)
    leaderboard = aggregate_rankings(stage2, label_to_model)
    stage3 = await stage3_synthesize(user_query, stage1, stage2, chairman_model)

    return {
        "query": user_query,
        "council_models": models,
        "chairman_model": chairman_model,
        "stage1_responses": stage1,
        "stage2_rankings": stage2,
        "leaderboard": leaderboard,
        "final_answer": stage3,
        "failures": failures,
        "label_to_model": label_to_model,
    }

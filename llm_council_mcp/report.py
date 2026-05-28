"""Render a council result as a self-contained HTML report.

Produces a single static .html file (no external assets) so it can be opened
directly in a browser or shared as-is.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6; margin: 0; padding: 2rem; max-width: 880px; margin-inline: auto;
  background: #0d1117; color: #e6edf3;
}
h1 { font-size: 1.7rem; border-bottom: 1px solid #30363d; padding-bottom: .5rem; }
h2 { font-size: 1.25rem; margin-top: 2rem; color: #58a6ff; }
h3 { font-size: 1.05rem; margin-top: 1.25rem; color: #d2a8ff; }
.meta { color: #8b949e; font-size: .85rem; }
.final {
  background: #161b22; border: 1px solid #30363d; border-left: 4px solid #2ea043;
  border-radius: 8px; padding: 1rem 1.25rem; white-space: pre-wrap;
}
table { border-collapse: collapse; width: 100%; margin-top: .5rem; }
th, td { border: 1px solid #30363d; padding: .5rem .75rem; text-align: left; }
th { background: #161b22; }
tr:nth-child(even) td { background: #0f141a; }
.card {
  background: #161b22; border: 1px solid #30363d; border-radius: 8px;
  padding: 1rem 1.25rem; margin: .75rem 0; white-space: pre-wrap;
}
.model { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #79c0ff; }
.fail { color: #f85149; }
details summary { cursor: pointer; color: #58a6ff; margin: .5rem 0; }
"""


def _esc(text: str) -> str:
    return html.escape(text or "")


def render_html(result: dict[str, Any]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if result.get("error"):
        body = f"<h1>LLM Council \u2014 Error</h1><p class='fail'>{_esc(result['error'])}</p>"
        return _wrap(body, ts)

    parts: list[str] = []
    parts.append("<h1>LLM Council Verdict</h1>")
    parts.append(f"<p class='meta'>Generated {ts}</p>")
    parts.append(f"<p><strong>Question:</strong> {_esc(result['query'])}</p>")

    final = result["final_answer"]
    parts.append(f"<h2>Final Answer</h2>")
    parts.append(
        f"<p class='meta'>Chairman: <span class='model'>{_esc(final['model'])}</span></p>"
    )
    parts.append(f"<div class='final'>{_esc(final['response'])}</div>")

    parts.append("<h2>Peer Leaderboard</h2>")
    parts.append("<p class='meta'>Lower average rank = better.</p>")
    parts.append("<table><tr><th>#</th><th>Model</th><th>Avg rank</th><th>Reviews</th></tr>")
    for i, row in enumerate(result.get("leaderboard", []), start=1):
        parts.append(
            f"<tr><td>{i}</td><td class='model'>{_esc(row['model'])}</td>"
            f"<td>{row['average_rank']}</td><td>{row['rankings_count']}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Stage 1 \u2014 Individual Responses</h2>")
    for r in result["stage1_responses"]:
        parts.append(f"<h3 class='model'>{_esc(r['model'])}</h3>")
        parts.append(f"<div class='card'>{_esc(r['response'])}</div>")

    parts.append("<h2>Stage 2 \u2014 Peer Reviews &amp; Rankings</h2>")
    for r in result["stage2_rankings"]:
        parts.append(
            f"<details><summary>{_esc(r['model'])}</summary>"
            f"<div class='card'>{_esc(r['ranking_text'])}</div></details>"
        )

    if result.get("failures"):
        parts.append("<h2>Failures</h2><ul>")
        for f in result["failures"]:
            parts.append(f"<li class='fail'>{_esc(f['model'])}: {_esc(f['error'])}</li>")
        parts.append("</ul>")

    return _wrap("\n".join(parts), ts)


def _wrap(body: str, ts: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>LLM Council Report</title>"
        f"<style>{_CSS}</style></head><body>{body}</body></html>"
    )

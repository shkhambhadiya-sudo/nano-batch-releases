"""Analyst (spec §4.6): reads 11matrix growth data and links it to the work done
on each project, so the goal check and the daily brief can say whether finished
work actually moved anything."""
from __future__ import annotations

from .. import memory
from ..connectors import matrix
from ..llm.gateway import gateway
from ..log import activity

AGENT = "analyst"
SYSTEM = "You are the Analyst agent. You explain growth numbers in relation to the work done. Short, factual, no fluff."


def _pct(cur: float, prev: float) -> float | None:
    return None if not prev else round(100 * (cur - prev) / prev, 1)


async def run(run_id: str, covered_since: str | None) -> None:
    with activity(AGENT, "11matrix metrics fetched", run_id) as rec:
        props = await matrix.client().metrics(days=7)
        rec.notes = f"{len(props)} properties"
    projects = {p.get("deeds_project_id"): p for p in memory.list_("projects", limit=100)}
    rows = []
    for p in props:
        proj = projects.get(p.get("deeds_project_id"))
        done = memory.list_("tasks", "project_id=? AND status='done' AND updated_at >= date('now','-14 days')", (proj["id"],), limit=500) if proj else []
        rows.append({
            "project": proj["name"] if proj else p["name"], "project_id": proj["id"] if proj else None,
            "sessions": _pct(p["sessions"], p["sessions_prev"]), "revenue": _pct(p["revenue"], p["revenue_prev"]),
            "ad_spend": _pct(p["ad_spend"], p["ad_spend_prev"]), "clicks": _pct(p["clicks"], p["clicks_prev"]),
            "done_14d": len(done),
        })
        if proj:
            memory.patch("projects", proj["id"], {"matrix_ids": [p["matrix_id"]]})
    flat = [r for r in rows if r["done_14d"] >= 3 and (r["revenue"] or 0) <= 0 and (r["sessions"] or 0) <= 0]
    with activity(AGENT, "growth narrative written", run_id) as rec:
        table = "\n".join(f"| {r['project']} | {r['sessions']} | {r['revenue']} | {r['ad_spend']} | {r['done_14d']} |" for r in rows)
        res = await gateway.complete("large", SYSTEM,
            "TASK: growth_narrative\nIn 5 lines max: which projects are growing, which are spending more for less, and which "
            "finished a lot of work with no movement in numbers.\n\n| project | sessions % | revenue % | ad spend % | tasks done 14d |\n|---|---|---|---|---|\n" + table)
        rec.model, rec.tokens = res.model, res.tokens
    body = "\n".join([
        "# Analyst report (last 7 days vs previous 7)", "", res.text.strip(), "",
        "## Work done but numbers flat", *([f"- {r['project']}: {r['done_14d']} tasks done, revenue {r['revenue']}%, sessions {r['sessions']}%" for r in flat] or ["- none"]),
        "", "## All projects", "| project | sessions % | revenue % | ad spend % | done 14d |", "|---|---|---|---|---|", table,
    ])
    memory.save_report(AGENT, "analyst", body, {"rows": rows, "flat": [r["project"] for r in flat]}, run_id)

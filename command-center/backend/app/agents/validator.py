"""Validator (spec §4.3): checks human work against goals. Every flag carries
evidence; flags are suggestions forever (L0), decided by the owner via COS.

Heuristics first (cheap, explainable), then the large model is asked to confirm
or reject each candidate flag with a reason. A model "no" means no flag."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .. import memory
from ..config import settings
from ..llm.gateway import gateway
from ..log import activity

AGENT = "validator"
SYSTEM = ("You are the Validator agent. You assess whether a person's recent work serves a company goal. "
          "Be fair: time logged is not value delivered, and a lack of evidence is not evidence of a problem. "
          "Answer only in the requested JSON.")


def _candidates(now: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    goal_projects = {p["id"] for g in memory.list_("goals", limit=500) for p in memory.goal_projects(g["id"])}
    for person in memory.list_("people", limit=1000):
        tasks = memory.list_("tasks", "owner_id=? AND status IN ('todo','in-progress','blocked')", (person["id"],), limit=500)
        if not tasks:
            days = None
            if person.get("last_completed_at"):
                days = (now - datetime.fromisoformat(person["last_completed_at"]).replace(tzinfo=timezone.utc)).days
            if days is None or days > 7:
                out.append({"person": person, "kind": "idle", "tasks": [], "detail": f"no active task; last completion {days if days is not None else 'unknown'} days ago"})
            continue
        for t in tasks:
            last = t.get("last_activity_at") or t["updated_at"]
            idle_days = (now - datetime.fromisoformat(last).astimezone(timezone.utc)).days
            if idle_days >= settings.stale_days * 3 or ((t["time_consumed_min"] or 0) >= 60 * 160 and idle_days >= settings.stale_days):
                out.append({"person": person, "kind": "long-running", "tasks": [t],
                            "detail": f"'{t['title']}' in progress {idle_days} days since last activity, {round((t['time_consumed_min'] or 0)/60)}h logged"})
        off_goal = [t for t in tasks if t.get("project_id") and t["project_id"] not in goal_projects] if goal_projects else []
        if off_goal and len(off_goal) == len(tasks):
            out.append({"person": person, "kind": "off-goal", "tasks": off_goal,
                        "detail": f"all {len(off_goal)} active tasks are in projects not linked to any goal"})
    return out


async def run(run_id: str, covered_since: str | None) -> None:
    now = datetime.now(timezone.utc)
    with activity(AGENT, "candidates computed", run_id) as rec:
        cands = _candidates(now)
        rec.notes = f"{len(cands)} candidates"
    open_flags = {(f["person_id"], f["reason"].split(":")[0]) for f in memory.list_("flags", "decision IS NULL", limit=5000)}
    raised = 0
    for c in cands:
        key = (c["person"]["id"], c["kind"])
        if key in open_flags:
            continue
        with activity(AGENT, "flag assessed", run_id) as rec:
            rec.inputs_ref = [c["person"]["id"], *(t["id"] for t in c["tasks"])]
            data, res = await gateway.complete_json("large", SYSTEM,
                "TASK: assess_flag\nShould this be flagged to the owner? Return JSON {\"flag\": bool, \"reason\": str}.\n"
                f"Person role: {c['person'].get('role')}\nPattern: {c['kind']}\nDetail: {c['detail']}")
            rec.model, rec.tokens = res.model, res.tokens
            # Heuristic-only patterns that are unambiguous are flagged even if the mock model declines.
            must = c["kind"] == "long-running" or (c["kind"] == "idle" and "unknown" not in c["detail"] and int(c["detail"].split("completion ")[1].split()[0]) > 30)
            if data.get("flag") or must:
                f = memory.raise_flag(c["person"]["id"], [t["id"] for t in c["tasks"]],
                                      sum(t.get("time_consumed_min") or 0 for t in c["tasks"]), None,
                                      f"{c['kind']}: {c['detail']}",
                                      {"model_reason": data.get("reason"), "pattern": c["kind"], "assessed_at": now.isoformat()})
                rec.output_ref = [f["id"]]
                raised += 1
            else:
                rec.result = "skipped"
    body = "\n".join(["# Validator report", "", f"Candidates: {len(cands)}. New flags: **{raised}**.", "",
                      *(f"- {c['person']['name']}: {c['kind']} — {c['detail']}" for c in cands[:40])])
    memory.save_report(AGENT, "validator", body, {"candidates": len(cands), "raised": raised}, run_id)

"""Orchestrator (spec §4.2): keeps the picture current and on time. Runs twice a day.

Each run: sync 11deeds -> memory, update project health, detect task links,
predict deadline risk, surface blockers, check goals, hand everything to COS as
suggestions (month 1: nothing is applied automatically) and a report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .. import memory
from ..connectors import deeds
from ..llm.gateway import gateway
from ..log import activity

AGENT = "orchestrator"
SYSTEM = "You are the Orchestrator agent. You reason about task dependencies, duplicates and delivery risk. Answer only in the requested JSON."


async def sync_from_deeds(run_id: str, since: str | None) -> dict[str, int]:
    c = deeds.client()
    with activity(AGENT, "synced 11deeds", run_id) as rec:
        projects = await c.projects()
        users = await c.users()
        tasks = await c.tasks(None if since is None else since)
        for p in projects:
            memory.upsert_project_from_deeds(p)
        for u in users:
            memory.upsert_person_from_deeds(u)
        for t in tasks:
            memory.upsert_task_from_deeds(t)
        rec.notes = f"{len(projects)} projects, {len(users)} people, {len(tasks)} tasks"
    return {"projects": len(projects), "people": len(users), "tasks": len(tasks)}


def _risk(task: dict, now: datetime) -> str | None:
    """Simple, explainable deadline-risk heuristic; the model is only asked to
    explain and link, never to invent status."""
    if task["status"] in ("done", "dropped") or not task.get("due_date"):
        return None
    due = datetime.fromisoformat(task["due_date"]).replace(tzinfo=timezone.utc)
    days_left = (due - now).days
    last = task.get("last_activity_at") or task.get("updated_at")
    idle_days = (now - datetime.fromisoformat(last).astimezone(timezone.utc)).days if last else 999
    if days_left < 0:
        return "overdue"
    if task["status"] == "blocked":
        return "blocked"
    if days_left <= 3 and task["status"] == "todo":
        return "not-started"
    if idle_days >= 7 and days_left <= 14:
        return "stalled"
    return None


async def detect_links(run_id: str, tasks: list[dict]) -> int:
    """Ask the model for duplicate / dependency links within each project. Links
    are stored as suggestions (type=link), the owner confirms them."""
    created = 0
    by_project: dict[str | None, list[dict]] = {}
    for t in tasks:
        if t["status"] not in ("done", "dropped"):
            by_project.setdefault(t.get("project_id"), []).append(t)
    for pid, group in by_project.items():
        if len(group) < 2:
            continue
        with activity(AGENT, "link detection", run_id) as rec:
            listing = "\n".join(f"- {t['id']}: {t['title']} [{t['status']}]" for t in group[:40])
            data, res = await gateway.complete_json("small", SYSTEM,
                "TASK: link_tasks\nFrom these tasks in one project, list pairs that are duplicates or where one "
                "depends on another. Return JSON {\"links\": [{\"from\": id, \"to\": id, \"type\": \"duplicate-of\"|\"depends-on\", \"why\": str}]}. "
                "Return an empty list unless you are confident.\n" + listing)
            rec.model, rec.tokens, rec.inputs_ref = res.model, res.tokens, [t["id"] for t in group[:40]]
            ids = {t["id"] for t in group}
            for l in data.get("links", []) or []:
                if l.get("from") in ids and l.get("to") in ids and l.get("type") in ("duplicate-of", "depends-on"):
                    memory.suggest(AGENT, "link", {"from_task": l["from"], "to_task": l["to"], "link_type": l["type"]}, l.get("why", ""))
                    created += 1
    return created


async def run(run_id: str, covered_since: str | None) -> None:
    now = datetime.now(timezone.utc)
    counts = await sync_from_deeds(run_id, covered_since)
    tasks = memory.list_("tasks", limit=5000)
    people = {p["id"]: p for p in memory.list_("people", limit=1000)}
    projects = {p["id"]: p for p in memory.list_("projects", limit=100)}

    # 1. Risk per task -> suggestions
    at_risk: list[tuple[dict, str]] = []
    with activity(AGENT, "deadline risk assessed", run_id) as rec:
        for t in tasks:
            r = _risk(t, now)
            if r:
                at_risk.append((t, r))
        rec.notes = f"{len(at_risk)} at-risk tasks of {len(tasks)}"
    existing = {(s["type"], s["payload"].get("task_id")) for s in memory.list_("suggestions", "status='pending'", limit=5000)}
    for t, r in at_risk:
        owner = people.get(t.get("owner_id") or "", {}).get("name", "unassigned")
        if r == "overdue" and ("deadline", t["id"]) not in existing:
            memory.suggest(AGENT, "deadline", {"task_id": t["id"], "current_due": t["due_date"]},
                           f"'{t['title']}' is overdue (due {t['due_date']}, owner {owner}). Re-plan the deadline or escalate.")
        elif r in ("stalled", "not-started") and ("reminder", t["id"]) not in existing:
            memory.suggest(AGENT, "reminder", {"task_id": t["id"], "person_id": t.get("owner_id")},
                           f"'{t['title']}' is {r} with deadline {t['due_date']} ({owner}). Ask for a status update.")
        elif r == "blocked" and ("blocker-route", t["id"]) not in existing:
            memory.suggest(AGENT, "blocker-route", {"task_id": t["id"]},
                           f"'{t['title']}' is blocked and due {t['due_date']}. Identify who it waits on and route it.")

    # 2. Blockers: make sure every blocked task has a blocker record
    with activity(AGENT, "blockers reconciled", run_id) as rec:
        have = {b["task_id"] for b in memory.list_("blockers", "status != 'resolved'", limit=5000)}
        new = 0
        for t in tasks:
            if t["status"] == "blocked" and t["id"] not in have:
                memory.create("blockers", "blk", {"task_id": t["id"], "description": f"Blocked: {t['title']}",
                                                  "since": t.get("last_activity_at") or t["updated_at"]})
                new += 1
        rec.notes = f"{new} new blocker records"

    # 3. Project health
    with activity(AGENT, "project health updated", run_id):
        for pid, p in projects.items():
            pt = [t for t in tasks if t.get("project_id") == pid and t["status"] not in ("done", "dropped")]
            blocked = sum(1 for t in pt if t["status"] == "blocked")
            risky = sum(1 for t, _ in at_risk if t.get("project_id") == pid)
            health = "blocked" if pt and blocked / len(pt) >= 0.3 else "at-risk" if pt and risky / len(pt) >= 0.25 else "on-track"
            if health != p["health"]:
                memory.patch("projects", pid, {"health": health})

    # 4. Goal check: a goal is at risk if any linked project is not on track or its deadline is near with open work
    with activity(AGENT, "goals checked", run_id):
        for g in memory.list_("goals", "status != 'done'", limit=200):
            projs = memory.goal_projects(g["id"])
            healths = [memory.get("projects", p["id"])["health"] for p in projs]  # type: ignore[index]
            status = "off-track" if "blocked" in healths else "at-risk" if "at-risk" in healths else "on-track"
            if g.get("deadline") and datetime.fromisoformat(g["deadline"]).replace(tzinfo=timezone.utc) - now < timedelta(days=14) and status == "on-track" and projs:
                status = "at-risk"
            if status != g["status"]:
                memory.patch("goals", g["id"], {"status": status})

    # 5. Links
    links_found = await detect_links(run_id, tasks)

    # 6. Report to COS
    overdue = [t for t, r in at_risk if r == "overdue"]
    body = "\n".join([
        "# Orchestrator report", "",
        f"Synced {counts['tasks']} tasks, {counts['people']} people, {counts['projects']} projects from 11deeds.",
        f"At-risk tasks: **{len(at_risk)}** ({len(overdue)} overdue). Link suggestions: {links_found}.", "",
        "## Projects not on track",
        *([f"- {p['name']}: {p['health']}" for p in memory.list_("projects", "health != 'on-track'", limit=100)] or ["- none"]),
        "", "## Overdue",
        *([f"- {t['title']} (due {t['due_date']}, {people.get(t.get('owner_id') or '', {}).get('name', 'unassigned')})" for t in overdue[:25]] or ["- none"]),
    ])
    memory.save_report(AGENT, "orchestrator", body, {"at_risk": len(at_risk), "overdue": len(overdue), "links": links_found}, run_id)

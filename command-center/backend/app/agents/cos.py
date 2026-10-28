"""COS Agent (spec §4.1): the judgment layer over COS Memory.

- Interview mode: classify a raw capture, ask only the follow-ups needed, file it.
- Daily brief: one page for the owner, built from memory + latest agent reports.
- Intake of agent reports is done by the agents calling memory.save_report; COS
  reads them when briefing."""
from __future__ import annotations

from typing import Any

from .. import memory
from ..llm.gateway import gateway
from ..log import activity

AGENT = "cos"

SYSTEM = (
    "You are the Chief of Staff for a company running 18 projects with ~100 people. "
    "You are precise, brief and sceptical. You only ask a question when the answer "
    "changes what should be done. Always answer in the JSON shape requested."
)


async def capture(raw_text: str) -> dict[str, Any]:
    """Owner dumps anything. Returns the idea row, possibly with a pending question."""
    with activity(AGENT, "capture classified") as rec:
        projects = memory.list_("projects", limit=100)
        names = ", ".join(f"{p['name']} (id {p['id']})" for p in projects) or "none yet"
        prompt = (
            "TASK: classify_capture\n"
            f"Known projects: {names}\n"
            "Classify the INPUT as one of: idea, task, goal, blocker, note. Give a short title. "
            "If a project clearly matches, give its id as project_hint, else null. "
            "List at most 2 questions whose answers are needed to make it actionable "
            "(e.g. definition of done, deadline, who it waits on). Return JSON with keys "
            "kind, title, project_hint, questions, confidence.\n"
            f"INPUT: {raw_text}"
        )
        data, res = await gateway.complete_json("small", SYSTEM, prompt)
        rec.model, rec.tokens = res.model, res.tokens
        kind = data.get("kind") if data.get("kind") in ("idea", "task", "goal", "blocker", "note") else "note"
        questions = [q for q in (data.get("questions") or []) if isinstance(q, str)][:2]
        project_id = data.get("project_hint") if any(p["id"] == data.get("project_hint") for p in projects) else None
        idea = memory.create("ideas", "idea", {
            "raw_text": raw_text, "kind": kind, "project_id": project_id,
            "interview": [{"q": None, "a": raw_text, "title": data.get("title") or raw_text[:80]}],
            "pending_question": questions[0] if questions else None,
            "status": "refining" if questions else "refined",
        })
        if len(questions) > 1:
            memory.patch("ideas", idea["id"], {"interview": idea["interview"] + [{"queued": questions[1:]}]})
            idea = memory.get("ideas", idea["id"])  # type: ignore[assignment]
        rec.output_ref = [idea["id"]]
    return idea  # type: ignore[return-value]


async def answer(idea_id: str, answer_text: str) -> dict[str, Any]:
    """Owner answers the pending question. Moves to the next queued question or marks refined."""
    idea = memory.get("ideas", idea_id)
    if not idea:
        raise KeyError(idea_id)
    with activity(AGENT, "interview answer recorded") as rec:
        rec.inputs_ref = [idea_id]
        interview: list[dict] = [e for e in idea["interview"] if "queued" not in e]
        queued: list[str] = next((e["queued"] for e in idea["interview"] if "queued" in e), [])
        interview.append({"q": idea.get("pending_question"), "a": answer_text})
        nxt = queued.pop(0) if queued else None
        if queued:
            interview.append({"queued": queued})
        updated = memory.patch("ideas", idea_id, {
            "interview": interview, "pending_question": nxt,
            "status": "refining" if nxt else "refined",
        })
    return updated  # type: ignore[return-value]


def convert(idea_id: str, *, project_id: str | None = None, owner_id: str | None = None, due_date: str | None = None) -> dict[str, Any]:
    """File a refined capture as a task, goal or blocker (or keep as idea/note)."""
    idea = memory.get("ideas", idea_id)
    if not idea:
        raise KeyError(idea_id)
    with activity(AGENT, f"capture converted to {idea['kind']}") as rec:
        rec.inputs_ref = [idea_id]
        title = next((e.get("title") for e in idea["interview"] if e.get("title")), idea["raw_text"][:80])
        qa = "\n".join(f"Q: {e['q']}\nA: {e['a']}" for e in idea["interview"] if e.get("q"))
        description = idea["raw_text"] + (f"\n\n{qa}" if qa else "")
        project_id = project_id or idea.get("project_id")
        created: dict | None = None
        if idea["kind"] == "task":
            created = memory.create("tasks", "task", {"title": title, "description": description, "project_id": project_id,
                                                      "owner_id": owner_id, "due_date": due_date, "source": "owner",
                                                      "last_activity_at": memory.db.now_iso()})
        elif idea["kind"] == "goal":
            created = memory.create("goals", "goal", {"title": title, "description": description, "deadline": due_date})
        elif idea["kind"] == "blocker":
            created = memory.create("blockers", "blk", {"description": description, "waiting_on": owner_id,
                                                        "since": memory.db.now_iso()})
        new_status = "converted" if created else "refined"
        updated = memory.patch("ideas", idea_id, {"status": new_status, "converted_to": created["id"] if created else None})
        rec.output_ref = [created["id"]] if created else []
    return {"idea": updated, "created": created}


async def daily_brief(run_id: str | None = None, covered_since: str | None = None) -> dict[str, Any]:
    with activity(AGENT, "daily brief produced", run_id) as rec:
        counts = memory.summary_counts()
        overdue = memory.overdue_tasks()[:10]
        stale = memory.stale_tasks()[:10]
        idle = memory.idle_people()[:10]
        blockers = memory.open_blockers()[:10]
        goals = memory.list_("goals", "status != 'done'", limit=50)
        pending = memory.list_("suggestions", "status='pending'", limit=20)
        latest = {t: memory.latest_report(t) for t in ("orchestrator", "validator", "doctor", "analyst")}

        lines = [f"# Daily brief", "",
                 f"**{counts['open_tasks']}** open tasks · **{counts['overdue_tasks']}** overdue · "
                 f"**{counts['open_blockers']}** blockers · **{counts['idle_people']}** idle people · "
                 f"**{counts['stale_tasks']}** stale tasks · **{counts['pending_suggestions']}** suggestions waiting", ""]
        off = [g for g in goals if g["status"] != "on-track"]
        lines += ["## Goals", *(f"- {g['status'].upper()}: {g['title']}" for g in off)] if off else ["## Goals", "- All tracked goals on track"]
        if overdue:
            lines += ["", "## Overdue", *(f"- {t['title']} ({t.get('project_name') or '-'}, {t.get('owner_name') or 'unassigned'}, due {t['due_date']})" for t in overdue)]
        if blockers:
            lines += ["", "## Blockers", *(f"- {b['description']} — {b['age_days']}d, waiting on {b.get('waiting_on_name') or '?'}" for b in blockers)]
        if idle:
            lines += ["", "## Idle people", *(f"- {p['name']} ({p['role'] or '-'})" for p in idle)]
        if stale:
            lines += ["", f"## Stale tasks (no activity {memory.settings.stale_days}+ days)",
                      *(f"- {t['title']} — {t.get('owner_name') or 'unassigned'}" for t in stale)]
        if pending:
            lines += ["", f"## {len(pending)} suggestions need your decision", *(f"- [{s['agent']}] {s['type']}: {s['rationale'][:120]}" for s in pending[:8])]
        for t, r in latest.items():
            if r:
                lines += ["", f"## Latest {t} report ({r['created_at'][:16]})", r["body"].split("\n## ", 1)[0][:800]]

        body = "\n".join(lines)
        # The large model turns the facts into a short "what I'd do today" section.
        res = await gateway.complete("large", SYSTEM,
                                     "TASK: brief_recommendation\nGiven this brief, write 3 to 5 one-line actions the owner "
                                     "should take today, most important first. Plain text bullets.\n\n" + body)
        rec.model, rec.tokens = res.model, res.tokens
        body += "\n\n## What I'd do today\n" + res.text.strip()
        rep = memory.save_report(AGENT, "daily-brief", body, {"counts": counts}, run_id)
        rec.output_ref = [rep["id"]]
    return rep


async def run(run_id: str, covered_since: str | None) -> None:
    await daily_brief(run_id, covered_since)

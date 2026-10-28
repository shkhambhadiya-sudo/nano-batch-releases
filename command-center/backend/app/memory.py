"""COS Memory: the fixed set of read/write functions over the database (spec §4.1).
Agents never touch the DB directly - they call these. The owner's UI calls them
through the API layer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import db
from .config import settings

JSON_COLS = {
    "projects": ("matrix_ids",), "people": ("skills", "teams"), "ideas": ("interview",),
    "flags": ("task_ids", "evidence"), "suggestions": ("payload",), "reports": ("data",),
    "agent_runs": ("checkpoint",),
}


def _decode(table: str, row: dict | None) -> dict | None:
    if row is None:
        return None
    for col in JSON_COLS.get(table, ()):
        row[col] = db.loads(row.get(col), [] if col not in ("evidence", "payload", "data", "checkpoint") else {})
    return row


def _decode_all(table: str, rows: list[dict]) -> list[dict]:
    return [_decode(table, r) for r in rows]  # type: ignore[misc]


# ---- generic -----------------------------------------------------------------

def get(table: str, id_: str) -> dict | None:
    with db.connect() as conn:
        return _decode(table, db.one(conn, f"SELECT * FROM {table} WHERE id=?", (id_,)))


def list_(table: str, where: str = "1=1", params: tuple = (), order: str = "created_at DESC", limit: int = 500) -> list[dict]:
    with db.connect() as conn:
        return _decode_all(table, db.q(conn, f"SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ?", (*params, limit)))


def create(table: str, prefix: str, fields: dict[str, Any]) -> dict:
    now = db.now_iso()
    row = {"id": db.new_id(prefix), "created_at": now, **fields}
    if table in ("goals", "projects", "people", "tasks", "ideas", "blockers"):
        row.setdefault("updated_at", now)
    with db.connect() as conn:
        db.insert(conn, table, row)
    return get(table, row["id"])  # type: ignore[return-value]


def patch(table: str, id_: str, fields: dict[str, Any]) -> dict | None:
    if table in ("goals", "projects", "people", "tasks", "ideas", "blockers"):
        fields = {**fields, "updated_at": db.now_iso()}
    with db.connect() as conn:
        db.update(conn, table, id_, fields)
    return get(table, id_)


def delete(table: str, id_: str) -> None:
    with db.connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (id_,))


# ---- goals / projects --------------------------------------------------------

def project_goals(project_id: str) -> list[dict]:
    with db.connect() as conn:
        return db.q(conn, "SELECT g.* FROM goals g JOIN project_goals pg ON pg.goal_id=g.id WHERE pg.project_id=?", (project_id,))


def set_project_goals(project_id: str, goal_ids: list[str]) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM project_goals WHERE project_id=?", (project_id,))
        for g in goal_ids:
            conn.execute("INSERT OR IGNORE INTO project_goals (project_id, goal_id) VALUES (?, ?)", (project_id, g))


def goal_projects(goal_id: str) -> list[dict]:
    with db.connect() as conn:
        return db.q(conn, "SELECT p.* FROM projects p JOIN project_goals pg ON pg.project_id=p.id WHERE pg.goal_id=?", (goal_id,))


# ---- tasks -------------------------------------------------------------------

def upsert_task_from_deeds(deeds_task: dict[str, Any]) -> dict:
    """Idempotent sync of one 11deeds task into memory, keyed by deeds_task_id."""
    with db.connect() as conn:
        existing = db.one(conn, "SELECT id FROM tasks WHERE deeds_task_id=?", (deeds_task["deeds_task_id"],))
        project = db.one(conn, "SELECT id FROM projects WHERE deeds_project_id=?", (deeds_task.get("deeds_project_id"),)) if deeds_task.get("deeds_project_id") else None
        owner = db.one(conn, "SELECT id FROM people WHERE deeds_user_id=?", (deeds_task.get("deeds_user_id"),)) if deeds_task.get("deeds_user_id") else None
    fields = {
        "title": deeds_task["title"], "description": deeds_task.get("description", ""),
        "status": deeds_task.get("status", "todo"), "priority": deeds_task.get("priority", "medium"),
        "due_date": deeds_task.get("due_date"), "last_activity_at": deeds_task.get("last_activity_at"),
        "time_consumed_min": int(deeds_task.get("time_consumed_min", 0)),
        "project_id": project["id"] if project else None, "owner_id": owner["id"] if owner else None,
        "deeds_task_id": deeds_task["deeds_task_id"], "source": "deeds",
    }
    if existing:
        return patch("tasks", existing["id"], fields)  # type: ignore[return-value]
    return create("tasks", "task", fields)


def upsert_person_from_deeds(user: dict[str, Any]) -> dict:
    with db.connect() as conn:
        existing = db.one(conn, "SELECT id FROM people WHERE deeds_user_id=?", (user["deeds_user_id"],))
    fields = {"name": user["name"], "role": user.get("role", ""), "skills": user.get("skills", []),
              "teams": user.get("teams", []), "deeds_user_id": user["deeds_user_id"],
              "last_completed_at": user.get("last_completed_at")}
    if existing:
        return patch("people", existing["id"], fields)  # type: ignore[return-value]
    return create("people", "person", fields)


def upsert_project_from_deeds(proj: dict[str, Any]) -> dict:
    with db.connect() as conn:
        existing = db.one(conn, "SELECT id FROM projects WHERE deeds_project_id=?", (proj["deeds_project_id"],))
    fields = {"name": proj["name"], "team": proj.get("team", ""), "deeds_project_id": proj["deeds_project_id"]}
    if existing:
        return patch("projects", existing["id"], {"name": fields["name"], "team": fields["team"]})  # type: ignore[return-value]
    return create("projects", "proj", fields)


def add_link(from_task: str, to_task: str, type_: str, set_by: str = "agent") -> None:
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO task_links (from_task, to_task, type, set_by, created_at) VALUES (?,?,?,?,?)",
                     (from_task, to_task, type_, set_by, db.now_iso()))


def links(task_id: str | None = None) -> list[dict]:
    with db.connect() as conn:
        if task_id:
            return db.q(conn, "SELECT * FROM task_links WHERE from_task=? OR to_task=?", (task_id, task_id))
        return db.q(conn, "SELECT * FROM task_links")


# ---- suggestions / flags -----------------------------------------------------

def suggest(agent: str, type_: str, payload: dict[str, Any], rationale: str) -> dict:
    return create("suggestions", "sug", {"agent": agent, "type": type_, "payload": payload, "rationale": rationale})


def decide_suggestion(id_: str, approved: bool) -> dict | None:
    return patch("suggestions", id_, {"status": "approved" if approved else "rejected", "decided_at": db.now_iso()})


def suggestion_accuracy() -> list[dict]:
    with db.connect() as conn:
        rows = db.q(conn, """
            SELECT agent,
                   SUM(status='pending')  AS pending,
                   SUM(status='approved') AS approved,
                   SUM(status='rejected') AS rejected
            FROM suggestions GROUP BY agent""")
        perms = {r["agent"]: r["level"] for r in db.q(conn, "SELECT * FROM agent_permissions")}
    for r in rows:
        decided = (r["approved"] or 0) + (r["rejected"] or 0)
        r["accuracy"] = round(100 * (r["approved"] or 0) / decided) if decided else None
        r["level"] = perms.get(r["agent"], 0)
    return rows


def raise_flag(person_id: str | None, task_ids: list[str], time_min: int, goal_id: str | None, reason: str, evidence: dict) -> dict:
    return create("flags", "flag", {"person_id": person_id, "task_ids": task_ids, "time_consumed_min": time_min,
                                    "goal_id": goal_id, "reason": reason, "evidence": evidence})


def decide_flag(id_: str, decision: str, note: str = "") -> dict | None:
    return patch("flags", id_, {"decision": decision, "decision_note": note, "decided_at": db.now_iso()})


# ---- reports / permissions ---------------------------------------------------

def save_report(agent: str, type_: str, body: str, data: dict | None = None, run_id: str | None = None) -> dict:
    return create("reports", "rep", {"agent": agent, "type": type_, "body": body, "data": data or {}, "run_id": run_id})


def latest_report(type_: str) -> dict | None:
    rows = list_("reports", "type=?", (type_,), limit=1)
    return rows[0] if rows else None


def permission_level(agent: str) -> int:
    with db.connect() as conn:
        row = db.one(conn, "SELECT level FROM agent_permissions WHERE agent=?", (agent,))
    return int(row["level"]) if row else 0


def set_permission_level(agent: str, level: int) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO agent_permissions (agent, level) VALUES (?, ?) ON CONFLICT(agent) DO UPDATE SET level=excluded.level",
                     (agent, max(0, min(3, level))))


# ---- derived views (spec §5) -------------------------------------------------

def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def idle_people() -> list[dict]:
    with db.connect() as conn:
        return db.q(conn, """
            SELECT p.*, 0 AS active_tasks FROM people p
            WHERE NOT EXISTS (SELECT 1 FROM tasks t WHERE t.owner_id=p.id AND t.status IN ('todo','in-progress','blocked'))
            ORDER BY p.last_completed_at""")


def people_load() -> list[dict]:
    with db.connect() as conn:
        rows = db.q(conn, """
            SELECT p.id, p.name, p.role, p.teams, p.last_completed_at,
                   SUM(CASE WHEN t.status IN ('todo','in-progress','blocked') THEN 1 ELSE 0 END) AS active_tasks,
                   SUM(CASE WHEN t.status='in-progress' THEN 1 ELSE 0 END) AS in_progress,
                   SUM(CASE WHEN t.status='blocked' THEN 1 ELSE 0 END) AS blocked,
                   MAX(t.last_activity_at) AS last_activity_at
            FROM people p LEFT JOIN tasks t ON t.owner_id=p.id
            GROUP BY p.id ORDER BY active_tasks DESC""")
    for r in rows:
        r["teams"] = db.loads(r["teams"], [])
        n = r["active_tasks"] or 0
        r["load"] = "idle" if n == 0 else "light" if n <= 2 else "normal" if n <= 5 else "overloaded"
    return rows


def stale_tasks(days: int | None = None) -> list[dict]:
    cutoff = _cutoff(days or settings.stale_days)
    with db.connect() as conn:
        return db.q(conn, """
            SELECT t.*, p.name AS owner_name, pr.name AS project_name FROM tasks t
            LEFT JOIN people p ON p.id=t.owner_id LEFT JOIN projects pr ON pr.id=t.project_id
            WHERE t.status IN ('todo','in-progress','blocked') AND COALESCE(t.last_activity_at, t.updated_at) < ?
            ORDER BY COALESCE(t.last_activity_at, t.updated_at)""", (cutoff,))


def overdue_tasks() -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    with db.connect() as conn:
        return db.q(conn, """
            SELECT t.*, p.name AS owner_name, pr.name AS project_name FROM tasks t
            LEFT JOIN people p ON p.id=t.owner_id LEFT JOIN projects pr ON pr.id=t.project_id
            WHERE t.status IN ('todo','in-progress','blocked') AND t.due_date IS NOT NULL AND t.due_date < ?
            ORDER BY t.due_date""", (today,))


def open_blockers() -> list[dict]:
    with db.connect() as conn:
        rows = db.q(conn, """
            SELECT b.*, t.title AS task_title, pr.name AS project_name, pr.id AS project_id,
                   w.name AS waiting_on_name, r.name AS routed_to_name
            FROM blockers b LEFT JOIN tasks t ON t.id=b.task_id LEFT JOIN projects pr ON pr.id=t.project_id
            LEFT JOIN people w ON w.id=b.waiting_on LEFT JOIN people r ON r.id=b.routed_to
            WHERE b.status != 'resolved' ORDER BY b.since""")
    now = datetime.now(timezone.utc)
    for r in rows:
        try:
            r["age_days"] = (now - datetime.fromisoformat(r["since"]).astimezone(timezone.utc)).days
        except ValueError:
            r["age_days"] = None
    return rows


def project_overview() -> list[dict]:
    with db.connect() as conn:
        rows = db.q(conn, """
            SELECT pr.*,
                   SUM(CASE WHEN t.status IN ('todo','in-progress','blocked') THEN 1 ELSE 0 END) AS open_tasks,
                   SUM(CASE WHEN t.status='blocked' THEN 1 ELSE 0 END) AS blocked_tasks,
                   SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) AS done_tasks,
                   SUM(CASE WHEN t.status IN ('todo','in-progress','blocked') AND t.due_date < date('now') THEN 1 ELSE 0 END) AS overdue_tasks
            FROM projects pr LEFT JOIN tasks t ON t.project_id=pr.id
            GROUP BY pr.id ORDER BY pr.name""")
    return _decode_all("projects", rows)


def summary_counts() -> dict[str, Any]:
    with db.connect() as conn:
        c = lambda sql, p=(): (db.one(conn, sql, p) or {}).get("n", 0)  # noqa: E731
        return {
            "projects": c("SELECT COUNT(*) n FROM projects"),
            "goals": c("SELECT COUNT(*) n FROM goals"),
            "people": c("SELECT COUNT(*) n FROM people"),
            "open_tasks": c("SELECT COUNT(*) n FROM tasks WHERE status IN ('todo','in-progress','blocked')"),
            "overdue_tasks": c("SELECT COUNT(*) n FROM tasks WHERE status IN ('todo','in-progress','blocked') AND due_date < date('now')"),
            "open_blockers": c("SELECT COUNT(*) n FROM blockers WHERE status != 'resolved'"),
            "pending_suggestions": c("SELECT COUNT(*) n FROM suggestions WHERE status='pending'"),
            "open_flags": c("SELECT COUNT(*) n FROM flags WHERE decision IS NULL"),
            "ideas_backlog": c("SELECT COUNT(*) n FROM ideas WHERE status IN ('captured','refining','refined')"),
            "idle_people": len(idle_people()),
            "stale_tasks": len(stale_tasks()),
        }

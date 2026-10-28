"""Doctor (spec §4.4): every 6 hours, audits every agent's activity log (COS
included), confirms scheduled runs happened and reports arrived, and writes a
diagnosis with suggested fixes. Diagnoses only - never changes code."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import db, memory
from ..config import settings
from ..llm.gateway import gateway
from ..log import activity, sanitized_export

AGENT = "doctor"
SYSTEM = "You are the Doctor agent: a systems reliability reviewer. You read sanitised logs and produce short, concrete findings."

EXPECTED = {  # agent -> max hours between successful runs before it counts as missed
    "orchestrator": 14, "validator": 26, "analyst": 26, "cos": 26, "doctor": 7,
}


async def run(run_id: str, covered_since: str | None) -> None:
    now = datetime.now(timezone.utc)
    since = covered_since or (now - timedelta(hours=settings.doctor_interval_hours)).isoformat()
    findings: list[str] = []

    with activity(AGENT, "run cadence checked", run_id):
        with db.connect() as conn:
            for agent, max_h in EXPECTED.items():
                if agent == "doctor":
                    continue
                last = db.one(conn, "SELECT finished_at FROM agent_runs WHERE agent=? AND status='ok' ORDER BY finished_at DESC LIMIT 1", (agent,))
                if not last:
                    findings.append(f"{agent}: has never completed a run")
                elif now - datetime.fromisoformat(last["finished_at"]) > timedelta(hours=max_h):
                    findings.append(f"{agent}: last successful run {last['finished_at']} (> {max_h}h ago)")
            errs = db.q(conn, "SELECT agent, error, started_at FROM agent_runs WHERE status='error' AND started_at >= ? ORDER BY started_at DESC", (since,))
            for e in errs:
                findings.append(f"{e['agent']}: run failed at {e['started_at']} — {e['error']}")

    with activity(AGENT, "activity log audited", run_id) as rec:
        with db.connect() as conn:
            rows = db.q(conn, """SELECT agent, result, COUNT(*) n, AVG(duration_ms) avg_ms, SUM(COALESCE(tokens,0)) tokens
                                 FROM activity_log WHERE ts >= ? GROUP BY agent, result""", (since,))
            slow = db.q(conn, "SELECT agent, action, duration_ms FROM activity_log WHERE ts >= ? AND duration_ms > 120000 ORDER BY duration_ms DESC LIMIT 10", (since,))
            errors = db.q(conn, "SELECT agent, action, error FROM activity_log WHERE ts >= ? AND result='error' ORDER BY id DESC LIMIT 20", (since,))
        rec.notes = f"{sum(r['n'] for r in rows)} log entries since {since}"
        for e in errors:
            findings.append(f"{e['agent']}: '{e['action']}' errored — {e['error']}")
        for s in slow:
            findings.append(f"{s['agent']}: '{s['action']}' took {round(s['duration_ms']/1000)}s")
        if not rows:
            findings.append("no agent activity at all in the audited window")

    with activity(AGENT, "integrations checked", run_id):
        from ..connectors import deeds, matrix  # local import keeps the doctor importable in tests
        llm = await gateway.health()
        d = await deeds.client().health()
        m = await matrix.client().health()
        if not llm.get("ok"):
            findings.append(f"model server unreachable: {llm.get('error')}")
        if not d.get("ok"):
            findings.append(f"11deeds unreachable: {d.get('error')}")
        if not m.get("ok"):
            findings.append(f"11matrix unreachable: {m.get('error')}")
        if settings.llm_backend == "mock":
            findings.append("LLM backend is 'mock' — judgments are rule-based placeholders, not model output")

    with activity(AGENT, "diagnosis written", run_id) as rec:
        table = "\n".join(f"| {r['agent']} | {r['result']} | {r['n']} | {round(r['avg_ms'] or 0)} | {r['tokens']} |" for r in rows)
        sample = sanitized_export(since=since, limit=200)
        res = await gateway.complete("small", SYSTEM,
            "TASK: diagnose\nGiven these findings and a sanitised log sample, suggest up to 5 concrete fixes "
            "for the Engineer, most important first. One line each.\n\nFindings:\n" + "\n".join(f"- {f}" for f in findings) +
            f"\n\nLog sample (first 30 of {len(sample)}):\n" + "\n".join(str(s) for s in sample[:30]))
        rec.model, rec.tokens = res.model, res.tokens
        body = "\n".join([
            "# Doctor diagnosis", "", f"Window: {since} → {now.isoformat()}", "",
            "## Findings", *([f"- {f}" for f in findings] or ["- nothing wrong found"]), "",
            "## Activity by agent", "| agent | result | entries | avg ms | tokens |", "|---|---|---|---|---|", table, "",
            "## Suggested fixes (for Engineer, owner approval required)", res.text.strip(),
        ])
        rep = memory.save_report(AGENT, "doctor", body, {"findings": findings}, run_id)
        rec.output_ref = [rep["id"]]

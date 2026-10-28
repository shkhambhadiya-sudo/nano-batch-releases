"""Append-only activity log (spec §7). Every agent action goes through `log_action`
or the `Activity` context manager, which also captures duration and errors.

`sanitized_export` is the only view the Engineer may read: ids, actions, results
and error messages, with free-text notes dropped."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import db


def log_action(
    agent: str,
    action: str,
    *,
    run_id: str | None = None,
    inputs_ref: list[str] | None = None,
    output_ref: list[str] | None = None,
    model: str | None = None,
    tokens: int | None = None,
    duration_ms: int | None = None,
    result: str = "ok",
    error: str | None = None,
    notes: str | None = None,
) -> None:
    with db.connect() as conn:
        db.insert(conn, "activity_log", {
            "ts": db.now_iso(), "agent": agent, "run_id": run_id, "action": action,
            "inputs_ref": inputs_ref or [], "output_ref": output_ref or [], "model": model,
            "tokens": tokens, "duration_ms": duration_ms, "result": result, "error": error, "notes": notes,
        })


class _Rec:
    """Mutable record handed to the body of an `Activity` block so it can attach
    references and model usage before the entry is written."""

    def __init__(self) -> None:
        self.inputs_ref: list[str] = []
        self.output_ref: list[str] = []
        self.model: str | None = None
        self.tokens: int | None = None
        self.notes: str | None = None
        self.result: str = "ok"


@contextmanager
def activity(agent: str, action: str, run_id: str | None = None) -> Iterator[_Rec]:
    rec = _Rec()
    start = time.monotonic()
    try:
        yield rec
    except Exception as exc:  # noqa: BLE001 - we log and re-raise every failure
        log_action(agent, action, run_id=run_id, inputs_ref=rec.inputs_ref, output_ref=rec.output_ref,
                   model=rec.model, tokens=rec.tokens, duration_ms=int((time.monotonic() - start) * 1000),
                   result="error", error=f"{type(exc).__name__}: {exc}", notes=rec.notes)
        raise
    log_action(agent, action, run_id=run_id, inputs_ref=rec.inputs_ref, output_ref=rec.output_ref,
               model=rec.model, tokens=rec.tokens, duration_ms=int((time.monotonic() - start) * 1000),
               result=rec.result, notes=rec.notes)


def recent(limit: int = 200, agent: str | None = None, since: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM activity_log WHERE 1=1"
    params: list[Any] = []
    if agent:
        sql += " AND agent = ?"
        params.append(agent)
    if since:
        sql += " AND ts >= ?"
        params.append(since)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with db.connect() as conn:
        rows = db.q(conn, sql, tuple(params))
    for r in rows:
        r["inputs_ref"] = db.loads(r["inputs_ref"], [])
        r["output_ref"] = db.loads(r["output_ref"], [])
    return rows


def sanitized_export(since: str | None = None, limit: int = 2000) -> list[dict[str, Any]]:
    keep = ("id", "ts", "agent", "run_id", "action", "model", "tokens", "duration_ms", "result", "error")
    return [{k: r.get(k) for k in keep} for r in recent(limit=limit, since=since)]

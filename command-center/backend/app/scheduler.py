"""Single scheduler process for every agent (spec §8).

Rules:
- Each job knows its schedule (fixed local times, or an interval).
- The last successful run is stored in `agent_runs`; a missed window runs ONCE on
  boot, covering everything since `covered_until` - never once per missed slot.
- Interrupted runs stay `running` in the table; on boot they are marked `error`
  (interrupted) and the next run covers the same window again, using whatever the
  agent checkpointed.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from . import db
from .log import log_action

logger = logging.getLogger("scheduler")

RunFn = Callable[[str, str | None], Awaitable[None]]  # (run_id, covered_since) -> None


@dataclass
class Job:
    agent: str
    run: RunFn
    times: tuple[str, ...] = ()        # "HH:MM" local, for fixed-time jobs
    interval_hours: int | None = None  # for interval jobs


def _local_now() -> datetime:
    return datetime.now().astimezone()


def last_run(agent: str) -> dict | None:
    with db.connect() as conn:
        return db.one(conn, "SELECT * FROM agent_runs WHERE agent=? AND status='ok' ORDER BY finished_at DESC LIMIT 1", (agent,))


def is_due(job: Job, now: datetime | None = None) -> bool:
    """A job is due when at least one scheduled slot has passed since its last
    successful run (or it never ran)."""
    now = now or _local_now()
    last = last_run(job.agent)
    last_at = datetime.fromisoformat(last["finished_at"]).astimezone() if last else None
    if job.interval_hours:
        return last_at is None or now - last_at >= timedelta(hours=job.interval_hours)
    if last_at is None:
        return True
    for day_offset in (1, 0):
        day = (now - timedelta(days=day_offset)).date()
        for t in job.times:
            hh, mm = (int(x) for x in t.split(":"))
            slot = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hh, minute=mm)
            if last_at < slot <= now:
                return True
    return False


async def run_job(job: Job) -> str:
    run_id = db.new_id("run")
    prev = last_run(job.agent)
    covered_since = prev["covered_until"] if prev else None
    started = db.now_iso()
    with db.connect() as conn:
        db.insert(conn, "agent_runs", {"id": run_id, "agent": job.agent, "started_at": started,
                                       "status": "running", "covered_since": covered_since})
    log_action(job.agent, "run started", run_id=run_id, notes=f"covering since {covered_since or 'beginning'}")
    try:
        await job.run(run_id, covered_since)
    except Exception as exc:  # noqa: BLE001
        logger.error("job %s failed: %s", job.agent, traceback.format_exc())
        with db.connect() as conn:
            db.update(conn, "agent_runs", run_id, {"status": "error", "finished_at": db.now_iso(),
                                                    "error": f"{type(exc).__name__}: {exc}"})
        log_action(job.agent, "run failed", run_id=run_id, result="error", error=f"{type(exc).__name__}: {exc}")
        return run_id
    finished = db.now_iso()
    with db.connect() as conn:
        db.update(conn, "agent_runs", run_id, {"status": "ok", "finished_at": finished, "covered_until": finished})
    log_action(job.agent, "run finished", run_id=run_id)
    return run_id


def mark_interrupted() -> int:
    """Runs left in `running` state belong to a previous process (laptop was
    switched off mid-run). Mark them so the window is covered again."""
    with db.connect() as conn:
        rows = db.q(conn, "SELECT id, agent FROM agent_runs WHERE status='running'")
        for r in rows:
            db.update(conn, "agent_runs", r["id"], {"status": "error", "finished_at": db.now_iso(),
                                                     "error": "interrupted: process stopped before run finished"})
    for r in rows:
        log_action(r["agent"], "run marked interrupted", run_id=r["id"], result="error",
                   error="process stopped before run finished")
    return len(rows)


class Scheduler:
    def __init__(self, jobs: list[Job], tick_seconds: int = 60) -> None:
        self.jobs = jobs
        self.tick = tick_seconds
        self._task: asyncio.Task | None = None
        self._locks = {j.agent: asyncio.Lock() for j in jobs}

    async def start(self) -> None:
        interrupted = mark_interrupted()
        log_action("scheduler", "boot", notes=f"{interrupted} interrupted run(s) marked; catching up due jobs once each")
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def trigger(self, agent: str) -> str:
        job = next(j for j in self.jobs if j.agent == agent)
        async with self._locks[agent]:
            return await run_job(job)

    async def _loop(self) -> None:
        while True:
            for job in self.jobs:
                try:
                    if is_due(job) and not self._locks[job.agent].locked():
                        asyncio.create_task(self.trigger(job.agent))
                except Exception:  # noqa: BLE001
                    logger.error("scheduler tick error for %s: %s", job.agent, traceback.format_exc())
            await asyncio.sleep(self.tick)

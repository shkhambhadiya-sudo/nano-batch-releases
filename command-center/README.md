# Command Center

Local AI chief-of-staff for running many projects at once. Runs entirely on one Mac
with local models; the owner uses it from an iPad. Design: [`../COMMAND_CENTER_SPEC.md`](../COMMAND_CENTER_SPEC.md).

## What's in the box

| Piece | Where | Status |
|---|---|---|
| COS Memory (SQLite + query API) | `backend/app/memory.py`, `schema.sql` | done |
| COS Agent: capture/interview, filing, daily brief | `backend/app/agents/cos.py` | done |
| Orchestrator (sync, risk, links, blockers, health, goals) | `agents/orchestrator.py` | done |
| Validator (flags with evidence, always L0) | `agents/validator.py` | done |
| Doctor (6-hourly audit of every agent's log) | `agents/doctor.py` | done |
| Analyst (11matrix growth vs. work done) | `agents/analyst.py` | done |
| Scheduler with boot catch-up (one run per missed window) | `backend/app/scheduler.py` | done |
| Activity log + sanitised export for the Engineer | `backend/app/log.py` | done |
| Permission ladder L0–L3 with per-agent accuracy | `memory.py`, Approvals screen | done |
| 11deeds / 11matrix connectors | `backend/app/connectors/` | **mock fixtures**; HTTP client ready, routes are placeholders |
| iPad PWA: Command Center, Capture, Map, Approvals, Blockers, People, Ideas, Goals, System | `frontend/src/screens/` | done |
| Local models via Ollama (large + small tier) | `backend/app/llm/gateway.py` | done; `mock` backend for running without a model |

## Run it on the Mac

```bash
git clone -b claude/command-center-spec https://github.com/shkhambhadiya-sudo/nano-batch-releases
cd nano-batch-releases/command-center
./setup.sh run            # installs deps, builds UI, writes .env, pulls models if Ollama exists, runs tests, starts
```

Open `http://<mac-name>.local:8787` on the iPad (same Wi-Fi) → Share → *Add to Home Screen*.
For access from outside the network use Tailscale and the Mac's Tailscale address.

To start at login and restart on crash:

```bash
./setup.sh install-service
```

## Configure

Everything is in `.env` (created by `setup.sh`):

- `CC_LLM_BACKEND=ollama|mock`, `CC_MODEL_LARGE`, `CC_MODEL_SMALL` — install [Ollama](https://ollama.com), then `ollama pull <model>`.
  Suggested on 128 GB: large `qwen2.5:72b` (or `llama3.3:70b`), small `qwen2.5:7b`.
- `CC_DEEDS_BACKEND=mock|http` + `CC_DEEDS_URL` / `CC_DEEDS_TOKEN` — the HTTP client expects
  `GET /api/users`, `/api/projects`, `/api/tasks?updated_since=`, `/api/attendance?since=`, `/api/health`.
  Adjust `connectors/deeds.py::_norm_*` to the real response shapes; agents only see the normalised form.
- `CC_MATRIX_BACKEND=mock|http` + `CC_MATRIX_URL` — expects `GET /api/metrics?days=7`, `/api/health`.
- Schedules: `CC_ORCHESTRATOR_TIMES=09:00,18:00`, `CC_VALIDATOR_TIMES`, `CC_ANALYST_TIMES`, `CC_BRIEF_TIMES`, `CC_DOCTOR_INTERVAL_HOURS=6`.

## Day-one flow

1. **Goals** → add your real goals.
2. **System** → run `orchestrator` (pulls 11deeds; with `mock` it loads 18 sample projects / 40 people).
3. **Map** → edit each project and tick the goals it serves.
4. **Capture** → dump ideas; COS asks follow-ups; file as task / goal / blocker.
5. **Approvals** → approve/reject what the agents propose. Accuracy builds per agent; promote levels when you trust them.
6. **System** → read the Doctor's diagnosis after a day; anything it suggests goes to the Engineer (Claude Code), who changes code only after your approval.

## Development

```bash
.venv/bin/python -m pytest -q                  # backend tests
cd frontend && npm run dev                      # UI with hot reload on :5173 (proxies /api to :8787)
CC_SCHEDULER=0 .venv/bin/uvicorn app.main:app --app-dir backend --port 8787 --reload
```

Rules the code enforces (from the spec): agents talk only to COS Memory, never to each other;
every agent action is logged; nothing is applied without owner approval at L0; the Validator can
never be promoted; the Engineer reads only `/api/system/log/sanitized`, never raw data.

# HANDOFF — Command Center

> Give this file to a new Claude Code session. It contains everything from the previous session: the owner's situation, every decision made, what was built, what is still mock, and what the new session should do first.

---

## 0. Where the code is

| | |
|---|---|
| **GitHub repo** | `shkhambhadiya-sudo/nano-batch-releases` |
| **Branch** | `claude/command-center-spec` (not merged to `main`; `main` only has a README for an unrelated "Nano Batch" app) |
| **Clone** | `git clone -b claude/command-center-spec https://github.com/shkhambhadiya-sudo/nano-batch-releases` |
| **Project folder** | `command-center/` inside the repo |
| **Design document** | `COMMAND_CENTER_SPEC.md` at the repo root (the full architecture agreed with the owner) |
| **Run guide** | `command-center/README.md` |
| **This file** | `HANDOFF.md` at the repo root |

The repo name is historical (it was a release feed for another app). The Command Center lives in its own folder and can be moved to its own repo at any time.

---

## 1. The owner and the problem (context from the conversation)

- The owner runs **18 projects** at once (Shopify stores, internal platforms, an agency) with **~100 people** across teams. Many people work on multiple projects.
- Ideas arrive constantly and get lost because nothing captures and organises them.
- Many people are idle or have been on the same task for ~6 months without moving any goal.
- There is no single picture of where everything stands, what's blocked, and what's at risk.
- The owner wants to open one app on an **iPad**, dump ideas, see the whole picture, and plan/assign from there, with AI connecting tasks, setting priorities, and chasing deadlines.

### Existing systems
- **11deeds** — their own task-management platform on a VPS. Every employee has an account. Holds tasks, assignments, comments/chats, check-in/break/leave times, time consumed per task. AI bots can already chat with users. Chat is being added so AI can reach people. → to be connected via MCP/HTTP, **read-only in month 1**.
- **11matrix** — their own analytics platform: every project/store's Google Analytics, ad accounts, Search Console. → read-only.
- **Slack** — general chat today; not integrated (task talk moves to 11deeds).

### Hard constraints decided by the owner
1. **Everything runs on one laptop**: Apple **M5 Ultra, 128 GB** unified memory. App, DB, agents, models.
2. **Local models only.** No company/employee data goes to any external AI API.
3. **One exception — the Engineer** is Claude Code (cloud). It may see **code, config, Doctor reports, sanitised logs only**. Never raw employee data, chats, time logs, analytics.
4. **Laptop on/off**: when off, agents stop; when on, they resume where they left off — no duplicate catch-up runs, no stale alerts.
5. **Owner-only user** for now. Employees keep using 11deeds.
6. **Month 1 = suggestions only (L0).** Autonomy granted per agent later based on measured accuracy. Validator flags are suggestions **forever**.
7. No voice input in v1.

---

## 2. The agent design (agreed)

Rule for all: **no agent talks to another agent directly; everything goes through COS.** Every agent logs every action.

| Agent | Job | Schedule |
|---|---|---|
| **COS** (Chief of Staff) | Owns all data. Split into **COS Memory** (SQLite + fixed query functions — exact, fast) and **COS Agent** (judgment: classify captures, ask follow-ups, file items, daily brief, review flags with owner) | always on |
| **Orchestrator** | Sync 11deeds → memory; task status; deadline risk; task links (duplicates/dependencies); blockers routed; project health; goal on-track check | 2×/day (09:00, 18:00) |
| **Validator** | Reviews human work vs goals; raises **flags with evidence** (person, tasks, time, goal, reason). Always L0 | daily 08:30 |
| **Doctor** | Audits every agent's activity log (COS included), checks runs happened, integrations up; writes diagnosis + suggested fixes. Never changes code | every 6 h |
| **Engineer** | Claude Code on the Mac. Builds/repairs. Acts only on Doctor-defined problems or owner requests, **only after owner approval** | on demand |
| **Analyst** (added in discussion) | Reads 11matrix; links growth to work done per project ("tasks done but traffic flat") | daily 08:00 |

### Permission ladder
L0 suggest only (month 1, all) → L1 reminders/status requests → L2 assign/reassign → L3 priorities/deadlines. Promotion per agent, by owner, using the recorded approve/reject accuracy. Validator locked at L0.

### Items the owner never explicitly confirmed (defaults were chosen — marked ASSUMED in the spec §12)
- 11deeds / 11matrix MCPs don't exist yet → we built HTTP client stubs + mock fixtures, read-only.
- Validator once daily. Orchestrator 09:00/18:00. Single approval queue filterable by agent. SQLite. Employees to be informed about AI review (owner to confirm; check local data-protection law, e.g. India DPDP).

---

## 3. What was built (v1, complete and tested)

Stack: **Python 3.11+ / FastAPI / SQLite** backend, **React + Vite PWA** frontend, **Ollama** for local models (with a rule-based `mock` backend so everything runs without a model server), one process started by **launchd**.

```
command-center/
  COMMAND_CENTER_SPEC.md   (../ at repo root)
  README.md                run/config guide
  setup.sh                 one-shot Mac installer: uv venv, npm build, .env, ollama pull, tests, run / install-service
  pyproject.toml
  launchd/com.commandcenter.server.plist
  backend/app/
    config.py              all settings from env/.env (CC_*)
    schema.sql             goals, projects, project_goals, milestones, people, tasks, task_links, ideas,
                           blockers, flags, suggestions, agent_runs, activity_log, reports, agent_permissions, kv
    db.py                  sqlite helpers (WAL, dict rows, JSON columns)
    memory.py              COS Memory: CRUD, deeds upserts, links, suggestions + accuracy, flags, reports,
                           permissions, derived views (idle people, people load, stale, overdue, blockers, project overview, counts)
    log.py                 append-only activity log; `activity()` context manager; `sanitized_export()` for the Engineer
    scheduler.py           fixed-time + interval jobs; `is_due` = one run per missed window; `mark_interrupted` on boot
    llm/gateway.py         large/small tiers; OllamaBackend (/api/chat, json mode) and MockBackend (prompts start with "TASK: <kind>")
    connectors/deeds.py    DeedsMock (fixtures/deeds.json) + DeedsHTTP (placeholder routes); normalised shapes documented in file
    connectors/matrix.py   MatrixMock + MatrixHTTP
    connectors/fixtures/   18 projects, 40 people, 189 tasks, attendance, 18 analytics properties (generated sample data)
    agents/cos.py          capture() → classify + follow-up questions; answer(); convert() → task/goal/blocker; daily_brief()
    agents/orchestrator.py sync, risk heuristic (overdue/blocked/not-started/stalled) → suggestions, blockers, project health, goal status, link detection → suggestions; no duplicate pending suggestions per task
    agents/validator.py    candidates (idle / long-running / off-goal) → model assessment → flags with evidence
    agents/doctor.py       cadence check, error scan, slow actions, integration health, LLM-written fix list → report
    agents/analyst.py      % change per property, "work done but flat" detection → report
    main.py                FastAPI: /api/overview, /capture, /ideas/*, generic CRUD /{table}, /links, /views/*, /suggestions, /flags,
                           /permissions, /reports, /system/health|log|log/sanitized|run/{agent}; serves frontend/dist; starts scheduler
  backend/tests/test_core.py   8 tests: memory views, accuracy/permissions, log sanitising, scheduler catch-up,
                               interrupted runs, COS interview, all agents end-to-end on mock data, API smoke
  frontend/src/
    App.jsx                sidebar nav (hash-routed), badges
    components.jsx         useLoad, Pill, Markdown renderer, Modal, Field
    screens/Home.jsx       tiles, 18 project cards with health, goals, daily brief, agent accuracy
    screens/Capture.jsx    text box → COS classification → inline follow-up question → file as task/goal/blocker
    screens/MapView.jsx    Goals → Projects → Tasks tree, links shown, project/task editors
    screens/Approvals.jsx  suggestions (approve/reject, filter by agent), validator flags (valid/discussed/dismiss), permission levels
    screens/Blockers.jsx   blockers wall with age, route-to person, resolve; overdue tasks
    screens/People.jsx     load heatmap (idle/light/normal/overloaded), stale tasks, assign from person
    screens/Ideas.jsx      backlog, file / drop
    screens/Goals.jsx      goal editor, latest analyst report
    screens/Health.jsx     model/11deeds/11matrix status, schedule, run-agent-now buttons, Doctor diagnosis, runs, activity log
```

### Verified in the previous session
- `pytest`: 8/8 pass.
- Full agent cycle on mock data: 18 projects, 40 people, 130 open tasks, 40 overdue, 32 blockers, ~80 suggestions, ~38 flags generated.
- All 9 screens driven in headless Chromium (iPad landscape 1180×820): no console/page errors. Capture flow tested through the real UI.
- Built in a **Linux cloud container**, NOT on the owner's Mac. It has never been run on the Mac. Ollama was never exercised (mock backend only).

---

## 4. What is still mock / unfinished

1. **Not yet running on the Mac.** Needs `./setup.sh run` on the M5 Ultra.
2. **Models**: `.env` defaults `CC_LLM_BACKEND=ollama`, `CC_MODEL_LARGE=qwen2.5:72b`, `CC_MODEL_SMALL=qwen2.5:7b`. Never tested against real Ollama. Prompt JSON parsing is defensive but untested with real outputs.
3. **11deeds / 11matrix**: fixture data. `DeedsHTTP` / `MatrixHTTP` routes (`/api/users`, `/api/projects`, `/api/tasks?updated_since=`, `/api/attendance`, `/api/metrics?days=`) are **guesses**; `_norm_*` functions must be adapted to the real API.
4. **Write actions to 11deeds** (reminders, assignments) are recorded only; L1+ has no effect until write access exists.
5. **Milestones** table exists but has no UI.
6. **No auth** on the app (single owner on a private network; add a token if exposed via Tailscale to shared devices).
7. Validator heuristics are tuned to the fixture; thresholds in `validator._candidates` will need tuning on real data.

---

## 5. Instructions for the new session

You are the **Engineer** agent from `COMMAND_CENTER_SPEC.md` §4.5. Follow these steps in order and do not skip the analysis.

**Step 1 — Analyse the codebase before changing anything.**
```
Read COMMAND_CENTER_SPEC.md fully.
Read command-center/README.md.
Read every file under command-center/backend/app/ and command-center/frontend/src/.
Run: cd command-center && ./setup.sh   (installs, builds, runs tests — do not pass "run" yet)
```
Then report back to the owner, in plain language: what exists, whether tests pass on this machine, which parts are mock, and anything in the code that contradicts the spec.

**Step 2 — Confirm the ASSUMED items** (spec §12) with the owner before building further.

**Step 3 — Make it live on the Mac.**
- `./setup.sh run` → confirm `http://localhost:8787` loads and the iPad can reach `http://<mac>.local:8787`.
- Install Ollama if missing, pull the two models, switch `.env` from mock to ollama, run each agent from the System screen, verify real model output and fix any JSON-parsing issues in `llm/gateway.py` and the agents' prompts.
- `./setup.sh install-service` so it starts at login.

**Step 4 — Connect real data.**
- Get the 11deeds API/MCP details from the owner. Adapt `connectors/deeds.py` (`DeedsHTTP` + `_norm_*`), set `CC_DEEDS_BACKEND=http`, run the Orchestrator, verify people/projects/tasks appear correctly. Same for 11matrix.

**Step 5 — Operate as the Engineer.**
- Only change code for problems the Doctor reports or the owner asks for, and **only after the owner approves the proposed solution**.
- Never read raw employee data; use `/api/system/log/sanitized` and the Doctor reports.
- Keep every change on the `claude/command-center-spec` branch (or a new branch from it); commit and push after each verified step.

**Rules that must hold in any change you make**
- Agents read/write only through `memory.py`; no agent imports another agent.
- Every agent action is wrapped in `log.activity()`.
- Nothing is applied automatically at L0; new agent outputs are `memory.suggest()` or `memory.raise_flag()`.
- The Validator can never be promoted above L0.
- Scheduler jobs must stay idempotent across catch-up runs (no duplicate suggestions, no repeated alerts).

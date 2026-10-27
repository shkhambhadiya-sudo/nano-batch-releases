# Command Center — Architecture & Build Brief

> Hand this file to a Claude Code session running **locally on the M5 Ultra**. That session is the **Engineer** agent. It builds everything else described here.
> Status: design agreed in discussion. Nothing built yet. Items marked **ASSUMED** were defaults chosen by Claude and not yet confirmed by the owner — confirm or change them before building.

---

## 1. Problem statement

The owner runs **18 projects** at once with **~100 people** across multiple teams. Three problems:

1. **Ideas leak.** Ideas arrive faster than they can be captured and organised, and are lost without execution.
2. **Resources are invisible.** No view of who is overloaded, who is idle, or who has been stuck on a task for months (some tasks have been "in progress" for ~6 months with no impact on goals).
3. **No single picture.** Nothing shows, in one place, where every project stands, what is blocked, what is at risk, and which ideas are waiting.

Goal: an **AI chief-of-staff system** on top of a structured map of the organisation. The owner opens it on an iPad, dumps ideas, sees the entire picture, and plans and assigns work from there. The AI connects tasks, sets priorities, watches deadlines, and makes sure work actually moves the company's goals.

---

## 2. Hard constraints (non-negotiable)

| Constraint | Detail |
|---|---|
| **Runs on one laptop** | Apple M5 Ultra, 128 GB unified memory. Everything (app, database, agents, models) runs here. |
| **Local models only** | No company or employee data goes to any external AI API. Models run locally (Ollama / LM Studio / MLX). |
| **One exception: the Engineer** | The Engineer is Claude Code (Anthropic cloud). It may see **code, config, Doctor reports, and sanitised error logs**. It must **never** see raw employee data, task chats, time logs, or analytics data. Logs it reads are stripped of personal data first. |
| **Laptop on/off** | When the laptop is off, every agent stops. When it comes back, every agent resumes from where it stopped — no duplicate runs, no stale alerts. |
| **Single user (owner) for now** | Only the owner uses the Command Center. Employees keep using 11deeds. |
| **Month 1 = suggestions only** | No agent takes any action on its own. Every assignment, priority change, reminder, or flag is a suggestion the owner approves or rejects. Autonomy is granted later, per agent, based on measured accuracy. |
| **Validator flags are always suggestions** | Permanently, not just in month 1. A human decides on every flag about a person. |
| **No voice input in v1** | Deferred. |

---

## 3. Existing systems to connect

### 3.1 11deeds (own task-management platform, hosted on a VPS)
Every employee has an account. Contains:
- Tasks, assignments, status, deadlines
- Comments and chats on tasks
- Check-in time, break time, leave time
- Time consumed per task
- AI bots can already chat with users and ask for updates
- Chat functionality is being added so AI can reach people directly

**Connection:** MCP server. **ASSUMED:** does not exist yet — the Engineer builds it. **Read-only** in month 1; write access (create task, send chat) added when autonomy levels rise.

### 3.2 11matrix (own analytics platform)
Every project / Shopify store has connected: Google Analytics, all ad accounts, Google Search Console.

**Connection:** MCP server. **ASSUMED:** does not exist yet — the Engineer builds it. Read-only.

### 3.3 Slack
Used today for general chat. Not integrated in v1; all task discussion moves to 11deeds.

---

## 4. Agents

Six agents. Rule that applies to all of them:

> **No agent talks to another agent directly. All data goes through COS.** An agent that needs data asks COS. An agent that produces data hands it to COS.

> **Every agent must log every action**, however small, in the activity log (format in §7). The Doctor audits these logs.

### 4.1 COS — Chief of Staff
**Role:** owner of all data and the owner's main counterpart.

Implemented as two parts:
- **COS Memory** — a database with a fixed set of query functions. Exact, fast, and the only place other agents read from. (A language model is not a database; routing every lookup through a model would be slow and unreliable.)
- **COS Agent** — the judgment layer. Decides what to store and how, merges duplicates, decides what deserves the owner's attention, and talks to the owner.

Responsibilities:
- Receive reports from every agent and store them properly.
- Answer data requests from agents (via COS Memory).
- Make sure agents and employees are fully occupied with work that actually lifts the company; challenge work that doesn't connect to a goal.
- Store Validator flags separately with full evidence (see §4.4) and review them with the owner.
- **Idea capture ("Interview mode"):** the owner dumps a raw idea, task, goal, or worry. COS classifies it (idea / task / goal / blocker, which project, likely owner) and asks only the follow-up questions needed to make it well-defined ("What does done look like?", "Deadline?", "Does this block anything?"). Then files it.
- Produce the **daily brief** for the owner.

**Schedule:** always on while the laptop is on.

### 4.2 Orchestrator
**Role:** keeps the whole picture current and on time.

Each run:
- Pull current task state from 11deeds (via COS).
- Update status of every task; predict which will / won't finish on time.
- Detect and record relationships between tasks (depends-on, duplicates, related).
- Identify blockers and route each one to the right person (as a suggestion in month 1).
- Check every goal: are we on track or not, and why.
- Report everything to COS.

**Schedule:** twice a day. **ASSUMED:** 09:00 and 18:00.

### 4.3 Validator
**Role:** checks human work.

- Reads tasks, reports, comments, time logs from 11deeds (via COS).
- Checks that each person's work connects to a company goal.
- Raises **flags**. Every flag must cite: the person, the specific tasks, time consumed, the goal it does/doesn't connect to, the reason, and timestamps. Time logged is **not** treated as value delivered.
- Flags go to COS; COS stores them separately and reviews them with the owner.

**Schedule:** **ASSUMED:** once daily, morning.

**Prerequisite — ASSUMED:** employees are informed that AI reviews work in 11deeds. Check local employment and data-protection rules (e.g. India's DPDP Act if applicable).

### 4.4 Doctor
**Role:** system health and improvement.

- Wakes **every 6 hours**, reads the activity logs of every agent **including COS**.
- Confirms nothing is broken, all scheduled runs happened, all reports arrived.
- Continuously looks for ways to make the system more effective.
- Produces a **diagnosis report**: problems found + suggested solutions. Reports go to COS and are shown to the owner.
- The Doctor diagnoses only; it never changes code.

**Schedule:** every 6 hours (with catch-up rules in §8).

### 4.5 Engineer
**Role:** builds and repairs the system.

- Lives in **Claude Code** on the laptop, always.
- Is spawned first; it builds every other agent and the app.
- Works only on problems the Doctor defines (or the owner requests), and **only after the owner approves** the solution.
- Data access rule: code, config, Doctor reports, sanitised logs only. Never raw employee data.

### 4.6 Analyst *(added during discussion)*
**Role:** connects work to growth.

- Reads 11matrix (GA, ads, Search Console, store growth) via COS.
- Links growth metrics to projects and to the work done on them ("Project 7's SEO tasks are done but traffic is flat").
- Reports to COS; feeds the goal check and the daily brief.

**Schedule:** daily.

### 4.7 Adding agents later
The Doctor and Engineer can propose new agents. Same rules apply: COS-only communication, mandatory activity log, suggestion-only until promoted.

---

## 5. Data model (COS Memory)

Core entities:

| Entity | Key fields |
|---|---|
| **Goal** | id, title, description, metric, target, deadline, owner, status (on-track / at-risk / off-track), defined **here** by the owner (not in 11deeds) |
| **Project** | id, name, goals[], team, health (on-track / at-risk / blocked), 11deeds project id, 11matrix store/property ids |
| **Milestone** | id, project, title, due date, status |
| **Task** | id, project, milestone, title, description, owner, status, priority, due date, created, last activity at, time consumed, 11deeds task id, source (owner-idea / 11deeds / agent) |
| **TaskLink** | from task, to task, type (depends-on / duplicate-of / related-to), set by (agent / owner) |
| **Idea** | id, raw text, classified type, project (optional), interview Q&A, status (captured / refined / converted / dropped) |
| **Blocker** | id, task, description, waiting on (person), since, routed to, status |
| **Person** | id, name, role, skills[], teams[], projects[], 11deeds user id, current load, last completed at, idle since |
| **Flag** | id, person, raised by (Validator), tasks[], time consumed, goal (or none), reason, evidence, created, owner decision, decided at |
| **Suggestion** | id, agent, type (assign / reassign / priority / reminder / deadline / blocker-route / other), payload, rationale, status (pending / approved / rejected), decided at |
| **AgentRun** | agent, started, finished, status, covered-since, checkpoint |
| **ActivityLog** | see §7 |
| **Report** | agent, run, type (orchestrator / validator / doctor / analyst / daily-brief), body |

Derived views the app needs: **idle people** (no active task), **stale tasks** (no activity in N weeks — default 2), **overloaded people**, **blocker age**, **goal health**, **suggestion accuracy per agent**.

Storage: **ASSUMED** SQLite (single file, trivially backed up, more than enough for 100 people / 18 projects). Postgres only if it proves necessary.

---

## 6. Permission ladder

Every suggestion ever made is recorded with the owner's approve/reject decision, so each agent has a measured accuracy rate.

| Level | What the agent may do on its own |
|---|---|
| **L0** (month 1, all agents) | Nothing. Everything is a suggestion. |
| **L1** | Low-risk actions: send reminders, ask a person for a status update in 11deeds. |
| **L2** | Assign / reassign tasks. |
| **L3** | Set priorities and deadlines. |

Promotion is **per agent**, decided by the owner using the accuracy numbers (e.g. "Orchestrator: 91% of suggestions approved over 30 days"). Validator flags stay at L0 forever.

---

## 7. Activity log format

Every agent writes one record per action. This is what the Doctor audits.

```
timestamp        ISO 8601
agent            cos | orchestrator | validator | doctor | engineer | analyst
run_id           id of the AgentRun this belongs to
action           short verb phrase ("fetched 11deeds tasks", "raised flag", "asked COS for goals")
inputs_ref       references to the data used (ids, not copies)
output_ref       references to what was produced
model            which local model was used, if any
tokens / duration
result           ok | error | skipped
error            message if any
notes            free text
```

Logs are append-only. A **sanitised export** (ids and error messages only, no names, no chat text) is what the Engineer is allowed to read.

---

## 8. Scheduling, boot, and catch-up

- Each scheduled agent stores **last successful run** and **covered-until** timestamps.
- On laptop boot, every agent whose schedule was missed runs **once**, covering the window since its last run. It does **not** run once per missed slot (the Doctor doesn't run three times after a 14-hour sleep).
- Long tasks checkpoint progress. On restart they resume from the checkpoint.
- Alerts generated during a catch-up run are stamped with the time they were discovered, and anything already stale (deadline passed during the off period) is reported as such, not as a fresh warning.
- Scheduler: a single local process (e.g. a small Python/Node service started by `launchd` at login) that owns all timers. No agent has its own cron.

---

## 9. The app (owner's iPad)

**Form:** a web app served from the laptop, installed to the iPad home screen as a PWA. Reached over local Wi-Fi; from elsewhere via **Tailscale** (private network between own devices — nothing exposed to the internet).

**Screens:**

1. **Command Center (home)** — 18 project cards with health; counts of blockers, at-risk tasks, idle people, pending suggestions; today's daily brief from COS.
2. **Capture** — one text box. Type anything. COS classifies and, if needed, asks follow-up questions inline. Files the result.
3. **Map** — Goals → Projects → Milestones → Tasks, with links/dependencies visible. Click any node to drill in.
4. **Blockers wall** — every blocker, age, who it's waiting on, routed status.
5. **People** — directory with role, skills, load, last completed, idle-since. Heatmap of overloaded vs idle. Assign from here (as a suggestion, month 1).
6. **Ideas backlog** — captured ideas not yet converted.
7. **Approval queue** — **ASSUMED:** one queue for all suggestions and flags, filterable by agent and type. Approve / reject / edit. Shows each agent's running accuracy.
8. **Goals** — define and edit goals; see on-track status and Analyst evidence.
9. **System health** — latest Doctor report, agent run history, errors.

---

## 10. Tech stack (recommended, Engineer may adjust with reason)

| Layer | Choice |
|---|---|
| Models | Served locally via **Ollama** or **LM Studio** (MLX backend for Apple Silicon). Two tiers: a **large reasoning model** (~70–120B) for COS / Validator / Orchestrator / Analyst judgment; a **small fast model** for classification, summarising, and the Doctor's first pass over logs. Exact models chosen at build time. |
| Agent runtime | Python (asyncio) **or** Node — Engineer's choice; one language for all agents. Each agent = a module with a `run(since)` entry point + tool access to COS Memory only. |
| Database | SQLite (ASSUMED) |
| Backend / API | FastAPI (Python) or Fastify (Node); also serves the PWA |
| Frontend | React + Vite PWA, touch-first layout for iPad |
| Integrations | Two MCP servers: `11deeds-mcp`, `11matrix-mcp` (read-only in v1) |
| Scheduler | One local service under `launchd` |
| Remote access | Tailscale |
| Source control | Local git repo; optional private GitHub remote for backup |

---

## 11. Build order

1. **Engineer bootstrap** — repo, stack scaffold, SQLite schema (§5), activity-log writer (§7), scheduler with catch-up (§8), local model gateway with the two tiers.
2. **COS Memory + COS Agent** — storage, query API, Interview mode, daily brief.
3. **App v1** — Capture, Command Center, Map, Approval queue. (Enough for the owner to start dumping ideas on day one.)
4. **11deeds MCP (read-only)** → Person and Task sync into COS Memory.
5. **Orchestrator** — status, links, blockers, goal check. Suggestions appear in the queue.
6. **Doctor** — log audit, diagnosis reports, System health screen.
7. **Validator** — flags with evidence. (Only after the employee-notification prerequisite is handled.)
8. **11matrix MCP + Analyst**.
9. Remaining screens: Blockers wall, People heatmap, Ideas backlog, Goals.
10. Month-1 review → decide L1 promotions per agent.

---

## 12. Open items for the owner to confirm

- [ ] 11deeds MCP: exists or build? Read-only OK for month 1?
- [ ] 11matrix MCP: exists or build?
- [ ] Validator schedule: daily (assumed) or twice daily?
- [ ] Employees informed about AI review of work?
- [ ] Laptop's normal on-hours → Orchestrator run times (assumed 09:00 / 18:00)
- [ ] Approval queue: single queue (assumed) or per agent?
- [ ] SQLite acceptable (assumed)?

---

## 13. How to start the Engineer session on the Mac

```bash
npm install -g @anthropic-ai/claude-code
mkdir ~/command-center && cd ~/command-center && git init
cp /path/to/COMMAND_CENTER_SPEC.md .
claude
```

First message to that session:

> You are the Engineer agent described in COMMAND_CENTER_SPEC.md. Read it fully. Confirm the open items in §12 with me, then begin build step 1 from §11. Do not proceed past a step without showing me it works.

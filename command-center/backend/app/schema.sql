-- COS Memory schema. See COMMAND_CENTER_SPEC.md §5 and §7.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS goals (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    metric      TEXT DEFAULT '',
    target      TEXT DEFAULT '',
    deadline    TEXT,
    owner       TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'on-track',   -- on-track | at-risk | off-track | done
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    team            TEXT DEFAULT '',
    health          TEXT NOT NULL DEFAULT 'on-track', -- on-track | at-risk | blocked
    deeds_project_id TEXT,
    matrix_ids      TEXT DEFAULT '[]',                -- JSON list of 11matrix store/property ids
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_goals (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    goal_id    TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, goal_id)
);

CREATE TABLE IF NOT EXISTS milestones (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    due_date   TEXT,
    status     TEXT NOT NULL DEFAULT 'open',          -- open | done
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    role             TEXT DEFAULT '',
    skills           TEXT DEFAULT '[]',              -- JSON list
    teams            TEXT DEFAULT '[]',              -- JSON list
    deeds_user_id    TEXT,
    last_completed_at TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id) ON DELETE SET NULL,
    milestone_id    TEXT REFERENCES milestones(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    owner_id        TEXT REFERENCES people(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'todo',    -- todo | in-progress | blocked | done | dropped
    priority        TEXT NOT NULL DEFAULT 'medium',  -- low | medium | high | critical
    due_date        TEXT,
    last_activity_at TEXT,
    time_consumed_min INTEGER DEFAULT 0,
    deeds_task_id   TEXT,
    source          TEXT NOT NULL DEFAULT 'owner',   -- owner | deeds | agent
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_id);
CREATE INDEX IF NOT EXISTS idx_tasks_deeds ON tasks(deeds_task_id);

CREATE TABLE IF NOT EXISTS task_links (
    from_task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    to_task   TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    type      TEXT NOT NULL,                         -- depends-on | duplicate-of | related-to
    set_by    TEXT NOT NULL DEFAULT 'agent',         -- agent | owner
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_task, to_task, type)
);

CREATE TABLE IF NOT EXISTS ideas (
    id          TEXT PRIMARY KEY,
    raw_text    TEXT NOT NULL,
    kind        TEXT,                                -- idea | task | goal | blocker | note
    project_id  TEXT REFERENCES projects(id) ON DELETE SET NULL,
    interview   TEXT NOT NULL DEFAULT '[]',          -- JSON list of {q, a}
    pending_question TEXT,
    status      TEXT NOT NULL DEFAULT 'captured',    -- captured | refining | refined | converted | dropped
    converted_to TEXT,                               -- id of task/goal/blocker created from it
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blockers (
    id          TEXT PRIMARY KEY,
    task_id     TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    waiting_on  TEXT REFERENCES people(id) ON DELETE SET NULL,
    since       TEXT NOT NULL,
    routed_to   TEXT REFERENCES people(id) ON DELETE SET NULL,
    status      TEXT NOT NULL DEFAULT 'open',        -- open | routed | resolved
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flags (
    id           TEXT PRIMARY KEY,
    person_id    TEXT REFERENCES people(id) ON DELETE SET NULL,
    raised_by    TEXT NOT NULL DEFAULT 'validator',
    task_ids     TEXT NOT NULL DEFAULT '[]',
    time_consumed_min INTEGER DEFAULT 0,
    goal_id      TEXT REFERENCES goals(id) ON DELETE SET NULL,
    reason       TEXT NOT NULL,
    evidence     TEXT NOT NULL DEFAULT '{}',         -- JSON
    decision     TEXT,                               -- accepted | dismissed | discussed
    decision_note TEXT,
    decided_at   TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id         TEXT PRIMARY KEY,
    agent      TEXT NOT NULL,
    type       TEXT NOT NULL,                        -- assign | reassign | priority | reminder | deadline | blocker-route | link | other
    payload    TEXT NOT NULL DEFAULT '{}',           -- JSON
    rationale  TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',      -- pending | approved | rejected
    decided_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status);

CREATE TABLE IF NOT EXISTS agent_runs (
    id            TEXT PRIMARY KEY,
    agent         TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'running',   -- running | ok | error
    covered_since TEXT,
    covered_until TEXT,
    checkpoint    TEXT DEFAULT '{}',                 -- JSON, for resume
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent, started_at);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    run_id      TEXT,
    action      TEXT NOT NULL,
    inputs_ref  TEXT DEFAULT '[]',
    output_ref  TEXT DEFAULT '[]',
    model       TEXT,
    tokens      INTEGER,
    duration_ms INTEGER,
    result      TEXT NOT NULL DEFAULT 'ok',          -- ok | error | skipped
    error       TEXT,
    notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_ts ON activity_log(ts);
CREATE INDEX IF NOT EXISTS idx_log_agent ON activity_log(agent, ts);

CREATE TABLE IF NOT EXISTS reports (
    id         TEXT PRIMARY KEY,
    agent      TEXT NOT NULL,
    run_id     TEXT,
    type       TEXT NOT NULL,                        -- orchestrator | validator | doctor | analyst | daily-brief
    body       TEXT NOT NULL,                        -- markdown
    data       TEXT DEFAULT '{}',                    -- JSON
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(type, created_at);

CREATE TABLE IF NOT EXISTS agent_permissions (
    agent TEXT PRIMARY KEY,
    level INTEGER NOT NULL DEFAULT 0                 -- 0..3, spec §6
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

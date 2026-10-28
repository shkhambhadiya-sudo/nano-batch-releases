import React from 'react'
import { useLoad, Pill, Markdown, healthClass } from '../components.jsx'
import { api } from '../api.js'

export default function Home({ go }) {
  const [o, reload] = useLoad('/overview')
  if (!o) return <p className="sub">Loading…</p>
  const c = o.counts
  const tiles = [
    ['open_tasks', 'open tasks', ''], ['overdue_tasks', 'overdue', c.overdue_tasks ? 'bad' : 'ok'],
    ['open_blockers', 'blockers', c.open_blockers ? 'warn' : 'ok'], ['idle_people', 'idle people', c.idle_people ? 'bad' : 'ok'],
    ['stale_tasks', 'stale tasks', c.stale_tasks ? 'warn' : 'ok'], ['pending_suggestions', 'suggestions waiting', c.pending_suggestions ? 'warn' : ''],
    ['open_flags', 'flags to review', c.open_flags ? 'warn' : ''], ['ideas_backlog', 'ideas in backlog', ''],
  ]
  const runBrief = async () => { await api.post('/system/run/cos'); reload() }
  return (
    <>
      <div className="row spread"><h2>Where we stand</h2>
        <div className="row"><button className="btn sm" onClick={() => go('capture')}>+ Capture</button>
          <button className="btn sm" onClick={runBrief}>Refresh brief</button></div></div>
      <div className="tiles">
        {tiles.map(([k, l, cls]) => <div key={k} className={'tile ' + cls}><div className="n">{c[k] ?? 0}</div><div className="l">{l}</div></div>)}
      </div>

      <div className="section">Projects</div>
      <div className="grid">
        {o.projects.map((p) => (
          <div key={p.id} className="card clickable" onClick={() => go('map')}>
            <div className="row spread"><h3>{p.name}</h3><Pill kind={healthClass(p.health)}>{p.health}</Pill></div>
            <div className="sub">{p.open_tasks || 0} open · {p.overdue_tasks || 0} overdue · {p.blocked_tasks || 0} blocked · {p.done_tasks || 0} done</div>
          </div>
        ))}
        {!o.projects.length && <p className="sub">No projects yet. Run the Orchestrator from System, or add projects in Map.</p>}
      </div>

      <div className="section">Goals</div>
      <div className="list">
        {o.goals.map((g) => <div key={g.id} className="item row spread"><span className="t">{g.title}</span><Pill kind={healthClass(g.status)}>{g.status}</Pill></div>)}
        {!o.goals.length && <p className="sub">No goals defined. Goals are set here, by you — every agent measures against them.</p>}
      </div>

      <div className="section">Daily brief {o.brief && <span style={{ textTransform: 'none' }}>· {o.brief.created_at.slice(0, 16).replace('T', ' ')}</span>}</div>
      <div className="card">{o.brief ? <Markdown text={o.brief.body} /> : <span className="sub">No brief yet — tap "Refresh brief".</span>}</div>

      <div className="section">Agent accuracy (approved ÷ decided)</div>
      <div className="grid">
        {o.accuracy.map((a) => (
          <div key={a.agent} className="card"><div className="row spread"><h3>{a.agent}</h3><Pill>L{a.level}</Pill></div>
            <div className="sub">{a.accuracy == null ? 'no decisions yet' : `${a.accuracy}% approved`} · {a.pending} pending</div></div>
        ))}
      </div>
    </>
  )
}

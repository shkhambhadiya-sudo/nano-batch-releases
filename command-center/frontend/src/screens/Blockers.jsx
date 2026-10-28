import React from 'react'
import { useLoad, Pill } from '../components.jsx'
import { api } from '../api.js'

export default function Blockers({ refresh }) {
  const [rows, reload] = useLoad('/views/blockers')
  const [people] = useLoad('/people')
  const [overdue] = useLoad('/views/overdue')
  const route = async (b, pid) => { await api.patch(`/blockers/${b.id}`, { routed_to: pid || null, status: pid ? 'routed' : 'open' }); reload() }
  const resolve = async (b) => { await api.patch(`/blockers/${b.id}`, { status: 'resolved' }); reload(); refresh() }
  return (
    <>
      <h2>Blockers wall</h2>
      <div className="list">
        {(rows || []).map((b) => (
          <div key={b.id} className="item">
            <div className="row spread"><div className="t">{b.description}</div>
              <Pill kind={b.age_days > 14 ? 'bad' : b.age_days > 5 ? 'warn' : ''}>{b.age_days ?? '?'}d</Pill></div>
            <div className="m">{b.project_name || '—'}{b.task_title ? ` · ${b.task_title}` : ''} · waiting on {b.waiting_on_name || '?'} · {b.status}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <select style={{ width: 'auto' }} value={b.routed_to || ''} onChange={(e) => route(b, e.target.value)}>
                <option value="">route to…</option>{(people || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
              <button className="btn ok sm" onClick={() => resolve(b)}>Resolved</button>
            </div>
          </div>
        ))}
        {rows && !rows.length && <p className="sub">No open blockers.</p>}
      </div>
      <div className="section">Overdue tasks</div>
      <div className="list">
        {(overdue || []).map((t) => <div key={t.id} className="item"><div className="t">{t.title}</div><div className="m">{t.project_name || '—'} · {t.owner_name || 'unassigned'} · due {t.due_date} · {t.status}</div></div>)}
        {overdue && !overdue.length && <p className="sub">None.</p>}
      </div>
    </>
  )
}

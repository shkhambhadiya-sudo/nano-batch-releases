import React, { useState } from 'react'
import { useLoad, Pill, Modal, Field } from '../components.jsx'
import { api, ago } from '../api.js'

export default function People({ refresh }) {
  const [rows, reload] = useLoad('/views/people-load')
  const [stale] = useLoad('/views/stale')
  const [sel, setSel] = useState(null)
  if (!rows) return <p className="sub">Loading…</p>
  const groups = { idle: [], light: [], normal: [], overloaded: [] }
  rows.forEach((r) => groups[r.load].push(r))
  return (
    <>
      <h2>People</h2>
      <p className="sub">{rows.length} people · {groups.idle.length} idle · {groups.overloaded.length} overloaded. Tap a person to assign work (as a suggestion).</p>
      <div className="section">Load heatmap</div>
      <div className="heat">
        {rows.map((p) => (
          <div key={p.id} className={'p clickable ' + p.load} onClick={() => setSel(p)}>
            <div className="t">{p.name}</div>
            <div className="m">{p.role || '—'} · {p.active_tasks || 0} active{p.blocked ? ` · ${p.blocked} blocked` : ''}</div>
            <div className="m">last done {ago(p.last_completed_at)}</div>
          </div>
        ))}
      </div>
      <div className="section">Stale tasks (no activity in a while)</div>
      <div className="list">
        {(stale || []).map((t) => <div key={t.id} className="item"><div className="t">{t.title}</div><div className="m">{t.owner_name || 'unassigned'} · {t.project_name || '—'} · last activity {ago(t.last_activity_at || t.updated_at)} · {Math.round((t.time_consumed_min || 0) / 60)}h logged</div></div>)}
        {stale && !stale.length && <p className="sub">None.</p>}
      </div>
      {sel && <Assign person={sel} onClose={() => { setSel(null); reload(); refresh() }} />}
    </>
  )
}

function Assign({ person, onClose }) {
  const [tasks, setTasks] = useState([])
  const [taskId, setTaskId] = useState('')
  const [why, setWhy] = useState('')
  React.useEffect(() => { api.get('/tasks?limit=5000').then((t) => setTasks(t.filter((x) => x.status !== 'done' && x.status !== 'dropped'))) }, [])
  const mine = tasks.filter((t) => t.owner_id === person.id)
  const submit = async () => {
    // Owner-initiated assignment is applied immediately (it is the owner's decision, not an agent's).
    await api.patch(`/tasks/${taskId}`, { owner_id: person.id })
    onClose()
  }
  return (
    <Modal title={person.name} onClose={onClose}>
      <div className="sub">{person.role} · {(person.teams || []).join(', ')}</div>
      <div className="section">Current work</div>
      <div className="list">{mine.map((t) => <div key={t.id} className="item"><div className="t">{t.title}</div><div className="m">{t.status} · due {t.due_date || '—'}</div></div>)}{!mine.length && <span className="sub">Nothing active</span>}</div>
      <div className="section">Assign a task</div>
      <Field label="Task"><select value={taskId} onChange={(e) => setTaskId(e.target.value)}><option value="">—</option>{tasks.filter((t) => t.owner_id !== person.id).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}</select></Field>
      <button className="btn primary" disabled={!taskId} onClick={submit}>Assign to {person.name}</button>
      <p className="sub" style={{ marginTop: 10 }}>Note: until 11deeds write access is on, this changes the Command Center record only.</p>
    </Modal>
  )
}

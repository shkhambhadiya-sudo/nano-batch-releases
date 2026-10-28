import React, { useState } from 'react'
import { useLoad, Pill, healthClass, Modal, Field } from '../components.jsx'
import { api, daysTo } from '../api.js'

export default function MapView() {
  const [m, reload] = useLoad('/views/map')
  const [open, setOpen] = useState({})
  const [edit, setEdit] = useState(null) // {kind:'project'|'task', row}
  if (!m) return <p className="sub">Loading…</p>
  const tasksByProject = {}
  m.tasks.forEach((t) => { (tasksByProject[t.project_id || '_'] ||= []).push(t) })
  const goalsOf = (pid) => (m.project_goals.find((x) => x.project_id === pid)?.goal_ids || []).map((g) => m.goals.find((x) => x.id === g)?.title).filter(Boolean)
  const linksOf = (tid) => m.links.filter((l) => l.from_task === tid || l.to_task === tid)
  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }))

  return (
    <>
      <div className="row spread"><h2>Map</h2>
        <div className="row"><button className="btn sm" onClick={() => setEdit({ kind: 'project', row: { name: '', team: '', goal_ids: [] } })}>+ Project</button>
          <button className="btn sm" onClick={() => setEdit({ kind: 'task', row: { title: '', project_id: '', priority: 'medium', status: 'todo' } })}>+ Task</button></div></div>
      <p className="sub">Goals → Projects → Tasks. Tap a project to expand. Tap a task to edit.</p>
      <div className="map">
        {m.goals.map((g) => <div key={g.id} className="card goal row spread"><b>{g.title}</b><Pill kind={healthClass(g.status)}>{g.status}</Pill></div>)}
        {m.projects.map((p) => (
          <React.Fragment key={p.id}>
            <div className="card proj clickable" onClick={() => toggle(p.id)}>
              <div className="row spread"><b>{p.name}</b>
                <div className="row"><Pill kind={healthClass(p.health)}>{p.health}</Pill><span className="sub">{p.open_tasks || 0} open · {p.overdue_tasks || 0} overdue</span>
                  <button className="btn sm" onClick={(e) => { e.stopPropagation(); setEdit({ kind: 'project', row: { ...p, goal_ids: (m.project_goals.find((x) => x.project_id === p.id)?.goal_ids || []) } }) }}>edit</button></div></div>
              {goalsOf(p.id).length ? <div className="sub">→ {goalsOf(p.id).join(', ')}</div> : <div className="sub" style={{ color: 'var(--warn)' }}>not linked to any goal</div>}
            </div>
            {open[p.id] && (tasksByProject[p.id] || []).filter((t) => t.status !== 'done' && t.status !== 'dropped').map((t) => (
              <TaskRow key={t.id} t={t} links={linksOf(t.id)} tasks={m.tasks} onClick={() => setEdit({ kind: 'task', row: t })} />
            ))}
          </React.Fragment>
        ))}
        {(tasksByProject._ || []).length > 0 && (
          <>
            <div className="card proj clickable" onClick={() => toggle('_')}><b>Unassigned to a project</b> <span className="sub">{tasksByProject._.length}</span></div>
            {open._ && tasksByProject._.map((t) => <TaskRow key={t.id} t={t} links={linksOf(t.id)} tasks={m.tasks} onClick={() => setEdit({ kind: 'task', row: t })} />)}
          </>
        )}
      </div>
      {edit && <Editor edit={edit} goals={m.goals} projects={m.projects} onClose={() => { setEdit(null); reload() }} />}
    </>
  )
}

function TaskRow({ t, links, tasks, onClick }) {
  const d = daysTo(t.due_date)
  const title = (id) => tasks.find((x) => x.id === id)?.title || id
  return (
    <div className="card task clickable" onClick={onClick}>
      <div className="row spread"><span>{t.title}</span>
        <div className="row"><Pill kind={t.status === 'blocked' ? 'bad' : t.status === 'in-progress' ? 'info' : ''}>{t.status}</Pill>
          <Pill kind={t.priority === 'critical' ? 'bad' : t.priority === 'high' ? 'warn' : ''}>{t.priority}</Pill>
          {d != null && <Pill kind={d < 0 ? 'bad' : d <= 3 ? 'warn' : ''}>{d < 0 ? `${-d}d overdue` : `${d}d left`}</Pill>}</div></div>
      {links.length > 0 && <div className="sub">{links.map((l, i) => <span key={i}>{l.from_task === t.id ? `${l.type} → ${title(l.to_task)}` : `← ${l.type} ${title(l.from_task)}`}{i < links.length - 1 ? ' · ' : ''}</span>)}</div>}
    </div>
  )
}

function Editor({ edit, goals, projects, onClose }) {
  const [row, setRow] = useState(edit.row)
  const [people, setPeople] = React.useState([])
  React.useEffect(() => { api.get('/people').then(setPeople) }, [])
  const set = (k) => (e) => setRow({ ...row, [k]: e.target.value })
  const table = edit.kind === 'project' ? 'projects' : 'tasks'
  const save = async () => {
    const body = { ...row }; ['open_tasks', 'blocked_tasks', 'done_tasks', 'overdue_tasks', 'created_at', 'updated_at', 'id', 'matrix_ids'].forEach((k) => delete body[k])
    if (row.id) await api.patch(`/${table}/${row.id}`, body); else await api.post(`/${table}`, body)
    onClose()
  }
  const remove = async () => { if (confirm('Delete?')) { await api.del(`/${table}/${row.id}`); onClose() } }
  return (
    <Modal title={(row.id ? 'Edit ' : 'New ') + edit.kind} onClose={onClose}>
      {edit.kind === 'project' ? (
        <>
          <Field label="Name"><input value={row.name} onChange={set('name')} /></Field>
          <Field label="Team"><input value={row.team || ''} onChange={set('team')} /></Field>
          <Field label="Health"><select value={row.health || 'on-track'} onChange={set('health')}>{['on-track', 'at-risk', 'blocked'].map((h) => <option key={h}>{h}</option>)}</select></Field>
          <Field label="Goals this project serves">
            {goals.map((g) => <label key={g.id} style={{ display: 'block' }}><input type="checkbox" style={{ width: 'auto', marginRight: 8 }} checked={row.goal_ids.includes(g.id)}
              onChange={(e) => setRow({ ...row, goal_ids: e.target.checked ? [...row.goal_ids, g.id] : row.goal_ids.filter((x) => x !== g.id) })} />{g.title}</label>)}
            {!goals.length && <span className="sub">No goals yet</span>}
          </Field>
        </>
      ) : (
        <>
          <Field label="Title"><input value={row.title} onChange={set('title')} /></Field>
          <Field label="Description"><textarea value={row.description || ''} onChange={set('description')} /></Field>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <Field label="Project"><select value={row.project_id || ''} onChange={set('project_id')}><option value="">—</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="Owner"><select value={row.owner_id || ''} onChange={set('owner_id')}><option value="">—</option>{people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          </div>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <Field label="Status"><select value={row.status} onChange={set('status')}>{['todo', 'in-progress', 'blocked', 'done', 'dropped'].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Priority"><select value={row.priority} onChange={set('priority')}>{['low', 'medium', 'high', 'critical'].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Due"><input type="date" value={row.due_date || ''} onChange={set('due_date')} /></Field>
          </div>
        </>
      )}
      <div className="row spread"><button className="btn primary" onClick={save}>Save</button>{row.id && <button className="btn bad sm" onClick={remove}>Delete</button>}</div>
    </Modal>
  )
}

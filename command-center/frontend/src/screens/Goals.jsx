import React, { useState } from 'react'
import { useLoad, Pill, healthClass, Modal, Field, Markdown } from '../components.jsx'
import { api } from '../api.js'

export default function Goals({ refresh }) {
  const [rows, reload] = useLoad('/goals')
  const [reports] = useLoad('/reports?type_=analyst&limit=1')
  const [edit, setEdit] = useState(null)
  return (
    <>
      <div className="row spread"><h2>Goals</h2><button className="btn sm primary" onClick={() => setEdit({ title: '', description: '', metric: '', target: '', deadline: '', status: 'on-track' })}>+ Goal</button></div>
      <p className="sub">Goals are defined here, by you. Projects link to them; the Orchestrator checks them daily; the Validator flags work that serves none.</p>
      <div className="grid">
        {(rows || []).map((g) => (
          <div key={g.id} className="card clickable" onClick={() => setEdit(g)}>
            <div className="row spread"><h3>{g.title}</h3><Pill kind={healthClass(g.status)}>{g.status}</Pill></div>
            <div className="sub">{g.metric ? `${g.metric} → ${g.target}` : ''}{g.deadline ? ` · by ${g.deadline}` : ''}</div>
            {g.description && <div className="sub" style={{ marginTop: 6 }}>{g.description}</div>}
          </div>
        ))}
      </div>
      <div className="section">Latest growth analysis (11matrix)</div>
      <div className="card">{reports?.[0] ? <Markdown text={reports[0].body} /> : <span className="sub">No analyst report yet.</span>}</div>
      {edit && <GoalEditor row={edit} onClose={() => { setEdit(null); reload(); refresh() }} />}
    </>
  )
}

function GoalEditor({ row: init, onClose }) {
  const [row, setRow] = useState(init)
  const set = (k) => (e) => setRow({ ...row, [k]: e.target.value })
  const save = async () => {
    const body = { ...row }; ['id', 'created_at', 'updated_at'].forEach((k) => delete body[k])
    if (row.id) await api.patch(`/goals/${row.id}`, body); else await api.post('/goals', body)
    onClose()
  }
  const remove = async () => { if (confirm('Delete goal?')) { await api.del(`/goals/${row.id}`); onClose() } }
  return (
    <Modal title={row.id ? 'Edit goal' : 'New goal'} onClose={onClose}>
      <Field label="Title"><input value={row.title} onChange={set('title')} /></Field>
      <Field label="Description"><textarea value={row.description || ''} onChange={set('description')} /></Field>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <Field label="Metric"><input value={row.metric || ''} onChange={set('metric')} placeholder="monthly revenue" /></Field>
        <Field label="Target"><input value={row.target || ''} onChange={set('target')} placeholder="1 Cr" /></Field>
        <Field label="Deadline"><input type="date" value={row.deadline || ''} onChange={set('deadline')} /></Field>
      </div>
      <Field label="Status"><select value={row.status} onChange={set('status')}>{['on-track', 'at-risk', 'off-track', 'done'].map((s) => <option key={s}>{s}</option>)}</select></Field>
      <div className="row spread"><button className="btn primary" onClick={save}>Save</button>{row.id && <button className="btn bad sm" onClick={remove}>Delete</button>}</div>
    </Modal>
  )
}

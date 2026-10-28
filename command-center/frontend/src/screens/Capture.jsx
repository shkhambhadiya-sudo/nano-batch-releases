import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Pill, Field } from '../components.jsx'

export default function Capture({ go, refresh }) {
  const [text, setText] = useState('')
  const [idea, setIdea] = useState(null)
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [projects, setProjects] = useState([])
  const [people, setPeople] = useState([])
  const [file, setFile] = useState({ project_id: '', owner_id: '', due_date: '' })
  const box = useRef()

  useEffect(() => { api.get('/projects').then(setProjects); api.get('/people').then(setPeople); box.current?.focus() }, [])

  const submit = async () => {
    if (!text.trim()) return
    setBusy(true)
    const i = await api.post('/capture', { text })
    setIdea(i); setFile((f) => ({ ...f, project_id: i.project_id || '' })); setText(''); setBusy(false); refresh()
  }
  const reply = async () => {
    if (!answer.trim()) return
    setBusy(true)
    setIdea(await api.post(`/ideas/${idea.id}/answer`, { text: answer })); setAnswer(''); setBusy(false)
  }
  const convert = async () => {
    setBusy(true)
    const r = await api.post(`/ideas/${idea.id}/convert`, {
      project_id: file.project_id || null, owner_id: file.owner_id || null, due_date: file.due_date || null,
    })
    setBusy(false); setIdea(null); refresh()
    alert(r.created ? `Filed as ${idea.kind}: ${r.created.title}` : 'Kept in the ideas backlog')
  }
  const setKind = async (kind) => setIdea(await api.patch(`/ideas/${idea.id}`, { kind }))
  const qa = idea ? idea.interview.filter((e) => e.q) : []

  return (
    <>
      <h2>Capture</h2>
      <p className="sub">Dump anything — an idea, a task, a goal, a worry. COS sorts it and asks only what it needs.</p>
      {!idea && (
        <div className="card">
          <textarea ref={box} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Launch referral program for Aurora before Diwali" />
          <div className="row" style={{ marginTop: 10 }}><button className="btn primary" disabled={busy} onClick={submit}>{busy ? 'Thinking…' : 'Capture'}</button></div>
        </div>
      )}
      {idea && (
        <div className="card">
          <div className="row spread"><h3>{idea.interview[0]?.title || idea.raw_text}</h3>
            <div className="row">{['idea', 'task', 'goal', 'blocker', 'note'].map((k) => (
              <button key={k} className={'btn sm' + (idea.kind === k ? ' primary' : '')} onClick={() => setKind(k)}>{k}</button>))}</div></div>
          <p className="sub">{idea.raw_text}</p>
          {qa.map((e, i) => <div key={i} className="item"><div className="m">{e.q}</div><div className="t">{e.a}</div></div>)}
          {idea.pending_question ? (
            <div style={{ marginTop: 12 }}>
              <div className="t" style={{ marginBottom: 6 }}>COS asks: <b>{idea.pending_question}</b></div>
              <div className="row"><input value={answer} onChange={(e) => setAnswer(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && reply()} placeholder="Your answer" />
                <button className="btn" disabled={busy} onClick={reply}>Answer</button>
                <button className="btn sm" onClick={() => setIdea({ ...idea, pending_question: null, status: 'refined' })}>Skip</button></div>
            </div>
          ) : (
            <div style={{ marginTop: 14 }}>
              <Pill kind="ok">refined</Pill>
              <div className="row" style={{ marginTop: 10, alignItems: 'flex-start' }}>
                <Field label="Project"><select value={file.project_id} onChange={(e) => setFile({ ...file, project_id: e.target.value })}>
                  <option value="">—</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
                <Field label="Owner"><select value={file.owner_id} onChange={(e) => setFile({ ...file, owner_id: e.target.value })}>
                  <option value="">—</option>{people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
                <Field label="Due"><input type="date" value={file.due_date} onChange={(e) => setFile({ ...file, due_date: e.target.value })} /></Field>
              </div>
              <div className="row"><button className="btn primary" disabled={busy} onClick={convert}>File as {idea.kind}</button>
                <button className="btn" onClick={() => { setIdea(null); go('ideas') }}>Keep in backlog</button></div>
            </div>
          )}
        </div>
      )}
    </>
  )
}

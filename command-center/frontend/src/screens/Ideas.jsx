import React from 'react'
import { useLoad, Pill } from '../components.jsx'
import { api, ago } from '../api.js'

export default function Ideas({ refresh }) {
  const [rows, reload] = useLoad('/ideas')
  const drop = async (i) => { await api.patch(`/ideas/${i.id}`, { status: 'dropped' }); reload(); refresh() }
  const convert = async (i) => { const r = await api.post(`/ideas/${i.id}/convert`, {}); reload(); refresh(); if (r.created) alert(`Filed: ${r.created.title}`) }
  const backlog = (rows || []).filter((i) => ['captured', 'refining', 'refined'].includes(i.status))
  const done = (rows || []).filter((i) => !['captured', 'refining', 'refined'].includes(i.status))
  return (
    <>
      <h2>Ideas backlog</h2>
      <div className="list">
        {backlog.map((i) => (
          <div key={i.id} className="item">
            <div className="row spread"><div className="t">{i.interview?.[0]?.title || i.raw_text}</div><div><Pill kind="info">{i.kind}</Pill> <Pill>{i.status}</Pill></div></div>
            <div className="m">{i.raw_text} · {ago(i.created_at)}</div>
            {i.pending_question && <div className="m">Open question: {i.pending_question}</div>}
            <div className="row" style={{ marginTop: 8 }}>
              {i.kind !== 'idea' && i.kind !== 'note' && <button className="btn sm primary" onClick={() => convert(i)}>File as {i.kind}</button>}
              <button className="btn sm bad" onClick={() => drop(i)}>Drop</button>
            </div>
          </div>
        ))}
        {rows && !backlog.length && <p className="sub">Backlog is empty.</p>}
      </div>
      {done.length > 0 && <><div className="section">Converted / dropped</div>
        <div className="list">{done.map((i) => <div key={i.id} className="item"><span className="t">{i.interview?.[0]?.title || i.raw_text}</span> <Pill>{i.status}</Pill></div>)}</div></>}
    </>
  )
}

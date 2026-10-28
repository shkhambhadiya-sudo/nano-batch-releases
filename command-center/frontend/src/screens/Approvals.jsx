import React, { useState } from 'react'
import { useLoad, Pill } from '../components.jsx'
import { api, ago } from '../api.js'

export default function Approvals({ refresh }) {
  const [tab, setTab] = useState('suggestions')
  const [agent, setAgent] = useState('')
  const [s, reloadS] = useLoad('/suggestions')
  const [f, reloadF] = useLoad('/flags')
  const [perm, reloadP] = useLoad('/permissions')
  const agents = [...new Set((s || []).map((x) => x.agent))]
  const rows = (s || []).filter((x) => !agent || x.agent === agent)

  const decide = async (id, approved) => { await api.post(`/suggestions/${id}/decide`, { approved }); reloadS(); reloadP(); refresh() }
  const decideFlag = async (id, decision) => {
    const note = decision === 'discussed' ? prompt('Note for the record (what was discussed / decided)?') || '' : ''
    await api.post(`/flags/${id}/decide`, { decision, note }); reloadF(); refresh()
  }
  const setLevel = async (a, level) => { await api.post(`/permissions/${a}`, { level }); reloadP() }

  return (
    <>
      <h2>Approvals</h2>
      <p className="sub">Month 1: every agent is at L0 — nothing happens until you approve it. Each decision trains the accuracy score.</p>
      <div className="tabs">
        <button className={tab === 'suggestions' ? 'active' : ''} onClick={() => setTab('suggestions')}>Suggestions {s ? `(${s.length})` : ''}</button>
        <button className={tab === 'flags' ? 'active' : ''} onClick={() => setTab('flags')}>Validator flags {f ? `(${f.length})` : ''}</button>
        <button className={tab === 'levels' ? 'active' : ''} onClick={() => setTab('levels')}>Permission levels</button>
      </div>

      {tab === 'suggestions' && (
        <>
          <div className="tabs"><button className={!agent ? 'active' : ''} onClick={() => setAgent('')}>all</button>
            {agents.map((a) => <button key={a} className={agent === a ? 'active' : ''} onClick={() => setAgent(a)}>{a}</button>)}</div>
          <div className="list">
            {rows.map((x) => (
              <div key={x.id} className="item">
                <div className="row spread"><div><Pill kind="info">{x.agent}</Pill> <Pill>{x.type}</Pill> <span className="sub">{ago(x.created_at)}</span></div>
                  <div className="row"><button className="btn ok sm" onClick={() => decide(x.id, true)}>Approve</button><button className="btn bad sm" onClick={() => decide(x.id, false)}>Reject</button></div></div>
                <div className="t" style={{ marginTop: 6 }}>{x.rationale}</div>
                {x.task && <div className="m">Task: {x.task.title}{x.task_to ? ` ↔ ${x.task_to.title}` : ''} · {x.task.status} · due {x.task.due_date || '—'}</div>}
              </div>
            ))}
            {s && !rows.length && <p className="sub">Nothing waiting.</p>}
          </div>
        </>
      )}

      {tab === 'flags' && (
        <div className="list">
          {(f || []).map((x) => (
            <div key={x.id} className="item">
              <div className="row spread"><div><b>{x.person?.name || 'unknown'}</b> <span className="sub">{x.person?.role}</span> · <span className="sub">{ago(x.created_at)}</span></div>
                <div className="row"><button className="btn ok sm" onClick={() => decideFlag(x.id, 'accepted')}>Valid</button>
                  <button className="btn sm" onClick={() => decideFlag(x.id, 'discussed')}>Discussed</button>
                  <button className="btn bad sm" onClick={() => decideFlag(x.id, 'dismissed')}>Dismiss</button></div></div>
              <div className="t" style={{ marginTop: 6 }}>{x.reason}</div>
              <div className="m">Time logged: {Math.round((x.time_consumed_min || 0) / 60)}h · Tasks: {x.task_titles.join(', ') || '—'}{x.evidence?.model_reason ? ` · Model: ${x.evidence.model_reason}` : ''}</div>
            </div>
          ))}
          {f && !f.length && <p className="sub">No open flags.</p>}
        </div>
      )}

      {tab === 'levels' && (
        <div className="grid">
          {(perm || []).map((a) => (
            <div key={a.agent} className="card"><h3>{a.agent}</h3>
              <div className="sub">{a.accuracy == null ? 'no decisions yet' : `${a.accuracy}% approved`} · {a.approved || 0} approved · {a.rejected || 0} rejected · {a.pending || 0} pending</div>
              <div className="row" style={{ marginTop: 10 }}>{[0, 1, 2, 3].map((l) => <button key={l} className={'btn sm' + (a.level === l ? ' primary' : '')} disabled={a.agent === 'validator' && l > 0} onClick={() => setLevel(a.agent, l)}>L{l}</button>)}</div>
            </div>
          ))}
          <div className="card sub">L0 suggest only · L1 reminders &amp; status requests · L2 assign/reassign · L3 priorities &amp; deadlines. Validator is locked at L0. Levels above L0 take effect only once 11deeds write access is enabled.</div>
        </div>
      )}
    </>
  )
}

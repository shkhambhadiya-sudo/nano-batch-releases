import React, { useState } from 'react'
import { useLoad, Pill, Markdown } from '../components.jsx'
import { api, ago } from '../api.js'

const AGENTS = ['orchestrator', 'validator', 'analyst', 'cos', 'doctor']

export default function Health({ refresh }) {
  const [h, reload] = useLoad('/system/health')
  const [log, reloadLog] = useLoad('/system/log?limit=100')
  const [busy, setBusy] = useState('')
  const run = async (a) => { setBusy(a); await api.post(`/system/run/${a}`); setBusy(''); reload(); reloadLog(); refresh() }
  if (!h) return <p className="sub">Loading…</p>
  const ok = (x) => <Pill kind={x?.ok ? 'ok' : 'bad'}>{x?.ok ? 'ok' : 'down'}</Pill>
  return (
    <>
      <h2>System</h2>
      <div className="grid">
        <div className="card"><div className="row spread"><h3>Models</h3>{ok(h.llm)}</div><div className="sub">backend: {h.llm.backend} · large: {h.llm.tiers?.large} · small: {h.llm.tiers?.small}</div>{h.llm.note && <div className="sub" style={{ color: 'var(--warn)' }}>{h.llm.note}</div>}{h.llm.error && <div className="sub" style={{ color: 'var(--bad)' }}>{h.llm.error}</div>}</div>
        <div className="card"><div className="row spread"><h3>11deeds</h3>{ok(h.deeds)}</div><div className="sub">{h.deeds.backend}{h.deeds.url ? ` · ${h.deeds.url}` : ''}{h.deeds.error ? ` · ${h.deeds.error}` : ''}</div></div>
        <div className="card"><div className="row spread"><h3>11matrix</h3>{ok(h.matrix)}</div><div className="sub">{h.matrix.backend}{h.matrix.error ? ` · ${h.matrix.error}` : ''}</div></div>
        <div className="card"><h3>Schedule</h3><div className="sub">orchestrator {h.schedule.orchestrator.join(', ')} · validator {h.schedule.validator.join(', ')} · analyst {h.schedule.analyst.join(', ')} · brief {h.schedule.brief.join(', ')} · doctor every {h.schedule.doctor_every_h}h</div></div>
      </div>

      <div className="section">Run an agent now</div>
      <div className="row">{AGENTS.map((a) => <button key={a} className="btn" disabled={!!busy} onClick={() => run(a)}>{busy === a ? 'running…' : a}</button>)}</div>

      <div className="section">Latest Doctor diagnosis</div>
      <div className="card">{h.doctor ? <Markdown text={h.doctor.body} /> : <span className="sub">No diagnosis yet.</span>}</div>

      <div className="section">Recent runs</div>
      <div className="list">
        {h.runs.map((r) => <div key={r.id} className="item row spread"><span><b>{r.agent}</b> <span className="sub">{ago(r.started_at)} · {r.started_at.slice(11, 16)}</span></span>
          <span><Pill kind={r.status === 'ok' ? 'ok' : r.status === 'running' ? 'info' : 'bad'}>{r.status}</Pill>{r.error && <span className="sub"> {r.error}</span>}</span></div>)}
      </div>

      <div className="section">Activity log (latest 100)</div>
      <div className="list">
        {(log || []).map((l) => <div key={l.id} className="item"><span className="sub">{l.ts.slice(5, 16).replace('T', ' ')}</span> <b>{l.agent}</b> {l.action} <Pill kind={l.result === 'ok' ? 'ok' : l.result === 'error' ? 'bad' : ''}>{l.result}</Pill>{l.model ? <span className="sub"> · {l.model} {l.tokens}tok</span> : null}{l.duration_ms != null ? <span className="sub"> · {l.duration_ms}ms</span> : null}{l.notes ? <div className="m">{l.notes}</div> : null}{l.error ? <div className="m" style={{ color: 'var(--bad)' }}>{l.error}</div> : null}</div>)}
      </div>
    </>
  )
}

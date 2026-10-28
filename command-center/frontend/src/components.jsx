import React, { useEffect, useState } from 'react'
import { api } from './api.js'

export function useLoad(path, deps = []) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let live = true
    api.get(path).then((d) => live && setData(d)).catch((e) => live && setErr(e.message))
    return () => { live = false }
  }, [path, tick, ...deps])  // eslint-disable-line
  return [data, () => setTick((t) => t + 1), err]
}

export const healthClass = (h) => (h === 'on-track' ? 'ok' : h === 'at-risk' ? 'warn' : h === 'blocked' || h === 'off-track' ? 'bad' : '')

export function Pill({ kind, children }) {
  return <span className={'pill ' + (kind || '')}>{children}</span>
}

export function Markdown({ text }) {
  // Minimal renderer for the agents' markdown: headings, bullets, bold, tables.
  if (!text) return null
  const lines = text.split('\n')
  const out = []
  let table = []
  const flush = () => {
    if (!table.length) return
    const rows = table.filter((r) => !/^\|\s*-/.test(r)).map((r) => r.split('|').slice(1, -1).map((c) => c.trim()))
    out.push(
      <table key={out.length}><tbody>
        {rows.map((r, i) => <tr key={i}>{r.map((c, j) => (i === 0 ? <th key={j}>{c}</th> : <td key={j}>{c}</td>))}</tr>)}
      </tbody></table>,
    )
    table = []
  }
  lines.forEach((l, i) => {
    if (l.startsWith('|')) { table.push(l); return }
    flush()
    if (l.startsWith('# ')) out.push(<h1 key={i}>{l.slice(2)}</h1>)
    else if (l.startsWith('## ')) out.push(<h2 key={i}>{l.slice(3)}</h2>)
    else if (l.startsWith('- ')) out.push(<div key={i}>• {bold(l.slice(2))}</div>)
    else if (l.trim() === '') out.push(<div key={i} style={{ height: 6 }} />)
    else out.push(<div key={i}>{bold(l)}</div>)
  })
  flush()
  return <div className="md">{out}</div>
}

function bold(s) {
  const parts = s.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, i) => (p.startsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p))
}

export function Modal({ title, onClose, children }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row spread" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="btn sm" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Field({ label, children }) {
  return <div className="field"><label>{label}</label>{children}</div>
}

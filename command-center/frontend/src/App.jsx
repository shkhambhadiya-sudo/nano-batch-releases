import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Home from './screens/Home.jsx'
import Capture from './screens/Capture.jsx'
import MapView from './screens/MapView.jsx'
import Approvals from './screens/Approvals.jsx'
import People from './screens/People.jsx'
import Blockers from './screens/Blockers.jsx'
import Ideas from './screens/Ideas.jsx'
import Goals from './screens/Goals.jsx'
import Health from './screens/Health.jsx'

const SCREENS = [
  ['home', 'Command Center', Home],
  ['capture', 'Capture', Capture],
  ['map', 'Map', MapView],
  ['approvals', 'Approvals', Approvals],
  ['blockers', 'Blockers', Blockers],
  ['people', 'People', People],
  ['ideas', 'Ideas', Ideas],
  ['goals', 'Goals', Goals],
  ['health', 'System', Health],
]

export default function App() {
  const [screen, setScreen] = useState(() => location.hash.replace('#', '') || 'home')
  const [counts, setCounts] = useState({})

  const refreshCounts = useCallback(() => {
    api.get('/overview').then((o) => setCounts(o.counts)).catch(() => {})
  }, [])

  useEffect(() => {
    refreshCounts()
    const t = setInterval(refreshCounts, 60000)
    return () => clearInterval(t)
  }, [refreshCounts])

  useEffect(() => { if (location.hash.replace('#', '') !== screen) location.hash = screen }, [screen])
  useEffect(() => {
    const onHash = () => setScreen(location.hash.replace('#', '') || 'home')
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [])

  const badges = {
    approvals: (counts.pending_suggestions || 0) + (counts.open_flags || 0),
    blockers: counts.open_blockers,
    ideas: counts.ideas_backlog,
  }
  const Screen = SCREENS.find((s) => s[0] === screen)?.[2] || Home

  return (
    <div className="app">
      <nav className="nav">
        <h1>Command Center</h1>
        {SCREENS.map(([key, label]) => (
          <button key={key} className={screen === key ? 'active' : ''} onClick={() => setScreen(key)}>
            <span>{label}</span>
            {badges[key] ? <span className={'count' + (key === 'approvals' ? ' hot' : '')}>{badges[key]}</span> : null}
          </button>
        ))}
      </nav>
      <main className="main">
        <Screen go={setScreen} refresh={refreshCounts} />
      </main>
    </div>
  )
}

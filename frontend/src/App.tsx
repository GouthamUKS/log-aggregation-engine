import { useState } from 'react'
import Overview from './pages/Overview'
import Timeseries from './pages/Timeseries'
import LogExplorer from './pages/LogExplorer'
import { useHealth } from './hooks/useApi'

const TABS = ['Overview', 'Timeseries', 'Log Explorer'] as const
type Tab = typeof TABS[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('Overview')
  const { data: health } = useHealth()

  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-border bg-panel">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-slate-100 font-semibold tracking-tight">Log Aggregation Engine</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${health?.status === 'ok' ? 'bg-emerald-900 text-emerald-300' : 'bg-red-900 text-red-300'}`}>
              {health?.status ?? 'connecting...'}
            </span>
          </div>
          <div className="text-xs text-slate-500">
            {health ? `hot: ${health.hot_count.toLocaleString()} | warm: ${health.warm_count.toLocaleString()}` : ''}
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-4 flex gap-0">
          {TABS.map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm border-b-2 transition-colors ${
                tab === t
                  ? 'border-sky-500 text-sky-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {tab === 'Overview' && <Overview />}
        {tab === 'Timeseries' && <Timeseries />}
        {tab === 'Log Explorer' && <LogExplorer />}
      </main>
    </div>
  )
}

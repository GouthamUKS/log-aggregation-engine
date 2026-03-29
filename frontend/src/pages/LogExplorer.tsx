import { useState } from 'react'
import { useLogs } from '../hooks/useApi'
import LevelBadge from '../components/LevelBadge'
import { format } from 'date-fns'

const SOURCES = ['', 'api-service', 'worker-service', 'cache-service', 'auth-service', 'db-service']
const LEVELS = ['', 'INFO', 'WARN', 'ERROR', 'FATAL', 'DEBUG']

export default function LogExplorer() {
  const [source, setSource] = useState('')
  const [level, setLevel] = useState('')
  const [limit, setLimit] = useState(100)
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data: logs, isLoading, refetch } = useLogs({
    source: source || undefined,
    level: level || undefined,
    limit,
  })

  function downloadCSV() {
    if (!logs?.length) return
    const header = 'timestamp,source,level,message\n'
    const rows = logs.map(l =>
      `"${l.timestamp}","${l.source}","${l.level}","${l.message.replace(/"/g, '""')}"`
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `logs_export_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400">Source</label>
          <select
            value={source}
            onChange={e => setSource(e.target.value)}
            className="bg-panel border border-border rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
          >
            {SOURCES.map(s => <option key={s} value={s}>{s || 'All sources'}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400">Level</label>
          <select
            value={level}
            onChange={e => setLevel(e.target.value)}
            className="bg-panel border border-border rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
          >
            {LEVELS.map(l => <option key={l} value={l}>{l || 'All levels'}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400">Limit</label>
          <select
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            className="bg-panel border border-border rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
          >
            {[50, 100, 250, 500, 1000].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <button
          onClick={() => refetch()}
          className="px-4 py-1.5 bg-sky-700 hover:bg-sky-600 rounded text-sm text-white border border-sky-500 transition-colors"
        >
          Refresh
        </button>
        <button
          onClick={downloadCSV}
          className="px-4 py-1.5 bg-panel hover:bg-slate-700 rounded text-sm text-slate-300 border border-border transition-colors"
        >
          Export CSV
        </button>
      </div>

      <div className="text-xs text-slate-500">
        {isLoading ? 'Loading...' : `${logs?.length ?? 0} results`}
      </div>

      <div className="bg-panel border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-slate-400 uppercase tracking-wider">
              <th className="px-4 py-3 text-left w-44">Timestamp</th>
              <th className="px-4 py-3 text-left w-36">Source</th>
              <th className="px-4 py-3 text-left w-20">Level</th>
              <th className="px-4 py-3 text-left">Message</th>
            </tr>
          </thead>
          <tbody>
            {(logs ?? []).map((log, i) => (
              <>
                <tr
                  key={i}
                  onClick={() => setExpanded(expanded === i ? null : i)}
                  className="border-b border-border hover:bg-slate-800 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-2 text-slate-400 text-xs whitespace-nowrap">
                    {format(new Date(log.timestamp), 'MM-dd HH:mm:ss')}
                  </td>
                  <td className="px-4 py-2 text-slate-300 text-xs">{log.source}</td>
                  <td className="px-4 py-2">
                    <LevelBadge level={log.level} />
                  </td>
                  <td className="px-4 py-2 text-slate-200 text-xs truncate max-w-xs">{log.message}</td>
                </tr>
                {expanded === i && (
                  <tr key={`${i}-exp`} className="border-b border-border bg-slate-900">
                    <td colSpan={4} className="px-4 py-3">
                      <div className="space-y-1 text-xs">
                        <div><span className="text-slate-500">timestamp: </span><span className="text-slate-200">{log.timestamp}</span></div>
                        <div><span className="text-slate-500">source: </span><span className="text-slate-200">{log.source}</span></div>
                        <div><span className="text-slate-500">level: </span><LevelBadge level={log.level} /></div>
                        <div><span className="text-slate-500">message: </span><span className="text-slate-200">{log.message}</span></div>
                        {log.metadata && (
                          <div>
                            <span className="text-slate-500">metadata: </span>
                            <pre className="text-slate-300 mt-1 bg-surface rounded p-2 overflow-auto">
                              {typeof log.metadata === 'string' ? log.metadata : JSON.stringify(log.metadata, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
            {!isLoading && !logs?.length && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">No logs found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useTimeseries } from '../hooks/useApi'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid,
} from 'recharts'
import { format, subHours, subDays } from 'date-fns'

const COLORS = ['#38bdf8', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#fb923c']

const SOURCE_LIST = ['api-service', 'worker-service', 'cache-service', 'auth-service', 'db-service']

function pivotTimeseries(rows: any[], dimKey: string): any[] {
  const map: Record<string, any> = {}
  for (const row of rows) {
    const ts = row.timestamp as string
    if (!map[ts]) map[ts] = { ts }
    map[ts][row[dimKey] ?? 'unknown'] = row.count
  }
  return Object.values(map).sort((a, b) => (a.ts as string).localeCompare(b.ts as string))
}

export default function Timeseries() {
  const [range, setRange] = useState<'1h' | '6h' | '24h' | '7d'>('6h')
  const [groupBy, setGroupBy] = useState<'source' | 'level'>('source')
  const [gran, setGran] = useState<'1h' | '1d'>('1h')

  const now = new Date()
  const startMap = {
    '1h': subHours(now, 1).toISOString(),
    '6h': subHours(now, 6).toISOString(),
    '24h': subHours(now, 24).toISOString(),
    '7d': subDays(now, 7).toISOString(),
  }
  const start = startMap[range]

  const { data, isLoading } = useTimeseries(groupBy, gran, start)
  const pivoted = pivotTimeseries(data ?? [], groupBy)
  const keys = groupBy === 'source' ? SOURCE_LIST : ['INFO', 'WARN', 'ERROR', 'FATAL']

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1">
          {(['1h', '6h', '24h', '7d'] as const).map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 text-xs rounded border ${range === r ? 'bg-sky-700 border-sky-500 text-white' : 'border-border text-slate-400 hover:border-slate-500'}`}
            >
              {r}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['source', 'level'] as const).map(g => (
            <button
              key={g}
              onClick={() => setGroupBy(g)}
              className={`px-3 py-1 text-xs rounded border ${groupBy === g ? 'bg-emerald-800 border-emerald-500 text-white' : 'border-border text-slate-400 hover:border-slate-500'}`}
            >
              by {g}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['1h', '1d'] as const).map(g => (
            <button
              key={g}
              onClick={() => setGran(g)}
              className={`px-3 py-1 text-xs rounded border ${gran === g ? 'bg-purple-800 border-purple-500 text-white' : 'border-border text-slate-400 hover:border-slate-500'}`}
            >
              {g} grain
            </button>
          ))}
        </div>
      </div>

      <div className="bg-panel border border-border rounded-lg p-4">
        <h3 className="text-sm text-slate-400 mb-4 uppercase tracking-wider">
          Log Volume — by {groupBy} ({range})
        </h3>
        {isLoading ? (
          <div className="flex items-center justify-center h-64 text-slate-400">Loading...</div>
        ) : (
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={pivoted} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="ts"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickFormatter={(v) => format(new Date(v), gran === '1h' ? 'HH:mm' : 'MMM dd')}
              />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
                labelFormatter={(v) => format(new Date(v), 'yyyy-MM-dd HH:mm')}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
              {keys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={COLORS[i % COLORS.length]}
                  dot={false}
                  strokeWidth={2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

import StatCard from '../components/StatCard'
import { useHealth, useAggregation } from '../hooks/useApi'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const SOURCE_COLORS = ['#38bdf8', '#34d399', '#fbbf24', '#f87171', '#a78bfa']

const LEVEL_COLORS: Record<string, string> = {
  INFO: '#38bdf8',
  WARN: '#fbbf24',
  ERROR: '#f87171',
  FATAL: '#a78bfa',
  DEBUG: '#64748b',
}

export default function Overview() {
  const { data: health, isLoading: healthLoading } = useHealth()
  const { data: bySource } = useAggregation('source')
  const { data: byLevel } = useAggregation('level')

  if (healthLoading) {
    return <div className="flex items-center justify-center h-64 text-slate-400">Loading...</div>
  }

  const totalLogs = (health?.hot_count ?? 0) + (health?.warm_count ?? 0)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Logs"
          value={totalLogs.toLocaleString()}
          sub={`hot: ${(health?.hot_count ?? 0).toLocaleString()} / warm: ${(health?.warm_count ?? 0).toLocaleString()}`}
          accent="blue"
        />
        <StatCard
          label="p50 Latency"
          value={`${health?.pipeline.p50_latency_ms ?? 0} ms`}
          sub="pipeline ingest"
          accent="green"
        />
        <StatCard
          label="Buffer Utilization"
          value={`${health?.buffer.utilization_pct ?? 0}%`}
          sub={`${health?.buffer.buffer_size ?? 0} / 10,000 msgs`}
          accent={
            (health?.buffer.utilization_pct ?? 0) > 80
              ? 'red'
              : (health?.buffer.utilization_pct ?? 0) > 50
              ? 'yellow'
              : 'green'
          }
        />
        <StatCard
          label="Dedup Rate"
          value={`${health?.pipeline.dedup_rate_pct ?? 0}%`}
          sub={`${health?.pipeline.deduplicated ?? 0} dupes dropped`}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          label="p95 Latency"
          value={`${health?.pipeline.p95_latency_ms ?? 0} ms`}
          accent={
            (health?.pipeline.p95_latency_ms ?? 0) > 100 ? 'red'
            : (health?.pipeline.p95_latency_ms ?? 0) > 50 ? 'yellow'
            : 'green'
          }
        />
        <StatCard
          label="p99 Latency"
          value={`${health?.pipeline.p99_latency_ms ?? 0} ms`}
          accent={
            (health?.pipeline.p99_latency_ms ?? 0) > 200 ? 'red'
            : (health?.pipeline.p99_latency_ms ?? 0) > 100 ? 'yellow'
            : 'green'
          }
        />
        <StatCard
          label="Cold Storage"
          value={`${health?.cold_size_gb.toFixed(3) ?? 0} GB`}
          sub={`${health?.cold_files ?? 0} parquet files`}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-panel border border-border rounded-lg p-4">
          <h3 className="text-sm text-slate-400 mb-4 uppercase tracking-wider">Logs by Source</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={bySource ?? []} margin={{ top: 0, right: 10, left: 0, bottom: 40 }}>
              <XAxis
                dataKey="source"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                angle={-30}
                textAnchor="end"
                interval={0}
              />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(bySource ?? []).map((_, i) => (
                  <Cell key={i} fill={SOURCE_COLORS[i % SOURCE_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-panel border border-border rounded-lg p-4">
          <h3 className="text-sm text-slate-400 mb-4 uppercase tracking-wider">Logs by Level</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={byLevel ?? []} margin={{ top: 0, right: 10, left: 0, bottom: 10 }}>
              <XAxis dataKey="level" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(byLevel ?? []).map((row, i) => (
                  <Cell key={i} fill={LEVEL_COLORS[row.level ?? ''] ?? '#64748b'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

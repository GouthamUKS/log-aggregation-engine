import { useQuery } from '@tanstack/react-query'

const BASE = ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => get<HealthData>('/health'),
    refetchInterval: 5000,
  })
}

export function useAggregation(groupBy: string, startTime?: string, endTime?: string) {
  const params = new URLSearchParams({ group_by: groupBy })
  if (startTime) params.set('start_time', startTime)
  if (endTime) params.set('end_time', endTime)
  return useQuery({
    queryKey: ['aggregation', groupBy, startTime, endTime],
    queryFn: () => get<AggRow[]>(`/query/aggregation?${params}`),
    refetchInterval: 15000,
  })
}

export function useTimeseries(groupBy: string, granularity: string, startTime?: string, endTime?: string) {
  const params = new URLSearchParams({ group_by: groupBy, granularity })
  if (startTime) params.set('start_time', startTime)
  if (endTime) params.set('end_time', endTime)
  return useQuery({
    queryKey: ['timeseries', groupBy, granularity, startTime, endTime],
    queryFn: () => get<TimeseriesRow[]>(`/query/timeseries?${params}`),
    refetchInterval: 15000,
  })
}

export function useLogs(params: LogQueryParams) {
  const qp = new URLSearchParams()
  if (params.source) qp.set('source', params.source)
  if (params.level) qp.set('level', params.level)
  if (params.startTime) qp.set('start_time', params.startTime)
  if (params.endTime) qp.set('end_time', params.endTime)
  qp.set('limit', String(params.limit ?? 100))
  return useQuery({
    queryKey: ['logs', params],
    queryFn: () => get<LogEntry[]>(`/query/logs?${qp}`),
    refetchInterval: 10000,
  })
}

export interface HealthData {
  status: string
  hot_count: number
  warm_count: number
  cold_files: number
  cold_size_gb: number
  buffer: {
    buffer_size: number
    total_received: number
    total_dropped: number
    utilization_pct: number
  }
  pipeline: {
    processed: number
    deduplicated: number
    dedup_rate_pct: number
    p50_latency_ms: number
    p95_latency_ms: number
    p99_latency_ms: number
  }
}

export interface AggRow {
  source?: string
  level?: string
  count: number
}

export interface TimeseriesRow {
  timestamp: string
  source?: string
  level?: string
  count: number
}

export interface LogEntry {
  timestamp: string
  source: string
  level: string
  message: string
  metadata: string | null
}

export interface LogQueryParams {
  source?: string
  level?: string
  startTime?: string
  endTime?: string
  limit?: number
}

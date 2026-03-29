interface Props {
  label: string
  value: string | number
  sub?: string
  accent?: 'green' | 'yellow' | 'red' | 'blue' | 'default'
}

const accents = {
  green: 'text-emerald-400',
  yellow: 'text-yellow-400',
  red: 'text-red-400',
  blue: 'text-sky-400',
  default: 'text-slate-100',
}

export default function StatCard({ label, value, sub, accent = 'default' }: Props) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4 flex flex-col gap-1">
      <span className="text-xs text-slate-400 uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-semibold ${accents[accent]}`}>{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}

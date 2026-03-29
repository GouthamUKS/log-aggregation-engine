const styles: Record<string, string> = {
  INFO: 'bg-sky-900 text-sky-300',
  WARN: 'bg-yellow-900 text-yellow-300',
  ERROR: 'bg-red-900 text-red-300',
  FATAL: 'bg-purple-900 text-purple-300',
  DEBUG: 'bg-slate-700 text-slate-300',
}

export default function LevelBadge({ level }: { level: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${styles[level] ?? styles.DEBUG}`}>
      {level}
    </span>
  )
}

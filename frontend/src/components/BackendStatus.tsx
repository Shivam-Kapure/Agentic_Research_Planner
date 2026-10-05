import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../lib/api'
import { HEALTH_QUERY_KEY } from '../lib/queryClient'

/**
 * Shows whether the API is reachable. The free Render tier sleeps when idle, so the
 * first request can take ~30-60 s; the retry policy for ['health'] lives in lib/queryClient.
 */
export function BackendStatus() {
  const { data, isPending, isError } = useQuery({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: getHealth,
    refetchInterval: 60_000,
  })

  if (isPending) {
    return <StatusPill tone="amber" label="Waking up the server… (can take up to a minute)" />
  }
  if (isError) {
    return <StatusPill tone="red" label="Server unreachable — please try again shortly" />
  }
  return <StatusPill tone="green" label={`Server online · v${data.version}`} />
}

const tones = {
  green: 'bg-emerald-100 text-emerald-800',
  amber: 'bg-amber-100 text-amber-800',
  red: 'bg-red-100 text-red-800',
} as const

function StatusPill({ tone, label }: { tone: keyof typeof tones; label: string }) {
  return (
    <span
      role="status"
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${tones[tone]}`}
    >
      <span className="h-2 w-2 rounded-full bg-current" aria-hidden />
      {label}
    </span>
  )
}

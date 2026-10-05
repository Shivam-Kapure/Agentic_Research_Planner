import { QueryClient } from '@tanstack/react-query'

export const HEALTH_QUERY_KEY = ['health'] as const

export function createQueryClient(): QueryClient {
  const client = new QueryClient()
  // A sleeping free-tier Render instance needs ~30-60 s to wake: keep retrying for ~30 s.
  client.setQueryDefaults(HEALTH_QUERY_KEY, { retry: 6, retryDelay: 5000 })
  return client
}

import { describe, expect, it } from 'vitest'
import { createQueryClient, HEALTH_QUERY_KEY } from './queryClient'

describe('createQueryClient', () => {
  it('retries the health check long enough to wake a sleeping server', () => {
    const defaults = createQueryClient().getQueryDefaults(HEALTH_QUERY_KEY)

    expect(defaults.retry).toBe(6)
    expect(defaults.retryDelay).toBe(5000)
  })
})

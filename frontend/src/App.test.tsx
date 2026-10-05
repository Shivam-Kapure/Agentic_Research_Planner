import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { App } from './App'

function renderAt(path: string) {
  // No retries in tests, so failures surface immediately
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mockFetch(response: Partial<Response> | Error) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() =>
      response instanceof Error ? Promise.reject(response) : Promise.resolve(response as Response),
    )
}

describe('App', () => {
  it('renders the home page with all five agents', () => {
    mockFetch(new Error('offline'))
    renderAt('/')

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/literature reviews/i)
    for (const agent of ['Research Planner', 'Literature Search', 'Document Analysis', 'Evidence Synthesis', 'Review Writer']) {
      expect(screen.getByRole('heading', { name: agent })).toBeInTheDocument()
    }
  })

  it('shows the backend as online when /health responds', async () => {
    const fetchSpy = mockFetch({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'ok', version: '0.1.0', env: 'test' }),
    })
    renderAt('/')

    expect(await screen.findByText(/Server online · v0\.1\.0/)).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledWith(expect.stringMatching(/\/health$/), undefined)
  })

  it('shows the backend as unreachable when /health fails', async () => {
    mockFetch({ ok: false, status: 503, json: () => Promise.resolve({}) })
    renderAt('/')

    expect(await screen.findByText(/Server unreachable/)).toBeInTheDocument()
  })

  it('renders a not-found page for unknown routes', () => {
    mockFetch(new Error('offline'))
    renderAt('/does-not-exist')

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

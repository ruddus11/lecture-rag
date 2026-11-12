import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { DocumentsPage } from '../src/features/upload/DocumentsPage'
import { AuthContext, type AuthState } from '../src/app/useAuth'
import { ApiError } from '../src/shared/api/client'

it('업로드 응답 유실 후 재시도는 같은 Idempotency-Key를 사용한다', async () => {
  const keys: string[] = []
  const request = vi.fn(async (path: string, opts?: { method?: string; headers?: Record<string, string> }) => {
    if (opts?.method === 'POST') {
      keys.push(opts.headers!['Idempotency-Key'])
      throw new ApiError(0, 'network_error', 'lost', 'RID', true)
    }
    if (path === '/collections') return { items: [{ id: 'c', name: '자료' }] }
    return { items: [] }
  })
  const auth = { token: 't', user: { role: 'admin' }, request } as unknown as AuthState
  const { container } = render(<AuthContext.Provider value={auth}><QueryClientProvider client={new QueryClient()}>
    <MemoryRouter><DocumentsPage /></MemoryRouter>
  </QueryClientProvider></AuthContext.Provider>)
  await screen.findByRole('button', { name: '업로드' })
  await userEvent.upload(container.querySelector('input[type=file]')!, new File(['%PDF-'], 'test.pdf', { type: 'application/pdf' }))
  await userEvent.click(screen.getByRole('button', { name: '업로드' }))
  await userEvent.click(await screen.findByRole('button', { name: '다시 시도' }))
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
})

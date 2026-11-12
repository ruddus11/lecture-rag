import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import PdfPage from '../src/features/sources/PdfPage'
import { AuthContext, type AuthState } from '../src/app/useAuth'

const failure = vi.hoisted(() => ({ status: 401 }))
afterEach(() => { vi.unstubAllGlobals(); failure.status = 401 })

vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ onLoadError }: { onLoadError: (e: Error) => void }) => (
    <button onClick={() => onLoadError(Object.assign(new Error('Unauthorized'), { status: failure.status }))}>expire</button>
  ),
  Page: () => null,
}))

it('PDF 요청이 401이면 인증을 해제한다', async () => {
  const logout = vi.fn()
  const auth = { token: 'expired', logout } as unknown as AuthState
  render(<AuthContext.Provider value={auth}><PdfPage documentId="d1" page={1} onPage={() => {}} /></AuthContext.Provider>)
  await userEvent.click(screen.getByRole('button', { name: 'expire' }))
  expect(logout).toHaveBeenCalledOnce()
})

it('PDF 서비스 오류에서 요청 ID와 재시도를 제공한다', async () => {
  failure.status = 503
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ error: {
    code: 'search_unavailable', message: 'offline', request_id: 'PDF-RID', retryable: true,
  } }, { status: 503 })))
  const auth = { token: 't', logout: vi.fn() } as unknown as AuthState
  render(<AuthContext.Provider value={auth}><PdfPage documentId="d1" page={1} onPage={() => {}} /></AuthContext.Provider>)
  await userEvent.click(screen.getByRole('button', { name: 'expire' }))
  expect(await screen.findByText('PDF-RID')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '다시 시도' }))
  expect(screen.getByRole('button', { name: 'expire' })).toBeInTheDocument()
})

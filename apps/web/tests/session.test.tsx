import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { App } from '../src/app/App'

afterEach(() => vi.unstubAllGlobals())

it('계정을 바꾸면 이전 기관 컬렉션을 재사용하지 않는다', async () => {
  window.history.replaceState({}, '', '/login')
  let account = 'a_admin'
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith('/auth/login')) {
      account = JSON.parse(options?.body as string).username
      return Response.json({ access_token: account, user: { username: account, role: 'admin', institution_id: account } })
    }
    if (url.includes('/documents') && account === 'b_admin') return new Promise<Response>(() => {})
    if (url.includes('/documents')) return Response.json({ items: [{ id: account, filename: `${account}.pdf`, status: 'ready', page_count: 1, chunk_count: 1 }] })
    return Response.json({ items: [{ id: 'shared', name: `${account} 자료`, search_profile: { mode: 'hybrid' } }] })
  }))
  render(<App />)
  const login = async (name: string) => {
    await userEvent.type(screen.getByLabelText('아이디'), name)
    await userEvent.type(screen.getByLabelText('비밀번호'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: '로그인' }))
  }
  await login('a_admin')
  await screen.findByText('a_admin 자료')
  await userEvent.click(screen.getByRole('link', { name: '자료' }))
  await screen.findByText('a_admin.pdf')
  await userEvent.click(screen.getByRole('button', { name: '로그아웃' }))
  await login('b_admin')
  await screen.findByText('b_admin 자료')
  await userEvent.click(screen.getByRole('link', { name: '자료' }))
  expect(screen.queryByText('a_admin.pdf')).toBeNull()
  await waitFor(() => expect(screen.queryByText('a_admin 자료')).toBeNull())
})

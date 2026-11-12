import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { apiRequest, type RequestOptions } from '../shared/api/client'
import type { LoginResponse, UserOut } from '../shared/api/types'
import { AuthContext } from './useAuth'

// 토큰은 메모리(React 상태)에만 둔다. localStorage 에 저장하지 않으므로 새로고침하면 다시 로그인한다 (설계서 13장).
export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<UserOut | null>(null)

  const login = useCallback(async (username: string, password: string) => {
    const res = await apiRequest<LoginResponse>('/auth/login', { method: 'POST', json: { username, password } })
    setToken(res.access_token)
    setUser(res.user)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const request = useCallback(
    <T,>(path: string, opts: Omit<RequestOptions, 'token'> = {}) => apiRequest<T>(path, { ...opts, token }),
    [token],
  )

  const value = useMemo(() => ({ token, user, login, logout, request }), [token, user, login, logout, request])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

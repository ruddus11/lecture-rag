import { createContext, useContext } from 'react'
import type { RequestOptions } from '../shared/api/client'
import type { UserOut } from '../shared/api/types'

export interface AuthState {
  token: string | null
  user: UserOut | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  request: <T>(path: string, opts?: Omit<RequestOptions, 'token'>) => Promise<T>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { LoginPage } from '../features/auth/LoginPage'
import { DocumentsPage } from '../features/upload/DocumentsPage'
import { SearchPage } from '../features/search/SearchPage'
import { ApiError } from '../shared/api/client'
import { AuthProvider } from './auth'
import { useAuth } from './useAuth'
import styles from './App.module.css'
import './global.css'

const ViewerPage = lazy(() => import('../features/sources/ViewerPage'))

function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <span className={styles.brand}>강의자료 검색</span>
        <nav className={styles.nav}>
          <NavLink to="/" end>
            질문
          </NavLink>
          <NavLink to="/documents">자료</NavLink>
        </nav>
        <span className={styles.user}>
          {user?.username} · {user?.institution_id} · {user?.role === 'admin' ? '관리자' : '학생'}
          <button type="button" onClick={logout}>
            로그아웃
          </button>
        </span>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  )
}

function Protected({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return <Shell>{children}</Shell>
}

function SessionRoutes() {
  const { logout } = useAuth()
  // 401 이면 토큰을 버려 로그인 화면으로 보낸다.
  const [client] = useState(() => {
    const on401 = (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) logout()
    }
    return new QueryClient({
      queryCache: new QueryCache({ onError: on401 }),
      mutationCache: new MutationCache({ onError: on401 }),
      defaultOptions: {
        queries: { retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 1, refetchOnWindowFocus: false },
      },
    })
  })
  return (
    <QueryClientProvider client={client}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <Protected>
              <SearchPage />
            </Protected>
          }
        />
        <Route
          path="/documents"
          element={
            <Protected>
              <DocumentsPage />
            </Protected>
          }
        />
        <Route
          path="/documents/:id/view"
          element={
            <Protected>
              <Suspense fallback={<p>뷰어를 불러오는 중…</p>}>
                <ViewerPage />
              </Suspense>
            </Protected>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </QueryClientProvider>
  )
}

function AppRoutes() {
  const { token } = useAuth()
  // 인증 세션마다 캐시를 새로 만들어 이전 계정의 자료가 남지 않게 한다.
  return <SessionRoutes key={token ?? 'anonymous'} />
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

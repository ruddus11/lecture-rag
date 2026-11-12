import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../app/useAuth'
import { ErrorPanel } from '../../shared/ui/ErrorPanel'
import styles from './LoginPage.module.css'

export function LoginPage() {
  const { token, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)

  if (token) return <Navigate to="/" replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(username, password)
    } catch (err) {
      setError(err)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={onSubmit}>
        <h1>강의자료 검색</h1>
        <p className={styles.hint}>데모 계정으로 로그인합니다. 계정은 README에 있습니다.</p>
        <label>
          아이디
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required minLength={3} maxLength={32} />
        </label>
        <label>
          비밀번호
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required minLength={8} maxLength={128} />
        </label>
        {error != null && <ErrorPanel error={error} />}
        <button type="submit" disabled={pending}>
          {pending ? '로그인 중…' : '로그인'}
        </button>
      </form>
    </div>
  )
}

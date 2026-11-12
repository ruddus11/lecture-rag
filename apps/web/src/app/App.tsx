import { useEffect, useState } from 'react'

// M1 골격: 프록시를 통해 API live 체크만 호출한다. M7에서 실제 화면으로 교체.
export function App() {
  const [status, setStatus] = useState('확인 중')
  useEffect(() => {
    fetch('/api/v1/health/live')
      .then((r) => r.json())
      .then((b: { status: string }) => setStatus(b.status))
      .catch(() => setStatus('연결 실패'))
  }, [])
  return (
    <main>
      <h1>강의자료 검색</h1>
      <p>API 상태: {status}</p>
    </main>
  )
}

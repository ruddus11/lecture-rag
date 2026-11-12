import { ApiError, errorMessage } from '../api/client'
import styles from './ui.module.css'

interface Props {
  error: unknown
  onRetry?: () => void
}

// 코드별 메시지, request_id, retryable 이면 재시도 버튼 (설계서 14장).
export function ErrorPanel({ error, onRetry }: Props) {
  const api = error instanceof ApiError ? error : null
  return (
    <div role="alert" className={styles.error}>
      <p className={styles.errorTitle}>{errorMessage(error)}</p>
      {api && (
        <p className={styles.meta}>
          코드 <code>{api.code}</code>
          {api.requestId && (
            <>
              {' '}· 요청 ID <code>{api.requestId}</code>
            </>
          )}
        </p>
      )}
      {api?.retryable && onRetry && (
        <button type="button" className={styles.secondary} onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  )
}

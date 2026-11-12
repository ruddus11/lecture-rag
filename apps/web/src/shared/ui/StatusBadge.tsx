import type { DocumentStatus, JobStatus } from '../api/types'
import styles from './ui.module.css'

const LABELS: Record<DocumentStatus | JobStatus, string> = {
  queued: '대기',
  processing: '처리 중',
  ready: '사용 가능',
  failed: '실패',
  deleting: '삭제 중',
  deleted: '삭제됨',
  succeeded: '완료',
}

const STAGES: Record<string, string> = {
  received: '접수',
  parsing: '텍스트 추출',
  chunking: '청크 분할',
  embedding: '임베딩',
  indexing_vector: '벡터 색인',
  indexing_keyword: '키워드 색인',
  activating: '활성화',
  removing_indexes: '색인 삭제',
  removing_file: '파일 삭제',
}

interface Props {
  status: DocumentStatus | JobStatus
  stage?: string | null
  errorCode?: string | null
}

export function StatusBadge({ status, stage, errorCode }: Props) {
  const tone = status === 'ready' || status === 'succeeded' ? 'ok' : status === 'failed' ? 'bad' : 'wait'
  return (
    <span className={`${styles.badge} ${styles[tone]}`} data-status={status}>
      {LABELS[status] ?? status}
      {status === 'processing' && stage ? ` · ${STAGES[stage] ?? stage}` : ''}
      {status === 'failed' && errorCode ? ` · ${errorCode}` : ''}
    </span>
  )
}

import { lazy, Suspense, useEffect, useState } from 'react'
import type { SourceRef } from './SourceCard'
import styles from './sources.module.css'

const PdfPage = lazy(() => import('./PdfPage'))

export function ViewerModal({ source, onClose }: { source: SourceRef; onClose: () => void }) {
  const [page, setPage] = useState(source.page)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label={source.title} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHead}>
          <strong>{source.title}</strong>
          <button type="button" onClick={onClose} aria-label="닫기">
            닫기
          </button>
        </div>
        <Suspense fallback={<p className={styles.muted}>뷰어를 불러오는 중…</p>}>
          <PdfPage documentId={source.documentId} page={page} onPage={setPage} />
        </Suspense>
      </div>
    </div>
  )
}

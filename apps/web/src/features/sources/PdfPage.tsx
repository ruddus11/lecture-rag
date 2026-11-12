import { useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import { useAuth } from '../../app/useAuth'
import { ApiError, toApiError, API_BASE } from '../../shared/api/client'
import { ErrorPanel } from '../../shared/ui/ErrorPanel'
import styles from './sources.module.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

interface Props {
  documentId: string
  page: number
  onPage: (page: number) => void
}

// 한 페이지만 렌더한다. 파일은 Authorization 헤더로 Range 요청한다 (설계서 14장).
export default function PdfPage({ documentId, page, onPage }: Props) {
  const { token, logout } = useAuth()
  const [pages, setPages] = useState<number | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)
  const [file] = useState(() => ({
    url: `${API_BASE}/documents/${documentId}/file`,
    httpHeaders: { Authorization: `Bearer ${token}` },
  }))
  return (
    <div className={styles.viewer}>
      <div className={styles.pager}>
        <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1}>
          이전
        </button>
        <span>
          {page} / {pages ?? '?'}쪽
        </span>
        <button type="button" onClick={() => onPage(page + 1)} disabled={pages != null && page >= pages}>
          다음
        </button>
      </div>
      {error ? (
        <ErrorPanel error={error} onRetry={() => { setError(null); setAttempt((n) => n + 1) }} />
      ) : (
        <Document
          key={attempt}
          file={file}
          onLoadSuccess={(d) => setPages(d.numPages)}
          onLoadError={async (e) => {
            if ('status' in e && e.status === 401) { logout(); return }
            // pdf.js 오류에는 표준 오류 본문이 없어 작은 Range 요청으로 요청 ID를 확인한다.
            try {
              const response = await fetch(file.url, { headers: { ...file.httpHeaders, Range: 'bytes=0-0' } })
              if (response.status === 401) { logout(); return }
              setError(response.ok
                ? new ApiError(0, 'pdf_error', e.message, null, true)
                : await toApiError(response))
            } catch {
              setError(new ApiError(0, 'network_error', 'PDF에 연결할 수 없습니다.', null, true))
            }
          }}
          loading={<p className={styles.muted}>PDF를 불러오는 중…</p>}
        >
          <Page pageNumber={page} width={760} />
        </Document>
      )}
    </div>
  )
}

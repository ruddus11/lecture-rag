import { useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import { useAuth } from '../../app/useAuth'
import { API_BASE } from '../../shared/api/client'
import styles from './sources.module.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

interface Props {
  documentId: string
  page: number
  onPage: (page: number) => void
}

// 한 페이지만 렌더한다. 파일은 Authorization 헤더로 Range 요청한다 (설계서 14장).
export default function PdfPage({ documentId, page, onPage }: Props) {
  const { token } = useAuth()
  const [pages, setPages] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
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
        <p role="alert" className={styles.notice}>
          PDF를 열지 못했습니다: {error}
        </p>
      ) : (
        <Document
          file={file}
          onLoadSuccess={(d) => setPages(d.numPages)}
          onLoadError={(e) => setError(e.message)}
          loading={<p className={styles.muted}>PDF를 불러오는 중…</p>}
        >
          <Page pageNumber={page} width={760} />
        </Document>
      )}
    </div>
  )
}

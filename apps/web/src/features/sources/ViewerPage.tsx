import { lazy, Suspense } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import styles from './sources.module.css'

const PdfPage = lazy(() => import('./PdfPage'))

export default function ViewerPage() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page')) || 1)
  return (
    <section>
      <p>
        <Link to="/documents">← 자료 목록</Link>
      </p>
      <Suspense fallback={<p className={styles.muted}>뷰어를 불러오는 중…</p>}>
        <PdfPage documentId={id} page={page} onPage={(p) => setParams({ page: String(p) })} />
      </Suspense>
    </section>
  )
}

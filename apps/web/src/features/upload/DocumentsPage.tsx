import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../app/useAuth'
import { CollectionPicker } from '../collections/CollectionPicker'
import { useCollections } from '../collections/useCollections'
import type { DocumentOut, JobAccepted, JobOut, UploadAccepted } from '../../shared/api/types'
import { ErrorPanel } from '../../shared/ui/ErrorPanel'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import styles from './DocumentsPage.module.css'

const MAX_MB = 20
const TERMINAL = new Set(['succeeded', 'failed'])

// 작업 상태를 2초 간격으로 확인하고 종료 상태에서 멈춘다 (설계서 14장).
export function JobWatcher({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const { request } = useAuth()
  const q = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => request<JobOut>(`/jobs/${jobId}`),
    refetchInterval: (query) => (query.state.data && TERMINAL.has(query.state.data.status) ? false : 2000),
  })
  const done = q.data && TERMINAL.has(q.data.status)
  const notified = useRef(false)
  useEffect(() => {
    if (done && !notified.current) {
      notified.current = true
      onDone()
    }
  }, [done, onDone])
  if (q.error) return <ErrorPanel error={q.error} onRetry={() => q.refetch()} />
  if (!q.data) return <span className={styles.muted}>작업 확인 중…</span>
  return (
    <span className={styles.job}>
      작업 <StatusBadge status={q.data.status} stage={q.data.stage} errorCode={q.data.error_code} />
      {q.data.attempts > 1 && <span className={styles.muted}> 시도 {q.data.attempts}/{q.data.max_attempts}</span>}
    </span>
  )
}

function DocumentRow({ doc, isAdmin, onChanged }: { doc: DocumentOut; isAdmin: boolean; onChanged: (job?: string) => void }) {
  const { request } = useAuth()
  const del = useMutation({
    mutationFn: () => request<JobAccepted>(`/documents/${doc.id}`, { method: 'DELETE' }),
    onSuccess: (r) => onChanged(r.job_id),
  })
  const retry = useMutation({
    mutationFn: () =>
      request<JobAccepted>(`/documents/${doc.id}/retry`, { method: 'POST', json: { expected_version: doc.active_version } }),
    onSuccess: (r) => onChanged(r.job_id),
  })
  const err = del.error ?? retry.error
  return (
    <tr>
      <td>
        {doc.status === 'ready' ? (
          <Link to={`/documents/${doc.id}/view?page=1`}>{doc.filename}</Link>
        ) : (
          doc.filename
        )}
        {doc.error_message && <div className={styles.reason}>{doc.error_message}</div>}
        {err != null && <ErrorPanel error={err} />}
      </td>
      <td>
        <StatusBadge status={doc.status} errorCode={doc.error_code} />
      </td>
      <td className={styles.num}>{doc.page_count ?? '-'}</td>
      <td className={styles.num}>{doc.chunk_count}</td>
      {isAdmin && (
        <td className={styles.actions}>
          {(doc.status === 'failed' || doc.status === 'deleting') && (
            <button type="button" onClick={() => retry.mutate()} disabled={retry.isPending}>
              재시도
            </button>
          )}
          {doc.status !== 'deleting' && (
            <button
              type="button"
              onClick={() => window.confirm(`${doc.filename} 을(를) 삭제할까요?`) && del.mutate()}
              disabled={del.isPending}
            >
              삭제
            </button>
          )}
        </td>
      )}
    </tr>
  )
}

export function DocumentsPage() {
  const { request, user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const qc = useQueryClient()
  const cols = useCollections()
  const [collectionId, setCollectionId] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [jobs, setJobs] = useState<string[]>([])
  const active = collectionId ?? cols.data?.[0]?.id ?? null

  const docs = useQuery({
    queryKey: ['documents', active],
    queryFn: () => request<{ items: DocumentOut[] }>(`/collections/${active}/documents`).then((r) => r.items),
    enabled: !!active,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['documents', active] })
    qc.invalidateQueries({ queryKey: ['collections'] })
  }

  const upload = useMutation({
    mutationFn: async (f: File) => {
      const body = new FormData()
      body.append('file', f)
      return request<UploadAccepted>(`/collections/${active}/documents`, {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
    },
    onSuccess: (r) => {
      setJobs((j) => [r.job_id, ...j])
      setFile(null)
      refresh()
    },
  })

  const tooBig = file != null && file.size > MAX_MB * 1024 * 1024
  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (file && !tooBig) upload.mutate(file)
  }

  if (cols.error) return <ErrorPanel error={cols.error} onRetry={() => cols.refetch()} />
  if (!cols.data) return <p className={styles.muted}>컬렉션을 불러오는 중…</p>

  return (
    <section className={styles.page}>
      <h2>자료</h2>
      <CollectionPicker items={cols.data} selected={active ? [active] : []} onChange={(ids) => setCollectionId(ids[0])} multiple={false} />

      {isAdmin && (
        <form className={styles.upload} onSubmit={onSubmit}>
          <input type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button type="submit" disabled={!file || tooBig || upload.isPending}>
            {upload.isPending ? '올리는 중…' : '업로드'}
          </button>
          <span className={styles.muted}>텍스트 PDF, 최대 {MAX_MB}MB·200쪽. 스캔 PDF는 지원하지 않습니다.</span>
          {tooBig && <span className={styles.reason}>파일이 {MAX_MB}MB를 넘습니다.</span>}
          {upload.error != null && <ErrorPanel error={upload.error} />}
        </form>
      )}

      {jobs.length > 0 && (
        <ul className={styles.jobs}>
          {jobs.map((id) => (
            <li key={id}>
              <JobWatcher jobId={id} onDone={refresh} />
            </li>
          ))}
        </ul>
      )}

      {docs.error ? (
        <ErrorPanel error={docs.error} onRetry={() => docs.refetch()} />
      ) : !docs.data ? (
        <p className={styles.muted}>문서를 불러오는 중…</p>
      ) : docs.data.length === 0 ? (
        <p className={styles.muted}>아직 올린 문서가 없습니다.{isAdmin ? ' PDF를 올려 보세요.' : ''}</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>파일</th>
              <th>상태</th>
              <th>쪽</th>
              <th>청크</th>
              {isAdmin && <th />}
            </tr>
          </thead>
          <tbody>
            {docs.data.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                isAdmin={isAdmin}
                onChanged={(job) => {
                  if (job) setJobs((j) => [job, ...j])
                  refresh()
                }}
              />
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

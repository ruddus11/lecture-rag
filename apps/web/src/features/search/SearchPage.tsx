import { useMutation } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../../app/useAuth'
import { CollectionPicker } from '../collections/CollectionPicker'
import { useCollections } from '../collections/useCollections'
import { AnswerPanel } from '../sources/AnswerPanel'
import type { SourceRef } from '../sources/SourceCard'
import { ViewerModal } from '../sources/ViewerModal'
import type { AnswerResponse, SearchMode } from '../../shared/api/types'
import { ErrorPanel } from '../../shared/ui/ErrorPanel'
import uiStyles from '../../shared/ui/ui.module.css'
import styles from './SearchPage.module.css'

const MAX_QUERY = 1000
const SLOW_MS = 30_000
const MODES: { value: SearchMode; label: string }[] = [
  { value: 'hybrid', label: '혼합' },
  { value: 'keyword', label: '키워드' },
  { value: 'vector', label: '의미' },
]
const SAMPLE_QUESTIONS = [
  '교착 상태가 발생하기 위한 네 가지 조건은?',
  '과적합을 줄이는 방법은 무엇인가?',
  'TCP 혼잡 제어에서 느린 시작은 어떻게 동작하나?',
]

function useElapsed(running: boolean): number {
  const [ms, setMs] = useState(0)
  useEffect(() => {
    if (!running) return
    const start = Date.now()
    const t = setInterval(() => setMs(Date.now() - start), 500)
    return () => {
      clearInterval(t)
      setMs(0)
    }
  }, [running])
  return ms
}

export function SearchPage() {
  const { request } = useAuth()
  const cols = useCollections()
  const [selected, setSelected] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<SearchMode | null>(null)
  const [viewer, setViewer] = useState<SourceRef | null>(null)

  const profileMode = cols.data?.find((c) => c.id === selected[0])?.search_profile.mode ?? cols.data?.[0]?.search_profile.mode
  const effectiveMode = mode ?? profileMode ?? 'hybrid'

  const ask = useMutation({
    mutationFn: (q: string) =>
      request<AnswerResponse>('/answers', { method: 'POST', json: { query: q, collection_ids: selected, mode: effectiveMode } }),
  })
  const elapsed = useElapsed(ask.isPending)
  const trimmed = query.trim()

  function submit(q: string) {
    if (q.trim().length === 0 || q.length > MAX_QUERY) return
    ask.mutate(q.trim())
  }
  function onSubmit(e: FormEvent) {
    e.preventDefault()
    submit(query)
  }

  return (
    <section className={styles.page}>
      {cols.error ? (
        <ErrorPanel error={cols.error} onRetry={() => cols.refetch()} />
      ) : !cols.data ? (
        <p className={styles.muted}>컬렉션을 불러오는 중…</p>
      ) : (
        <CollectionPicker items={cols.data} selected={selected} onChange={setSelected} />
      )}

      <form className={styles.form} onSubmit={onSubmit}>
        <textarea
          aria-label="질문"
          value={query}
          maxLength={MAX_QUERY}
          rows={3}
          placeholder="강의자료에 대해 질문하세요"
          disabled={ask.isPending}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(query)
          }}
        />
        <div className={styles.row}>
          <div className={styles.segment} role="radiogroup" aria-label="검색 방식">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={effectiveMode === m.value}
                className={effectiveMode === m.value ? styles.segOn : styles.seg}
                onClick={() => setMode(m.value)}
                disabled={ask.isPending}
              >
                {m.label}
              </button>
            ))}
          </div>
          <span className={styles.counter} aria-live="polite">
            {query.length}/{MAX_QUERY}
          </span>
          <button type="submit" className={styles.submit} disabled={ask.isPending || trimmed.length === 0}>
            {ask.isPending ? '답변 생성 중…' : '질문하기'}
          </button>
        </div>
      </form>

      {ask.isPending && (
        <p className={styles.loading} role="status">
          <span className={uiStyles.spinner} /> 근거를 찾고 답변을 만드는 중입니다… {Math.floor(elapsed / 1000)}초
          {elapsed > SLOW_MS && <span> 평소보다 오래 걸리고 있습니다. 잠시 더 기다리거나 나중에 다시 시도하세요.</span>}
        </p>
      )}
      {ask.error != null && !ask.isPending && <ErrorPanel error={ask.error} onRetry={() => submit(query)} />}
      {ask.data && !ask.isPending && <AnswerPanel data={ask.data} onOpen={setViewer} />}
      {!ask.data && !ask.isPending && ask.error == null && (
        <div className={styles.empty}>
          <p>예시 질문</p>
          <ul>
            {SAMPLE_QUESTIONS.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  onClick={() => {
                    setQuery(q)
                    submit(q)
                  }}
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {viewer && <ViewerModal source={viewer} onClose={() => setViewer(null)} />}
    </section>
  )
}

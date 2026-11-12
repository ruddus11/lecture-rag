import type { AnswerResponse } from '../../shared/api/types'
import { SourceCard, type SourceRef } from './SourceCard'
import styles from './sources.module.css'

const REASONS: Record<string, string> = {
  no_evidence: '검색된 자료가 없습니다.',
  insufficient_evidence: '찾은 자료만으로는 답하기에 근거가 부족합니다.',
  invalid_citations: '답변의 인용을 자료와 대조하지 못해 보류했습니다.',
  no_citations: '답변에 인용이 없어 보류했습니다.',
  empty_answer: '빈 답변이 와서 보류했습니다.',
  provider_refused: '답변 생성이 거절되어 보류했습니다.',
  provider_error: '답변 생성 결과를 해석하지 못했습니다.',
  provider_unavailable: '답변 생성 서비스에 연결하지 못했습니다. 검색 결과만 보여 드립니다.',
}

interface Props {
  data: AnswerResponse
  onOpen: (ref: SourceRef) => void
}

export function AnswerPanel({ data, onOpen }: Props) {
  return (
    <section className={styles.panel} aria-live="polite">
      {data.degraded && (
        <p className={styles.notice} role="status">
          일부 기능이 동작하지 않아 제한된 결과입니다
          {data.modes_used.length > 0 ? ` (사용한 검색: ${data.modes_used.join(', ')})` : ''}.
        </p>
      )}
      {data.abstained ? (
        <div className={styles.abstain}>
          <h3>자료에서 확인하지 못했습니다</h3>
          <p>{REASONS[data.abstain_reason ?? ''] ?? '근거가 확인되지 않아 답변을 보류했습니다.'}</p>
          <p className={styles.muted}>질문을 더 구체적으로 바꾸거나 다른 컬렉션을 선택해 보세요.</p>
        </div>
      ) : (
        <div className={styles.answer}>
          <p className={styles.answerText}>{data.answer}</p>
          <div className={styles.cards}>
            {data.citations.map((c, i) => (
              <SourceCard
                key={`${c.chunk_id}-${i}`}
                index={i + 1}
                title={c.document_title}
                page={c.page_number}
                quote={c.quote}
                onOpen={() => onOpen({ documentId: c.document_id, title: c.document_title, page: c.page_number })}
              />
            ))}
          </div>
        </div>
      )}
      {data.hits.length > 0 && (
        <details className={styles.hits} open={data.abstained}>
          <summary>검색된 근거 {data.hits.length}건</summary>
          <div className={styles.cards}>
            {data.hits.map((h) => (
              <SourceCard
                key={h.chunk_id}
                title={h.document_title}
                page={h.page_number}
                quote={h.text.length > 220 ? `${h.text.slice(0, 220)}…` : h.text}
                onOpen={() => onOpen({ documentId: h.document_id, title: h.document_title, page: h.page_number })}
              />
            ))}
          </div>
        </details>
      )}
      <p className={styles.footer}>
        {data.provider.name}/{data.provider.model} · {data.mode} · {Math.round(data.timings_ms.total ?? 0)}ms · 요청 ID{' '}
        <code>{data.request_id}</code>
      </p>
    </section>
  )
}

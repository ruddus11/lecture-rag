import styles from './sources.module.css'

export interface SourceRef {
  documentId: string
  title: string
  page: number
}

interface Props {
  index?: number
  title: string
  page: number
  quote: string
  onOpen: () => void
}

// 근거 카드: 문서명·페이지·quote. 클릭하면 해당 페이지를 연다 (quote 하이라이트는 범위 밖).
export function SourceCard({ index, title, page, quote, onOpen }: Props) {
  return (
    <button type="button" className={styles.card} onClick={onOpen} aria-label={`${title} ${page}쪽 열기`}>
      <span className={styles.cardHead}>
        {index != null && <span className={styles.idx}>[{index}]</span>}
        <span className={styles.title}>{title}</span>
        <span className={styles.page}>{page}쪽</span>
      </span>
      <span className={styles.quote}>{quote}</span>
    </button>
  )
}

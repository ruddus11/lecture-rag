import type { CollectionItem } from '../../shared/api/types'
import styles from './CollectionPicker.module.css'

interface Props {
  items: CollectionItem[]
  selected: string[]
  onChange: (ids: string[]) => void
  multiple?: boolean
}

// 허용 컬렉션만 서버가 내려준다. 아무것도 고르지 않으면 허용 컬렉션 전체에서 검색한다.
export function CollectionPicker({ items, selected, onChange, multiple = true }: Props) {
  function toggle(id: string) {
    if (!multiple) return onChange([id])
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  }
  if (items.length === 0) return <p className={styles.empty}>볼 수 있는 컬렉션이 없습니다.</p>
  return (
    <div className={styles.list} role="group" aria-label="컬렉션">
      {items.map((c) => (
        <label key={c.id} className={selected.includes(c.id) ? styles.on : styles.item}>
          <input
            type={multiple ? 'checkbox' : 'radio'}
            name="collection"
            checked={selected.includes(c.id)}
            onChange={() => toggle(c.id)}
          />
          <span>{c.name}</span>
          <span className={styles.count}>
            {c.ready_count}/{c.document_count}
          </span>
        </label>
      ))}
    </div>
  )
}

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AnswerPanel } from '../src/features/sources/AnswerPanel'
import { SourceCard } from '../src/features/sources/SourceCard'
import type { AnswerResponse, Hit } from '../src/shared/api/types'

const hit: Hit = {
  rank: 1, chunk_id: 'k1', document_id: 'd1', document_title: 'os.pdf', collection_id: 'c', page_number: 7,
  ordinal: 0, text: '교착 상태의 네 가지 조건', score: 0.03, keyword_rank: 1, vector_rank: 1,
}

function answer(over: Partial<AnswerResponse> = {}): AnswerResponse {
  return {
    request_id: 'RID', mode: 'hybrid', abstained: false, abstain_reason: null, answer: '상호 배제 등 네 가지다.',
    citations: [{ chunk_id: 'k1', document_id: 'd1', document_title: 'os.pdf', page_number: 7, quote: '네 가지 조건' }],
    hits: [hit], provider: { name: 'fake', model: 'fake' }, usage: {}, degraded: false, modes_used: ['keyword', 'vector'],
    timings_ms: { total: 12 }, cache_status: 'off', keyword_analyzer: 'korean', ...over,
  }
}

describe('근거 카드와 답변 패널', () => {
  it('근거 카드를 누르면 해당 문서·페이지로 이동 핸들러를 부른다', async () => {
    const onOpen = vi.fn()
    render(<AnswerPanel data={answer()} onOpen={onOpen} />)
    expect(screen.getByText('상호 배제 등 네 가지다.')).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'os.pdf 7쪽 열기' })[0])
    expect(onOpen).toHaveBeenCalledWith({ documentId: 'd1', title: 'os.pdf', page: 7 })
  })

  it('보류 응답은 안내 문구와 검색 근거를 보여 준다', () => {
    render(<AnswerPanel data={answer({ abstained: true, abstain_reason: 'insufficient_evidence', answer: '', citations: [] })} onOpen={() => {}} />)
    expect(screen.getByRole('heading', { name: '자료에서 확인하지 못했습니다' })).toBeInTheDocument()
    expect(screen.getByText('찾은 자료만으로는 답하기에 근거가 부족합니다.')).toBeInTheDocument()
    expect(screen.getByText('검색된 근거 1건')).toBeInTheDocument()
  })

  it('degraded 이면 사용한 검색 방식을 알린다', () => {
    render(<AnswerPanel data={answer({ degraded: true, modes_used: ['vector'] })} onOpen={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('사용한 검색: vector')
  })

  it('SourceCard 는 문서명·페이지·quote 를 보여 준다', () => {
    render(<SourceCard index={2} title="net.pdf" page={6} quote="느린 시작" onOpen={() => {}} />)
    expect(screen.getByText('[2]')).toBeInTheDocument()
    expect(screen.getByText('6쪽')).toBeInTheDocument()
    expect(screen.getByText('느린 시작')).toBeInTheDocument()
  })
})

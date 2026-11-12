import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/shared/api/client'
import { ErrorPanel } from '../src/shared/ui/ErrorPanel'
import { StatusBadge } from '../src/shared/ui/StatusBadge'

describe('StatusBadge', () => {
  it('처리 중이면 단계를, 실패면 사유 코드를 함께 보여 준다', () => {
    const { rerender } = render(<StatusBadge status="processing" stage="embedding" />)
    expect(screen.getByText('처리 중 · 임베딩')).toBeInTheDocument()
    rerender(<StatusBadge status="failed" errorCode="unsupported_scan" />)
    expect(screen.getByText('실패 · unsupported_scan')).toHaveAttribute('data-status', 'failed')
    rerender(<StatusBadge status="ready" />)
    expect(screen.getByText('사용 가능')).toBeInTheDocument()
  })
})

describe('ErrorPanel', () => {
  it('request_id 를 보여 주고 retryable 이면 재시도 버튼을 낸다', async () => {
    const onRetry = vi.fn()
    render(<ErrorPanel error={new ApiError(503, 'search_unavailable', 'x', '01REQ', true)} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('검색 엔진에 연결할 수 없습니다.')
    expect(screen.getByText('01REQ')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('retryable 이 아니면 재시도 버튼이 없다', () => {
    render(<ErrorPanel error={new ApiError(404, 'document_not_found', 'x', 'R', false)} onRetry={() => {}} />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})

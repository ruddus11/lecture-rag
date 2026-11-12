import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest, errorMessage, toApiError } from '../src/shared/api/client'

afterEach(() => vi.restoreAllMocks())

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })
}

describe('API 오류 매핑', () => {
  it('표준 오류 본문을 ApiError 로 바꾼다', async () => {
    const e = await toApiError(
      json(404, { error: { code: 'collection_not_found', message: 'x', request_id: '01ABC', retryable: false, details: null } }),
    )
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(404)
    expect(e.code).toBe('collection_not_found')
    expect(e.requestId).toBe('01ABC')
    expect(e.retryable).toBe(false)
    expect(errorMessage(e)).toBe('컬렉션을 찾을 수 없습니다.')
  })

  it('JSON 이 아닌 5xx 는 retryable, request id 는 헤더에서', async () => {
    const e = await toApiError(new Response('bad gateway', { status: 502, headers: { 'x-request-id': 'RID123' } }))
    expect(e.code).toBe('http_502')
    expect(e.retryable).toBe(true)
    expect(e.requestId).toBe('RID123')
  })

  it('네트워크 실패는 network_error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(apiRequest('/collections')).rejects.toMatchObject({ code: 'network_error', retryable: true })
  })

  it('Authorization 헤더와 JSON 본문을 붙인다', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, { ok: 1 }))
    await apiRequest('/answers', { method: 'POST', token: 'tok', json: { query: 'q' } })
    const [url, init] = spy.mock.calls[0]
    expect(url).toBe('/api/v1/answers')
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer tok')
    expect(init?.body).toBe('{"query":"q"}')
  })

  it('429 는 코드별 메시지', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(429, { error: { code: 'rate_limited', message: 'm', request_id: 'r', retryable: true, details: null } }),
    )
    await expect(apiRequest('/search')).rejects.toSatisfy((e: unknown) => errorMessage(e).includes('잠시 후'))
  })
})

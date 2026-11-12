import type { ErrorBody } from './types'

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly retryable: boolean
  readonly details: unknown

  constructor(status: number, code: string, message: string, requestId: string | null, retryable: boolean, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.retryable = retryable
    this.details = details
  }
}

// 코드별 사용자 메시지. 없으면 서버 message 를 그대로 쓴다.
const MESSAGES: Record<string, string> = {
  unauthorized: '로그인이 필요합니다.',
  token_expired: '로그인이 만료되었습니다. 다시 로그인해 주세요.',
  forbidden_role: '관리자만 할 수 있는 작업입니다.',
  collection_not_found: '컬렉션을 찾을 수 없습니다.',
  document_not_found: '문서를 찾을 수 없습니다.',
  duplicate_document: '같은 파일이 이미 이 컬렉션에 있습니다.',
  file_too_large: '파일이 20MB를 넘습니다.',
  unsupported_media_type: 'PDF 파일만 올릴 수 있습니다.',
  rate_limited: '요청이 너무 많습니다. 잠시 후 다시 시도하세요.',
  provider_rate_limited: '답변 생성 사용량 한도에 걸렸습니다. 잠시 후 다시 시도하세요.',
  search_unavailable: '검색 엔진에 연결할 수 없습니다.',
  network_error: '서버에 연결할 수 없습니다.',
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return MESSAGES[err.code] ?? err.message
  if (err instanceof Error) return err.message
  return '알 수 없는 오류가 발생했습니다.'
}

function isErrorBody(v: unknown): v is ErrorBody {
  return typeof v === 'object' && v !== null && 'error' in v && typeof (v as ErrorBody).error?.code === 'string'
}

export async function toApiError(res: Response): Promise<ApiError> {
  const headerId = res.headers.get('x-request-id')
  const body: unknown = await res.json().catch(() => null)
  if (isErrorBody(body)) {
    const e = body.error
    return new ApiError(res.status, e.code, e.message, e.request_id ?? headerId, e.retryable, e.details)
  }
  const retryable = res.status === 429 || res.status >= 500
  return new ApiError(res.status, `http_${res.status}`, `요청이 실패했습니다 (HTTP ${res.status}).`, headerId, retryable)
}

export interface RequestOptions {
  method?: string
  token?: string | null
  json?: unknown
  body?: BodyInit
  headers?: Record<string, string>
  signal?: AbortSignal
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) }
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`
  if (opts.json !== undefined) headers['Content-Type'] = 'application/json'
  const body = opts.json !== undefined ? JSON.stringify(opts.json) : opts.body
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { method: opts.method ?? 'GET', headers, body, signal: opts.signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'network_error', '서버에 연결할 수 없습니다.', null, true)
  }
  if (!res.ok) throw await toApiError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

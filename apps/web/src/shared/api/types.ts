// 설계서 8.2 스키마를 수동으로 옮긴 타입. 서버 schemas/*.py 와 함께 고친다.

export type Role = 'student' | 'admin'
export type SearchMode = 'keyword' | 'vector' | 'hybrid'
export type DocumentStatus = 'queued' | 'processing' | 'ready' | 'failed' | 'deleting' | 'deleted'
export type JobStatus = 'queued' | 'processing' | 'succeeded' | 'failed'

export interface UserOut {
  id: string
  username: string
  institution_id: string
  role: Role
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserOut
}

export interface MeResponse extends UserOut {
  institution_name: string
}

export interface SearchProfile {
  mode: SearchMode
  candidate_k: number
  context_k: number
  rrf_rank_constant: number
  max_chunks_per_page: number
}

export interface CollectionItem {
  id: string
  slug: string
  name: string
  document_count: number
  ready_count: number
  version: number
  search_profile: SearchProfile
}

export interface DocumentOut {
  id: string
  collection_id: string
  filename: string
  status: DocumentStatus
  page_count: number | null
  chunk_count: number
  active_version: number
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface UploadAccepted {
  document_id: string
  job_id: string
  status: 'queued'
}

export interface JobOut {
  id: string
  document_id: string
  kind: 'ingest' | 'delete'
  status: JobStatus
  stage: string | null
  attempts: number
  max_attempts: number
  error_code: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface JobAccepted {
  job_id: string
  status: string
}

export interface Hit {
  rank: number
  chunk_id: string
  document_id: string
  document_title: string
  collection_id: string
  page_number: number
  ordinal: number
  text: string
  score: number
  keyword_rank: number | null
  vector_rank: number | null
}

export interface SearchResponse {
  request_id: string
  mode: SearchMode
  modes_used: SearchMode[]
  degraded: boolean
  hits: Hit[]
  timings_ms: Record<string, number>
  cache_status: string
  keyword_analyzer: string
}

export interface CitationOut {
  chunk_id: string
  document_id: string
  document_title: string
  page_number: number
  quote: string
}

export interface AnswerResponse {
  request_id: string
  mode: SearchMode
  abstained: boolean
  abstain_reason: string | null
  answer: string
  citations: CitationOut[]
  hits: Hit[]
  provider: { name: string; model: string }
  usage: Record<string, number>
  degraded: boolean
  modes_used: SearchMode[]
  timings_ms: Record<string, number>
  cache_status: string
  keyword_analyzer: string
}

export interface ErrorBody {
  error: {
    code: string
    message: string
    request_id: string | null
    retryable: boolean
    details: unknown
  }
}

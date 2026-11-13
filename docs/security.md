# M11 보안 점검

2026-11-13, 기준 `062ede3`, macOS arm64, Python 3.12.13. 아래 증거는 자동 테스트 또는 소스 수동 점검이며 침투 테스트·공개 운영 인증을 의미하지 않는다.

| 설계서 13장 항목 | 증거 | 상태 / 한계 |
|---|---|---|
| 비밀·자료 제외 | `.gitignore`: .env, *.db, data/files, evaluation/private, hf_cache. `.env.example` API 키·AUTH_SECRET 빈 값 | 실비밀·수업 PDF 커밋 금지 |
| 커밋 전·전체 이력 스캔 | `python3 scripts/check_secrets.py`, `--history`; `.githooks/pre-commit` | sk 키·private key 패턴 최소 스캔. 모든 비밀을 탐지하지는 않음 |
| 로그 마스킹 | `tests/unit/test_security_logging.py::test_masks_nested_fields_and_traceback` | M11 중첩 extra·예외 traceback 누락을 RED→GREEN 수정 |
| 질문 기본 미기록 | `tests/api/test_answers.py::test_answer_with_valid_citation_in_hits` 및 QueryLog.query_text 검사 | LOG_QUERY_TEXT=false 유지 |
| 파일명·경로 | `tests/api/test_file.py`, `test_security.py::test_file_path_traversal_and_symlink` | UUID 저장, resolve 하위 경계, RFC5987, symlink 이탈 차단 |
| 크기·페이지·파싱 상한 | `test_documents.py::test_file_too_large_413`, `test_too_many_pages_fails`; `test_security.py::test_request_body_limit` | 파일 20MiB/200쪽/파싱 60초, HTTP 본문 21MiB. Content-Length와 chunked 모두 검사 |
| PDF 링크·JS | `documents/parser.py` 텍스트 추출만 수행, URL 호출 코드 없음(수동 소스 확인) | PDF viewer는 원문을 렌더함. 유해 PDF 수집 서비스로 공개하지 않음 |
| 인증·토큰 | `test_auth_collections.py`: 로그인, 만료 401, 8시간 TTL, 권한; `core/auth.py`: bcrypt/HS256 | 웹 AuthProvider 메모리 상태. 공개 운영에는 HTTPS/IdP 필요 |
| CORS·요청 ID | `test_security.py::test_cors_allowlist`, `test_request_id_rejects_invalid_and_preserves_valid` | 브라우저 allowlist; CORS는 인증 대체 수단이 아님 |
| rate limit | `test_auth_collections.py::test_rate_limiter_429` | 프로세스 내 사용자별 제한. 로그인 brute force의 별도 IP 제한은 미구현 |
| prompt injection | `test_answers.py::test_injection_pdf_not_followed`, `test_invalid_id_retried_once_then_abstain`; `test_citations.py` | 자작 injection.pdf를 테스트 시 생성. fake/인용 경계 검증이며 실제 LLM의 지시 저항성은 미검증 |
| 컨테이너 | `apps/api/Dockerfile` USER app, `apps/web/Dockerfile` USER nginx, 이미지 태그·digest 고정; compose 엔진 ports 없음(수동 소스 확인) | rootfs read_only 선택 미적용. Docker 실기동은 이 워크트리 미실행 |
| 개인정보·외부 전송 | README 한계 절 | 개인정보·내부 문서 미반입. 외부 LLM 선택 시 질문·검색 근거 전송 |
| 고객 설정 즉시 반영 | `tests/api/test_requirements.py` 3건 | 원장 변경 후 같은 JWT로 다음 요청 검사 |

## 실행

```bash
git config core.hooksPath .githooks
python3 scripts/check_secrets.py
python3 scripts/check_secrets.py --history
cd apps/api
uv run pytest tests/api/test_security.py tests/api/test_requirements.py tests/unit/test_security_logging.py
```

스캔은 키 값을 출력하지 않는다. 탐지 시 blob ID만 출력한다. 설치되지 않은 훅은 실행되지 않으므로 CI에서도 검사한다.
중첩 로그와 traceback 마스킹은 JSON 출력 경계에서 검증한다. 예외 내용 자체를 외부 응답으로 보내지 않는다.

# 고객 요구와 수용 조건

2026-11-13. 가상 고객: 두 캠퍼스에서 여러 과목을 운영하는 교육 담당자.

## 문제와 핵심 가치

학생은 허용된 강의자료에서 근거 페이지를 다시 확인하려고 서비스를 연다. 핵심 pain은 다른 과목 자료 혼입, 권한 회수 지연, 과목별 검색 방식 불일치다. 핵심 가치는 **허용된 과목 자료에서만 답과 출처를 바로 확인**하는 것이다.

## 요청 및 범위

- Must: 기관·과목 분리, 학생 역할 제한, 설정 변경 다음 요청 반영.
- Should: 변경 원장 운영 절차·자동 수용 테스트.
- Could: 향후 감사 이벤트.
- Not now: 설정 편집 UI·동적 정책 엔진·새 PATCH API.

기존 SQLite 원장을 정책 기준으로 유지한다. 변경은 관리자가 DB 세션에서 수행하는 운영 변경으로 가정한다. YAML은 최초 seed이며 실행 중 파일 수정만으로 즉시 반영되는 계약은 없다. 신규 설정 API를 추가하지 않아 병합 충돌과 운영 복잡도를 줄이지만 운영자 변경 편의성은 제한된다.

| 요구 | 수용 조건 | 자동 증거 |
|---|---|---|
| 학생 허용 자료만 | allowed_roles에서 student 제거 후 같은 JWT의 목록 제외, search/answer/file/document 404, admin 유지 | `test_allowed_roles_change_immediately_revokes_access` |
| 과목 검색 방식 | 원장 search_profile.mode를 keyword/vector/hybrid로 변경하면 다음 search·answer 응답 mode 일치, 명시 모드는 우선 | `test_search_profile_mode_change_applies_next_request` |
| 신규 과목 격리 | admin 전용 컬렉션 생성·색인 후 다른 기관 admin/student 및 같은 기관 student에게 조회·검색·답변·파일 차단 | `test_new_collection_keeps_institution_and_role_isolation` |

## 변경 기록

- 2026-11-13 / M11: API·데이터 모델 변경 없이 기존 컬렉션 원장의 다음 요청 반영 계약을 자동화. 테스트는 fake 임베딩·메모리 Qdrant·fake keyword/answer를 사용한다. 실제 엔진 캐시가 연결되는 M10 병합 후에도 같은 테스트를 다시 실행해야 한다.

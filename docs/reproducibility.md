# 실행·검증 기록

## 2026-11-13 최종 기능 검증

검증한 런타임 소스는 `03cd4e7`입니다. 아래에서 로컬 Docker와 원격 Linux, 실제 OpenAI 호출을 구분했습니다. 과거 성능 수치를 이번 컨테이너 측정으로 바꾸지 않았습니다.

| 환경 | 확인한 범위 | 결과 |
|---|---|---|
| macOS arm64, Python 3.12.13 | API 회귀, 린트·포맷·mypy | 156 passed, integration 5건 별도; 61 source files 타입 검사 통과 |
| Docker Desktop 4.99.0 / Engine 29.9.3 / Compose 5.7.0 | 독립 프로젝트의 API·웹·Qdrant·OpenSearch | 네 서비스 정상, SQLite·Nori·bge-m3·검색 필드 준비 상태 정상 |
| 로컬 Docker 검색 엔진 | 고유 인덱스의 통합 테스트 | 5 passed. aiohttp/Python 관련 DeprecationWarning 5건은 별도 기록 |
| 로컬 Docker HTTP | 자작 PDF 3개 업로드, 5문항×3검색 방식 | 각 방식 Hit@5 5/5; 기관별 자료 범위 적용 확인 |
| 로컬 Docker 웹 + 실제 OpenAI | 학생 로그인→질문→인용→원문 PDF 7/10쪽 | 실제 GPT 답변과 PDF canvas 표시 확인 |
| 로컬 Docker 웹 + 실제 OpenAI | 근거에 없는 교수 연구실 전화번호 질문 | 근거 부족 보류 화면 확인 |
| 로컬 Docker HTTP | 익명·타기관·삭제 | 익명 파일 401, 타기관 파일 404, 허용 Range 206, 삭제 202 후 파일 404와 세 방식 검색에서 제외. 샘플 재업로드로 데모 복원 |
| GitHub Actions Linux | 기본 검사·새 Compose·실제 엔진·브라우저 | checks와 integration 모두 성공. [실행 기록](https://github.com/ruddus11/lecture-rag/actions/runs/43382854896) |

로컬 Docker는 새 문서·DB·검색 인덱스 볼륨으로 실행했으며, 모델 다운로드만 기존 bge-m3 캐시를 읽기 전용으로 재사용했습니다. 원격 Linux는 fresh 모델 캐시로 검증했습니다. 로컬 평가의 API `/meta` commit은 빌드 인자를 지정하지 않아 `unknown`으로 남았으므로, 해당 원본 결과를 수정하지 않고 별도로 검증 소스를 명시했습니다.

## 실제 공급자 연결 확인

- OpenAI 임베딩: `text-embedding-3-small`, 1,536차원, 단일 요청 3,316ms.
- OpenAI 답변: `gpt-4.1-mini-2025-04-14`, 정상 근거의 구조화 답변과 인용 검증 통과. 단일 smoke 입력 573·출력 101토큰, 5,221ms.
- 근거 없는 질문: 같은 모델이 `insufficient_evidence`를 반환했습니다. 단일 smoke 입력 572·출력 15토큰, 4,797ms.
- 웹 전체 흐름은 별도로 실제 로컬 bge-m3 검색 결과를 GPT에 전달해 확인했습니다. 위 단일 요청 시간을 지연 벤치마크로 사용하지 않았습니다.
- API 키는 로컬 `.env`에서만 읽었으며 GitHub CI에 전달하지 않았습니다. 원격 브라우저 시나리오의 답변 생성기는 `fake`였습니다.
- Anthropic 실제 호출과 광범위한 생성 품질 평가는 수행하지 않았습니다.

## 컨테이너 검증에서 수정한 문제

1. 저장소 폴더 깊이를 고정한 설정 경로 코드가 `/app/app/retrieval/keyword.py`에서 `IndexError`를 일으켰습니다. 같은 배치 경로를 재현하는 회귀 테스트를 추가하고 상위 경로를 탐색하도록 수정했습니다.
2. Nginx가 PDF.js `.mjs` 워커를 `application/octet-stream`으로 보내 원문 뷰어가 열리지 않았습니다. JavaScript MIME 매핑을 추가했습니다. 실제 HTTP에서 `.mjs`는 `application/javascript`, CSS는 `text/css`를 유지하는 것과 브라우저 canvas 렌더링을 확인했습니다.

## 재현 명령

일반 실행과 실제 모델 선택 방법은 [README](../README.md)에 정리했습니다. 데이터 삭제가 필요한 fresh 검증은 기존 자료가 없는 별도 프로젝트 이름·볼륨에서만 수행합니다. 원본 콘솔 로그와 개인 개발 경로는 공개 저장소에 넣지 않았습니다.

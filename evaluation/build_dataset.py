"""검수한 자작 PDF 문항을 고정 sha256과 함께 저장. test 변경 시 CHANGELOG 기록 필수."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 각 기대 페이지를 sample_content 원문과 실제 PDF 추출문에서 대조했다.
ITEMS = {
    "definition": [
        ("프로세스란 무엇인가?", "os", [2]),
        ("스레드란 무엇인가?", "os", [3]),
        ("문맥 교환이란 무엇인가?", "os", [4]),
        ("교착 상태란 무엇인가?", "os", [7]),
        ("뮤텍스란 무엇인가?", "os", [9]),
        ("가상 메모리란 무엇인가?", "os", [10]),
        ("지도 학습이란 무엇인가?", "ai", [2]),
        ("과적합이란 무엇인가?", "ai", [4]),
        ("k-평균 군집화란 무엇인가?", "ai", [9]),
        ("경사 하강법이란 무엇인가?", "ai", [3]),
    ],
    "paraphrase": [
        (
            "프로그램이 실제 실행되는 동안 독립 주소 공간은 무엇으로 구성되는가?",
            "os",
            [2],
        ),
        ("같은 프로세스의 실행 흐름들이 함께 쓰는 자원은?", "os", [3]),
        ("CPU가 실행 대상을 바꿀 때 왜 처리량이 떨어질 수 있는가?", "os", [4]),
        ("긴 작업 때문에 짧은 작업이 기다리는 비선점 방식의 약점은?", "os", [5]),
        ("우선순위가 낮아 무한 대기하는 문제를 어떻게 완화하는가?", "os", [6]),
        ("자원이 안전하게 배분될지 미리 검사하는 교착 처리 방법은?", "os", [8]),
        ("페이지가 너무 자주 없어져 CPU 이용률이 떨어지는 현상은?", "os", [10]),
        ("훈련 오차는 낮지만 검증 오차가 높으면 어떤 대책을 쓰는가?", "ai", [4]),
        ("정답 없이 데이터의 구조를 찾는 학습 방식은?", "ai", [2]),
        ("매번 앞 모델의 실수를 다음 모델이 고치는 앙상블은?", "ai", [7]),
    ],
    "multi_evidence": [
        ("프로세스와 스레드의 주소 공간과 공유 자원을 비교하라.", "os", [2, 3]),
        ("선점형 스케줄링의 응답성 이득과 문맥 교환의 비용을 설명하라.", "os", [5, 4]),
        ("교착 상태의 네 조건과 예방 방법의 관계를 설명하라.", "os", [7, 8]),
        ("라운드 로빈의 시간 할당량과 문맥 교환 오버헤드의 관계는?", "os", [6, 4]),
        ("과적합을 막는 대책과 검증 세트의 역할은?", "ai", [4, 5]),
        ("지도 학습의 분류와 이를 평가하는 정밀도, 재현율을 설명하라.", "ai", [2, 6]),
        ("의사결정나무 과적합과 일반적인 규제 대책을 설명하라.", "ai", [7, 4]),
        ("신경망의 역전파와 경사 하강법의 역할은?", "ai", [8, 3]),
    ],
    "numeric_or_code": [
        ("라운드 로빈의 일반적인 시간 할당량 범위는?", "os", [6]),
        ("세마포어 임계 구역 앞뒤의 wait와 signal 코드는?", "os", [9]),
        ("선형 회귀의 식과 가중치 갱신식은?", "ai", [3]),
        ("정밀도와 재현율과 F1 점수의 계산식은?", "ai", [6]),
        ("양성이 1%일 때 모두 음성 예측하면 정확도는?", "ai", [6]),
        ("ReLU의 계산식은?", "ai", [8]),
    ],
    "unanswerable": [
        ("이 강의 교수님의 연구실 전화번호는?", "os", []),
        ("올해 운영체제 기말시험 날짜는?", "os", []),
        ("수강생 김민수의 성적은?", "os", []),
        ("이 자료에서 정한 수강료 환불 금액은?", "ai", []),
        ("이 강의의 다음 주 강의실 번호는?", "ai", []),
        ("교재 구매용 은행 계좌 번호는?", "ai", []),
    ],
}


def main():
    paths = {
        "os": ROOT / "data/samples/os_week3_process.pdf",
        "ai": ROOT / "data/samples/ai_week2_ml_basics.pdf",
    }
    slugs = {"os": "operating_systems", "ai": "ai_basics"}
    import pymupdf

    pages = {k: [p.get_text() for p in pymupdf.open(v)] for k, v in paths.items()}
    hashes = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()}
    rows = []
    for category, items in ITEMS.items():
        test_count = {
            "definition": 3,
            "paraphrase": 2,
            "multi_evidence": 2,
            "numeric_or_code": 1,
            "unanswerable": 2,
        }[category]
        for i, (question, doc, numbers) in enumerate(items):
            refs = [pages[doc][n - 1].strip() for n in numbers]
            rows.append(
                dict(
                    query_id=f"q{len(rows) + 1:03}",
                    question=question,
                    answerable=bool(numbers),
                    category=category,
                    split="test" if i >= len(items) - test_count else "dev",
                    collection_slug=slugs[doc],
                    gold=[dict(document_sha256=hashes[doc], page_numbers=numbers)]
                    if numbers
                    else [],
                    required_pages=[
                        dict(document_sha256=hashes[doc], page_number=n)
                        for n in numbers
                    ]
                    if category == "multi_evidence"
                    else [],
                    reference_answer="\n".join(refs)
                    if refs
                    else "자료에서 확인하지 못했습니다.",
                    review_status="verified_against_pdf_text",
                    review_date="2026-11-12",
                    notes="자작 PDF 물리 페이지와 본문 대조. 의미 인용 수동 평가는 별도.",
                )
            )
    for split in ["dev", "test"]:
        (ROOT / f"evaluation/dataset.{split}.jsonl").write_text(
            "".join(
                json.dumps(r, ensure_ascii=False) + "\n"
                for r in rows
                if r["split"] == split
            )
        )


if __name__ == "__main__":
    main()

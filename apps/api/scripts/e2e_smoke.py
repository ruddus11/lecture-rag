"""실행 중인 API 에 대해 전체 흐름을 한 번 돌리는 수동 smoke (HTTP 만 사용).

    python -m scripts.e2e_smoke --base http://127.0.0.1:8000/api/v1 --modes vector
    python -m scripts.e2e_smoke --skip-upload --modes keyword,vector,hybrid --answers

data/samples 의 자작 PDF 를 컬렉션에 올리고 ready 까지 기다린 뒤, 샘플 질문 5개를 검색해 기대 페이지가
상위 5 안에 있는지 출력한다. 출력은 JSON 줄이며 docs/handoff.md 의 실행 로그로 붙인다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[3]
SAMPLES = {
    "os_week3_process.pdf": "operating_systems",
    "ai_week2_ml_basics.pdf": "ai_basics",
    "net_week4_transport.pdf": "networks",
}
# (질문, 문서, 기대 페이지, 질의 계정)
QUESTIONS = [
    ("교착 상태가 발생하기 위한 네 가지 조건은?", "os_week3_process.pdf", 7, "a_student"),
    ("라운드 로빈에서 시간 할당량이 너무 작으면 어떻게 되나?", "os_week3_process.pdf", 6, "a_student"),
    ("과적합을 줄이는 방법은 무엇인가?", "ai_week2_ml_basics.pdf", 4, "a_student"),
    ("TCP 혼잡 제어에서 느린 시작은 어떻게 동작하나?", "net_week4_transport.pdf", 6, "b_student"),
    ("스레드의 문맥 교환 비용이 프로세스보다 작은 이유는?", "os_week3_process.pdf", 3, "a_student"),
]
PASSWORDS = {
    "a_admin": "admin-a-demo-2026",
    "a_student": "student-a-demo-2026",
    "b_admin": "admin-b-demo-2026",
    "b_student": "student-b-demo-2026",
}


def out(event: str, **kw: Any) -> None:
    print(json.dumps({"event": event, **kw}, ensure_ascii=False), flush=True)


class Client:
    def __init__(self, base: str) -> None:
        self.http = httpx.Client(base_url=base, timeout=120)
        self.tokens: dict[str, str] = {}

    def h(self, user: str) -> dict[str, str]:
        if user not in self.tokens:
            r = self.http.post("/auth/login", json={"username": user, "password": PASSWORDS[user]})
            r.raise_for_status()
            self.tokens[user] = r.json()["access_token"]
        return {"Authorization": f"Bearer {self.tokens[user]}"}

    def cols(self, user: str) -> dict[str, str]:
        r = self.http.get("/collections", headers=self.h(user))
        r.raise_for_status()
        return {c["slug"]: c["id"] for c in r.json()["items"]}


def upload_all(c: Client, samples_dir: Path) -> dict[str, str]:
    doc_ids: dict[str, str] = {}
    jobs: dict[str, tuple[str, str]] = {}  # 파일명 → (job_id, 관리자 계정)
    t0 = time.perf_counter()
    for name, slug in SAMPLES.items():
        admin = "b_admin" if slug == "networks" else "a_admin"
        cid = c.cols(admin)[slug]
        path = samples_dir / name
        r = c.http.post(
            f"/collections/{cid}/documents",
            headers=c.h(admin),
            files={"file": (name, path.read_bytes(), "application/pdf")},
        )
        if r.status_code == 409:
            doc_ids[name] = r.json()["error"]["details"]["document_id"]
            out("upload_duplicate", file=name, document_id=doc_ids[name])
            continue
        r.raise_for_status()
        doc_ids[name], jobs[name] = r.json()["document_id"], (r.json()["job_id"], admin)
        out("uploaded", file=name, http=r.status_code, **r.json())
    for name, (job_id, admin) in jobs.items():
        while True:
            body = c.http.get(f"/jobs/{job_id}", headers=c.h(admin)).json()
            if body["status"] in ("succeeded", "failed"):
                out(
                    "job_done",
                    file=name,
                    status=body["status"],
                    error=body["error_code"],
                    attempts=body["attempts"],
                    elapsed_s=round(time.perf_counter() - t0, 1),
                )
                break
            time.sleep(1)
    return doc_ids


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    ap.add_argument("--modes", default="vector")
    ap.add_argument("--samples", default=str(REPO / "data" / "samples"))
    ap.add_argument("--skip-upload", action="store_true")
    ap.add_argument("--answers", action="store_true", help="POST /answers 도 1회씩")
    args = ap.parse_args(argv)
    c = Client(args.base)
    out("health", **c.http.get("/health/ready").json())
    out("meta", **c.http.get("/meta", headers=c.h("a_student")).json())
    if not args.skip_upload:
        upload_all(c, Path(args.samples))
    ok_total = 0
    for mode in args.modes.split(","):
        ok = 0
        for q, doc, page, user in QUESTIONS:
            r = c.http.post("/search", headers=c.h(user), json={"query": q, "mode": mode, "top_k": 5})
            if r.status_code != 200:
                out("search_error", mode=mode, query=q, status=r.status_code, body=r.json())
                continue
            b = r.json()
            top = [(h["document_title"], h["page_number"]) for h in b["hits"]]
            hit = (doc, page) in top
            ok += hit
            out(
                "search",
                mode=mode,
                query=q,
                expected=[doc, page],
                hit_at_5=hit,
                top=top,
                modes_used=b["modes_used"],
                degraded=b["degraded"],
                total_ms=b["timings_ms"].get("total"),
            )
            if args.answers:
                a = c.http.post("/answers", headers=c.h(user), json={"query": q, "mode": mode})
                ab = a.json()
                out(
                    "answer",
                    mode=mode,
                    status=a.status_code,
                    abstained=ab.get("abstained"),
                    reason=ab.get("abstain_reason"),
                    answer=(ab.get("answer") or "")[:120],
                    citations=[(x["document_title"], x["page_number"]) for x in ab.get("citations", [])],
                )
        out("summary", mode=mode, hit_at_5=f"{ok}/{len(QUESTIONS)}")
        ok_total += ok
    return 0


if __name__ == "__main__":
    sys.exit(main())

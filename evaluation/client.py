"""평가 전용 HTTP 클라이언트. 비밀은 환경변수로만 받는다."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx


class EvaluationClient:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base, timeout=120)
        try:
            r = self.http.post(
                "/auth/login",
                json={
                    "username": os.environ["EVAL_USERNAME"],
                    "password": os.environ["EVAL_PASSWORD"],
                },
            )
            r.raise_for_status()
            self.http.headers["Authorization"] = "Bearer " + r.json()["access_token"]
            self.meta = self.get("/meta")
            self.collections = {
                c["slug"]: c["id"] for c in self.get("/collections")["items"]
            }
            self.documents = {}
            self.document_count = self.chunk_count = 0
            for slug, cid in self.collections.items():
                for doc in self.get(f"/collections/{cid}/documents")["items"]:
                    if doc["status"] != "ready":
                        continue
                    file = self.http.get(f"/documents/{doc['id']}/file")
                    file.raise_for_status()
                    digest = hashlib.sha256(file.content).hexdigest()
                    self.documents[(slug, digest)] = doc["id"]
                    self.document_count += 1
                    self.chunk_count += doc["chunk_count"]
            self.meta.update(
                document_count=self.document_count,
                chunk_count=self.chunk_count,
                container_memory=os.getenv(
                    "EVAL_CONTAINER_MEMORY", "unavailable (native host)"
                ),
                environment=os.getenv("EVAL_ENVIRONMENT", "unspecified"),
                cache=os.getenv("EVAL_CACHE", "unknown"),
            )
        except BaseException:
            self.http.close()
            raise

    def get(self, path):
        r = self.http.get(path)
        r.raise_for_status()
        return r.json()

    def close(self):
        self.http.close()


def dataset(split: str, root: Path | None = None) -> list[dict]:
    import json

    root = root or Path(__file__).parent
    return [
        json.loads(line)
        for line in (root / f"dataset.{split}.jsonl").read_text().splitlines()
        if line
    ]

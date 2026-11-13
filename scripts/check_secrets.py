#!/usr/bin/env python3
"""키 값을 출력하지 않는 최소 비밀 스캔. 기본 staged, --history 전체 도달 가능 이력."""
from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = [
    re.compile(rb"sk-(?:ant-)?[A-Za-z0-9_-]{16,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def main() -> int:
    if "--history" in sys.argv:
        objects = [line.split(b" ", 1)[0].decode() for line in git("rev-list", "--objects", "--all").splitlines()]
    else:
        objects = []
        for entry in git("ls-files", "--stage", "-z").split(b"\0"):
            if entry:
                mode, oid, _ = entry.split(b"\t", 1)[0].split()
                if mode != b"120000":
                    objects.append(oid.decode())
    checked = 0
    failed = []
    for oid in dict.fromkeys(objects):
        if git("cat-file", "-t", oid).strip() != b"blob":
            continue
        checked += 1
        content = git("cat-file", "blob", oid)
        if any(p.search(content) for p in PATTERNS):
            failed.append(oid)
    for oid in failed:
        print(f"secret pattern found in blob {oid}; inspect locally (value suppressed)", file=sys.stderr)
    print(f"secret scan: {checked} blobs, {len(failed)} findings")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())

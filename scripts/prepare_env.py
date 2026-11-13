"""로컬·CI용 .env 최초 생성. 기존 파일과 사용자 비밀은 덮어쓰지 않는다."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env already exists; keep it and configure AUTH_SECRET manually")
source = (root / ".env.example").read_text()
lines = [
    f"AUTH_SECRET={secrets.token_urlsafe(48)}" if line.startswith("AUTH_SECRET=") else line
    for line in source.splitlines()
]
with open(target, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
    stream.write("\n".join(lines) + "\n")
print("Created .env with a random AUTH_SECRET (value suppressed)")

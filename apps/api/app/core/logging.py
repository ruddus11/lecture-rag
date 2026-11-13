"""JSON 로그, X-Request-Id 미들웨어, 비밀 마스킹 (설계서 13장·15장)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_REQ_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")


def new_ulid() -> str:
    """ULID (48비트 ms 시각 + 80비트 난수, Crockford base32 26자)."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


_STD_ATTRS = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class SecretMasker(logging.Filter):
    """로그 레코드의 메시지·extra 필드에서 비밀 값과 Authorization 헤더를 *** 로 치환."""

    _bearer = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.=]+", re.IGNORECASE)
    _key_patterns = re.compile(r"(sk-ant-[A-Za-z0-9\-_]{8,}|sk-[A-Za-z0-9\-_]{16,})")

    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = [s for s in (secrets or []) if len(s) >= 6]

    def mask(self, text: str) -> str:
        for s in self.secrets:
            text = text.replace(s, "***")
        text = self._bearer.sub(r"\1***", text)
        return self._key_patterns.sub("***", text)

    def mask_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.mask(value)
        if isinstance(value, dict):
            return {
                k: "***" if str(k).lower() == "authorization" else self.mask_value(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.mask_value(v) for v in value]
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.mask(record.getMessage())
        record.args = None
        for k, v in list(record.__dict__.items()):
            if k.lower() == "authorization":
                record.__dict__[k] = "***"
            elif k not in _STD_ATTRS:
                record.__dict__[k] = self.mask_value(v)
        if record.exc_info:
            record.exc_text = self.mask(logging.Formatter().formatException(record.exc_info))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        msg = record.getMessage()
        if msg and msg != out["event"]:
            out["message"] = msg
        for k, v in record.__dict__.items():
            if k not in _STD_ATTRS and k not in out:
                out[k] = v
        if record.exc_info:
            out["exc"] = record.exc_text or self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup_logging(level: str, secrets: list[str]) -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_lrag", False):
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretMasker(secrets))
    handler._lrag = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    for noisy in ("uvicorn.access", "httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # opensearch-py 는 연결 실패마다 traceback 을 WARNING 으로 남긴다. 실패는 앱 코드가 한 줄로 기록한다.
    logging.getLogger("opensearch").setLevel(logging.ERROR)


access_log = logging.getLogger("app.access")


class RequestContextMiddleware:
    """X-Request-Id 를 받거나(형식 검증) ULID 로 만들고, 응답 헤더와 접근 로그에 남긴다.
    미처리 예외는 여기서 500 표준 오류로 바꿔 request_id 를 유지한다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = None
        for k, v in scope.get("headers", []):
            if k == b"x-request-id":
                incoming = v.decode("latin-1")
                break
        rid = incoming if incoming and _REQ_ID_RE.match(incoming) else new_ulid()
        token = request_id_var.set(rid)
        user_token = user_id_var.set(None)
        start = time.perf_counter()
        status_holder = {"status": 500, "started": False}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["started"] = True
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            logging.getLogger("app.error").exception("unhandled_error", extra={"event": "unhandled_error"})
            if not status_holder["started"]:
                from app.core.errors import error_response

                resp = error_response(500, "internal_error", "서버 내부 오류가 발생했습니다.")
                await resp(scope, receive, _send)
        finally:
            access_log.info(
                "request",
                extra={
                    "event": "request",
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_holder["status"],
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            request_id_var.reset(token)
            user_id_var.reset(user_token)

"""표준 오류 형식 (설계서 8.1)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        retryable: bool = False,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details
        self.headers = headers


def error_body(code: str, message: str, retryable: bool = False, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_var.get(),
            "retryable": retryable,
            "details": details,
        }
    }


def error_response(
    status: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(error_body(code, message, retryable, details), status_code=status, headers=headers)


# 자주 쓰는 오류
def not_found(code: str, message: str = "요청한 자원을 찾을 수 없습니다.") -> AppError:
    return AppError(404, code, message)


def collection_not_found() -> AppError:
    return AppError(404, "collection_not_found", "요청한 컬렉션을 찾을 수 없습니다.")


def document_not_found() -> AppError:
    return AppError(404, "document_not_found", "요청한 문서를 찾을 수 없습니다.")


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden_role",
    404: "not_found",
    405: "method_not_allowed",
    413: "file_too_large",
    415: "unsupported_media_type",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status >= 500:
            log.error("app_error", extra={"event": "app_error", "code": exc.code, "error": exc.message})
        return error_response(exc.status, exc.code, exc.message, exc.retryable, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = jsonable_encoder(exc.errors(), exclude={"input", "ctx", "url"})
        if any(e.get("type") == "json_invalid" for e in errors):
            return error_response(400, "bad_request", "요청 본문을 해석할 수 없습니다.", details=errors)
        return error_response(422, "validation_error", "요청 값이 올바르지 않습니다.", details=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))

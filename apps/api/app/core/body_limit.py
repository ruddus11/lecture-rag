"""multipart 파싱 전에 본문을 제한해 임시 디스크·메모리 남용을 막는다."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 20 MiB PDF + multipart 헤더 여유. 파일 자체 20 MiB 제한은 FileStore가 검사한다.
MAX_BODY_BYTES = 21 * 1024 * 1024


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from app.core.errors import error_response

        async def reject() -> None:
            await error_response(413, "file_too_large", "요청 본문이 허용 크기를 넘습니다.")(
                scope, receive, send
            )

        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await reject()
                        return
                except ValueError:
                    pass  # 신뢰하지 않는 길이 대신 실제 수신 바이트를 검사한다.
        body: list[Message] = []
        total = 0
        while True:
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await reject()
                return
            body.append(message)
            if message["type"] == "http.disconnect" or not message.get("more_body", False):
                break
        iterator = iter(body)

        # 이후 disconnect 감시 요청은 원래 receive로 전달한다.
        async def buffered_receive() -> Message:
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        await self.app(scope, buffered_receive, send)

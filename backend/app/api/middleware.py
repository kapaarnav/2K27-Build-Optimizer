import re
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.request_context import request_id_var

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = ""
        for key, value in scope.get("headers", []):
            if key.lower() == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if _REQUEST_ID.fullmatch(incoming) else str(uuid4())
        token = request_id_var.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)

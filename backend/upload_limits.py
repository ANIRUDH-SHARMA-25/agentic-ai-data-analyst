"""Bound upload request bodies before the multipart parser allocates/spools them."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MULTIPART_OVERHEAD_BYTES = 64 * 1024


class UploadBodyLimit:
    """Buffer at most the file limit plus bounded multipart header overhead.

    Actual received bytes are checked even when Content-Length is absent or
    inaccurate. Other endpoints pass through without buffering.
    """

    def __init__(self, app: ASGIApp, *, max_upload_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") != "/upload"):
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        length = headers.get(b"content-length")
        if length is not None:
            try:
                declared_size = int(length)
                if declared_size < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse({"detail": "Invalid Content-Length header."}, 400)(scope, receive, send)
                return
            if declared_size > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return
        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"detail": "Upload request exceeds the size limit."}, 413)(scope, receive, send)

"""Bound upload and analysis bodies before multipart/JSON parsing."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MULTIPART_OVERHEAD_BYTES = 64 * 1024
ANALYSIS_BODY_BYTES = 32 * 1024


class UploadBodyLimit:
    """Buffer at most the file limit plus bounded multipart header overhead.

    Actual received bytes are checked even when Content-Length is absent or
    inaccurate. Analysis JSON is capped separately before parsing; other
    endpoints pass through without buffering.
    """

    def __init__(self, app: ASGIApp, *, max_upload_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") not in {"/upload", "/analyze"}):
            await self.app(scope, receive, send)
            return
        is_analysis = scope["path"].rstrip("/") == "/analyze"
        body_limit = ANALYSIS_BODY_BYTES if is_analysis else self.max_body_bytes
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
            if declared_size > body_limit:
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
            if received > body_limit:
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
        kind = "Analysis" if scope["path"].rstrip("/") == "/analyze" else "Upload"
        await JSONResponse({"detail": f"{kind} request exceeds the size limit."}, 413)(scope, receive, send)

"""Bound the raw request body before OCR or JSON parsing."""
import hmac
from fastapi.responses import JSONResponse

class RequestGuard:
    """Bound JSON body size before parsing; authenticate all feature endpoints."""
    def __init__(self, app, token="", maximum=1_000_000):
        self.app, self.token, self.maximum = app, token, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send); return
        headers = dict(scope["headers"])
        if scope["method"] != "OPTIONS" and scope["path"] != "/health" and self.token:
            supplied = headers.get(b"authorization", b"")
            if not hmac.compare_digest(supplied, ("Bearer " + self.token).encode("utf-8")):
                await JSONResponse({"error":{"code":"UNAUTHORIZED","message":"A backend access token is required."}},401)(scope,receive,send)
                return
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect": return
            body.extend(event.get("body", b""))
            if len(body) > self.maximum:
                await JSONResponse({"error":{"code":"BODY_TOO_LARGE","message":"The request exceeds the configured upload limit."}},413)(scope,receive,send)
                return
            if not event.get("more_body", False): break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type":"http.request","body":bytes(body),"more_body":False}
            return await receive()
        await self.app(scope,bounded_receive,send)


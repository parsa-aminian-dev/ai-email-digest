from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.digest.config.settings import Settings
from src.digest.logging import configure_logging, event
from src.digest.models import DigestRequest, ProcessBatchRequest
from src.digest.service import DigestService
from src.digest.storage.repository import BusyJobError


class PrivateRequestMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        key = self.settings.api_key.get_secret_value()
        headers = dict(scope.get("headers", []))
        if scope["path"] != "/health" and key:
            supplied = headers.get(b"x-api-key", b"").decode("utf-8", errors="replace")
            if not secrets.compare_digest(supplied.encode(), key.encode()):
                await JSONResponse({"detail": "Unauthorized"}, status_code=401)(
                    scope, receive, send
                )
                return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.settings.max_request_size_bytes:
                await JSONResponse({"detail": "Request too large"}, status_code=413)(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def scheduler(service: DigestService) -> None:
    while True:
        try:
            await asyncio.to_thread(service.run_scheduled)
        except BusyJobError:
            pass
        except Exception as error:
            event("scheduler_failed", error_class=type(error).__name__)
        await asyncio.sleep(service.settings.poll_seconds)


def create_app(settings: Settings | None = None, service: DigestService | None = None) -> FastAPI:
    configured = settings or Settings()
    configure_logging(configured.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.service = service or DigestService(configured)
        current: DigestService = app.state.service
        task = None
        if configured.demo_mode:
            await asyncio.to_thread(current.ingest)
            now = datetime.now(UTC)
            result = await asyncio.to_thread(
                current.generate_digest, now - timedelta(days=1), now, deliver=True
            )
            app.state.demo_digest = result
        if configured.scheduler_enabled:
            task = asyncio.create_task(scheduler(current))
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            current.close()

    app = FastAPI(title="AI Email Digest", version="1.0.0", lifespan=lifespan)
    app.add_middleware(PrivateRequestMiddleware, settings=configured)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "Invalid request schema. See /docs."}, status_code=422)

    @app.exception_handler(BusyJobError)
    async def busy_job(request: Request, error: BusyJobError) -> JSONResponse:
        return JSONResponse({"detail": "Job already running; retry later"}, status_code=409)

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    def active(request: Request) -> DigestService:
        return request.app.state.service

    @app.post("/emails/process")
    @app.post("/process", include_in_schema=False)
    def process_batch(payload: ProcessBatchRequest, request: Request) -> dict[str, Any]:
        return active(request).process_batch(payload.messages)

    @app.post("/emails/ingest")
    def ingest(request: Request) -> dict[str, Any]:
        return active(request).ingest()

    @app.post("/digests")
    def digest(payload: DigestRequest, request: Request) -> dict[str, Any]:
        try:
            result = active(request).generate_digest(
                payload.start, payload.end, deliver=payload.deliver
            )
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Invalid period or delivery configuration"
            ) from None
        except BusyJobError:
            raise
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Digest delivery failed; inspect delivery state before retrying",
            ) from None
        return {
            "digest": result.model_dump(mode="json"),
            "delivery": active(request).repository.delivery_state(result.id),
        }

    @app.post("/jobs/tick")
    def tick(request: Request) -> dict[str, Any]:
        try:
            return active(request).run_scheduled()
        except BusyJobError:
            raise
        except Exception:
            raise HTTPException(
                status_code=503, detail="Scheduled job failed; inspect local delivery status"
            ) from None

    @app.get("/items")
    def items(request: Request, limit: int = Query(default=20, ge=1, le=500)) -> dict[str, Any]:
        return {
            "items": [
                item.model_dump(mode="json")
                for item in active(request).repository.list_recent(limit)
            ]
        }

    @app.get("/demo")
    def demo(request: Request) -> dict[str, Any]:
        if not configured.demo_mode:
            raise HTTPException(status_code=404, detail="Demo disabled")
        return {"digest": request.app.state.demo_digest.model_dump(mode="json")}

    @app.get("/demo/digest", response_class=HTMLResponse)
    def demo_html(request: Request) -> HTMLResponse:
        if not configured.demo_mode:
            raise HTTPException(status_code=404, detail="Demo disabled")
        return HTMLResponse(
            request.app.state.demo_digest.html,
            headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                "Cache-Control": "no-store",
            },
        )

    return app


app = create_app()

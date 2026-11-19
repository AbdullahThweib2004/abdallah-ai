import uuid

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.limits import log_rate_limit
from app.models.chat import ChatRequest, RateLimitResponse
from app.services.chat_messages import message
from app.services.chat_service import chat_events
from app.services.rate_limit import LIMIT_NAMES

router = APIRouter(tags=["chat"])


def _client_key(request: Request) -> str:
    # Direct peer address. Behind a proxy (step 10) this must read the trusted forwarded header.
    return request.client.host if request.client else "unknown"


@router.post(
    "/chat",
    response_class=StreamingResponse,
    response_model=None,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Server-Sent Events stream"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": RateLimitResponse},
    },
)
async def chat(body: ChatRequest, request: Request) -> StreamingResponse | JSONResponse:
    decision = request.app.state.rate_limiter.check(_client_key(request))
    if not decision.allowed:
        assert decision.reason is not None
        log_rate_limit(
            "app", LIMIT_NAMES[decision.reason], route="chat", retry_after=decision.retry_after
        )
        payload = RateLimitResponse(
            detail=message(decision.reason, body.ui_language), code=decision.reason
        )
        return JSONResponse(
            payload.model_dump(),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(decision.retry_after or 60)},
        )

    events = chat_events(
        uuid.uuid4().hex,
        body,
        provider=request.app.state.llm,
        retriever=request.app.state.retriever,
        identity=request.app.state.identity,
        settings=request.app.state.settings,
        projects=request.app.state.projects,
        cache=request.app.state.answer_cache,
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

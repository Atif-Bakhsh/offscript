"""Run locally: python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent_runner import AgentRunner
from .calendar_store import SIMULATION_CONTEXT, initial_slots
from .config import HarnessError, Settings, load_settings
from .models import (
    CompareRequest,
    ConfirmationRequest,
    ConfirmationResponse,
    ErrorDetail,
    ErrorPayload,
    ErrorResponse,
    HealthResponse,
    PromptDiffResponse,
    ScenarioCompareResponse,
    ScenariosResponse,
    SuiteEvaluationReport,
    SuiteRequest,
)
from .prompts import PROMPT_DIFF_RULES, PROMPT_V1, PROMPT_V2
from .scenarios import SCENARIOS


def create_app(settings: Settings | None = None, runner: AgentRunner | None = None) -> FastAPI:
    settings = settings or load_settings()
    runner = runner or AgentRunner(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.resolve_mode()  # Fail startup on an explicitly misconfigured live mode.
        yield
        runner.sessions.clear()

    app = FastAPI(
        title="OffScript",
        version="1.0.0",
        lifespan=lifespan,
        description="English voice-agent transcript simulation, prompt evaluation, and guarded mock booking. Local, single-worker harness.",
    )
    app.state.runner = runner
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(HarnessError)
    async def harness_error(request: Request, exc: HarnessError) -> JSONResponse:
        body = ErrorResponse(error=ErrorPayload(code=exc.code, message=exc.message))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorPayload(
                code="INVALID_REQUEST",
                message="The request does not match the English API contract.",
                details=[
                    ErrorDetail(field=".".join(str(p) for p in e["loc"]), message=e["msg"])
                    for e in exc.errors()
                ],
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(exclude_none=True))

    @app.get(
        "/api/health",
        response_model=HealthResponse,
        responses={
            503: {
                "model": ErrorResponse,
                "description": "API_KEY_REQUIRED: live mode is missing the selected provider key.",
            },
        },
    )
    async def health() -> HealthResponse:
        mode = settings.resolve_mode()
        return HealthResponse.model_validate(
            {
                "status": "ok",
                "mode": mode,
                "provider": settings.provider if mode != "verified_replay" else None,
                "model": settings.model if mode != "verified_replay" else None,
                "storage": "conversation-local in-memory",
                "durable": False,
                "workers": 1,
                "session_ttl_seconds": settings.session_ttl_seconds,
            }
        )

    @app.get("/api/scenarios", response_model=ScenariosResponse)
    async def scenarios() -> ScenariosResponse:
        return ScenariosResponse.model_validate(
            {
                "scenarios": [s.public() for s in SCENARIOS],
                "initial_calendar": initial_slots(),
                "simulation_context": SIMULATION_CONTEXT,
            }
        )

    @app.get("/api/prompt-diff", response_model=PromptDiffResponse)
    async def prompt_diff() -> PromptDiffResponse:
        return PromptDiffResponse.model_validate(
            {"prompt_v1": PROMPT_V1, "prompt_v2": PROMPT_V2, "rules": PROMPT_DIFF_RULES}
        )

    @app.post(
        "/api/compare-turn1",
        response_model=ScenarioCompareResponse,
        responses={
            409: {
                "model": ErrorResponse,
                "description": "LIVE_MODE_REQUIRED: custom input is unsupported in replay.",
            },
            422: {
                "model": ErrorResponse,
                "description": "INVALID_REQUEST: request validation failed.",
            },
            502: {
                "model": ErrorResponse,
                "description": "Provider refusal, authentication, model availability, output validation, or request failure.",
            },
            503: {
                "model": ErrorResponse,
                "description": "API_KEY_REQUIRED or SESSION_CAPACITY_REACHED.",
            },
            504: {
                "model": ErrorResponse,
                "description": "PROVIDER_TIMEOUT: bounded provider retries exhausted.",
            },
        },
    )
    async def compare_turn1(request: CompareRequest) -> ScenarioCompareResponse:
        return await runner.compare(request)

    @app.post(
        "/api/simulate-turn2",
        response_model=ConfirmationResponse,
        responses={
            404: {
                "model": ErrorResponse,
                "description": "CONVERSATION_NOT_FOUND: start a new comparison.",
            },
            409: {
                "model": ErrorResponse,
                "description": "CONVERSATION_COMPLETED: callback already booked.",
            },
            410: {
                "model": ErrorResponse,
                "description": "SESSION_EXPIRED: start a new comparison.",
            },
            422: {
                "model": ErrorResponse,
                "description": "INVALID_REQUEST: request validation failed.",
            },
            502: {
                "model": ErrorResponse,
                "description": "Provider refusal, authentication, model availability, output validation, or request failure.",
            },
            504: {
                "model": ErrorResponse,
                "description": "PROVIDER_TIMEOUT: bounded provider retries exhausted.",
            },
        },
    )
    async def simulate_turn2(request: ConfirmationRequest) -> ConfirmationResponse:
        return await runner.confirm(request.conversation_id, request.caller_text)

    @app.post(
        "/api/evaluate-suite",
        response_model=SuiteEvaluationReport,
        responses={
            422: {
                "model": ErrorResponse,
                "description": "INVALID_REQUEST: request validation failed.",
            },
            502: {
                "model": ErrorResponse,
                "description": "Provider refusal, authentication, model availability, output validation, or request failure.",
            },
            503: {
                "model": ErrorResponse,
                "description": "API_KEY_REQUIRED: live mode is missing the selected provider key.",
            },
            504: {
                "model": ErrorResponse,
                "description": "PROVIDER_TIMEOUT: bounded provider retries exhausted.",
            },
        },
    )
    async def evaluate_suite(request: SuiteRequest | None = None) -> SuiteEvaluationReport:
        return await runner.evaluate_suite(request.execution_mode if request else None)

    return app


app = create_app()

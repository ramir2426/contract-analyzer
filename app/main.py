import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import ContractAnalyzerError
from app.models.responses import ErrorResponse, ErrorDetail
from app.api.v1 import contracts, health

# Configure structured JSON logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("contract_analyzer.starting", version=settings.version, environment=settings.environment)
    yield
    log.info("contract_analyzer.stopping")


app = FastAPI(
    title="Contract Analyzer API",
    description="LLM-powered contract analysis. Upload any PDF contract and get plain-language risk flags.",
    version=settings.version,
    lifespan=lifespan,
)


# ─── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(ContractAnalyzerError)
async def contract_error_handler(request: Request, exc: ContractAnalyzerError):
    log.warning("request.error", error_code=exc.error_code, message=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.error_code,
                message=str(exc),
                request_id=request.headers.get("X-Request-ID"),
            )
        ).model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    log.error("request.unhandled_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(code="INTERNAL_ERROR", message="An unexpected error occurred.")
        ).model_dump(mode="json"),
    )


# ─── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(contracts.router, prefix="/api/v1", tags=["contracts"])

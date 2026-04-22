import json
import uuid
import asyncio
from datetime import datetime
import structlog

from fastapi import APIRouter, File, UploadFile, Header, Form

from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMService
from app.models.responses import (
    AnalysisResult,
    JobStatusResponse,
    JobStatus,
    ConversationResponse,
    ConversationMessage,
    CostEstimate,
)
from app.models.requests import ConversationRequest
from app.exceptions import JobNotFoundError, SessionNotFoundError, ContractAnalyzerError
from app.providers.registry import get_provider, PROVIDER_CAPABILITIES

router = APIRouter()
log = structlog.get_logger()

# In-memory stores — replaced with Redis in Phase 7
_job_store: dict = {}
_session_store: dict = {}


def _get_provider_from_header(x_llm_provider: str | None) -> str:
    provider = x_llm_provider or "ollama"
    if provider not in PROVIDER_CAPABILITIES:
        from app.exceptions import InvalidProviderError
        raise InvalidProviderError(f"Unknown provider '{provider}'. Supported: {list(PROVIDER_CAPABILITIES)}")
    return provider


# ── POST /contracts ────────────────────────────────────────────────────────────

@router.post("/contracts", response_model=dict, status_code=202)
async def upload_contract(
    file: UploadFile = File(...),
    language: str = Form(default="auto"),
    contract_type: str = Form(default="auto"),
    focus_areas: str = Form(default="[]"),        # JSON array as string
    model_override: str | None = Form(default=None),
    x_llm_provider: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    """
    Upload a contract PDF and start analysis.
    Returns a job_id immediately. Poll GET /contracts/{id}/status.

    - X-LLM-Provider: claude | openai | gemini | ollama (default: ollama)
    - X-API-Key: your API key (required for all providers except ollama)
    """
    provider = _get_provider_from_header(x_llm_provider)
    pdf_bytes = await file.read()

    # Validate before spawning — gives the client a synchronous 422 for bad files
    from app.services.pdf_service import PDFService
    PDFService()._validate(pdf_bytes, file.filename or "contract.pdf")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _job_store[job_id] = {
        "status": JobStatus.QUEUED,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "result": None,
        "error": None,
        "progress_message": "Queued for analysis...",
    }

    asyncio.create_task(
        _run_analysis(
            job_id=job_id,
            pdf_bytes=pdf_bytes,
            provider=provider,
            api_key=x_api_key,
            language=language,
            contract_type=contract_type,
            model_override=model_override,
        )
    )

    log.info("contract.submitted", job_id=job_id, provider=provider, filename=file.filename)

    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Analysis started. Poll GET /api/v1/contracts/{job_id}/status",
    }


async def _run_analysis(
    job_id: str,
    pdf_bytes: bytes,
    provider: str,
    api_key: str | None,
    language: str,
    contract_type: str,
    model_override: str | None,
):
    """Background task — runs the analysis pipeline and updates job state."""
    service = AnalysisService()

    async def update_progress(message: str):
        if job_id in _job_store:
            _job_store[job_id]["status"] = JobStatus.ANALYZING
            _job_store[job_id]["progress_message"] = message

    try:
        _job_store[job_id]["status"] = JobStatus.EXTRACTING
        _job_store[job_id]["progress_message"] = "Extracting PDF..."

        result = await service.analyze(
            pdf_bytes=pdf_bytes,
            provider=provider,
            api_key=api_key,
            output_language=language if language != "auto" else "en",
            contract_type=contract_type,
            model_override=model_override,
            progress_callback=update_progress,
        )

        _job_store[job_id]["status"] = JobStatus.COMPLETE
        _job_store[job_id]["completed_at"] = datetime.utcnow()
        _job_store[job_id]["result"] = result.model_dump(mode="json")
        _job_store[job_id]["progress_message"] = "Analysis complete."

        # Store result for conversation (session keyed by job_id)
        _session_store[job_id] = {
            "analysis": result.model_dump(mode="json"),
            "history": [],
        }

    except Exception as e:
        log.error("analysis.failed", job_id=job_id, error=str(e))
        _job_store[job_id]["status"] = JobStatus.FAILED
        _job_store[job_id]["error"] = str(e)
        _job_store[job_id]["progress_message"] = f"Analysis failed: {e}"


# ── GET /contracts/{id}/status ─────────────────────────────────────────────────

@router.get("/contracts/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in _job_store:
        raise JobNotFoundError(f"Job '{job_id}' not found.")

    job = _job_store[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress_message=job.get("progress_message"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
        error=job.get("error"),
    )


# ── GET /contracts/{id}/result ─────────────────────────────────────────────────

@router.get("/contracts/{job_id}/result", response_model=AnalysisResult)
async def get_job_result(job_id: str):
    if job_id not in _job_store:
        raise JobNotFoundError(f"Job '{job_id}' not found.")

    job = _job_store[job_id]

    if job["status"] != JobStatus.COMPLETE:
        raise ContractAnalyzerError(
            f"Job is not complete yet. Current status: {job['status']}"
        )

    return AnalysisResult(**job["result"])


# ── POST /contracts/estimate ───────────────────────────────────────────────────

@router.post("/contracts/estimate", response_model=CostEstimate)
async def estimate_cost(
    file: UploadFile = File(...),
    x_llm_provider: str | None = Header(default=None),
    x_model_override: str | None = Header(default=None),
):
    """Estimate token count and cost BEFORE running analysis. No LLM calls made."""
    provider = _get_provider_from_header(x_llm_provider)
    capabilities = get_provider(provider)
    pdf_bytes = await file.read()

    # Rough estimate: 1 token ≈ 4 bytes for English/German text
    estimated_tokens = len(pdf_bytes) // 4

    # Cost per 1M tokens (approximate, as of 2026)
    cost_per_million = {
        "claude": 3.0,    # claude-3-5-sonnet input
        "openai": 5.0,    # gpt-4o input
        "gemini": 1.25,   # gemini-1.5-pro input
        "ollama": 0.0,    # free
    }

    cost_per_token = cost_per_million.get(provider, 0) / 1_000_000
    estimated_cost = estimated_tokens * cost_per_token * 4   # x4 for multi-pass

    return CostEstimate(
        estimated_tokens=estimated_tokens,
        estimated_cost_usd=estimated_cost if provider != "ollama" else None,
        provider=provider,
        model=x_model_override or capabilities.default_model,
        note=(
            "Estimate only. Multi-pass pipeline uses ~4x the raw document tokens."
            if provider != "ollama"
            else "Ollama is free — no cost."
        ),
    )


# ── POST /contracts/{id}/messages — Conversation (Phase 8) ────────────────────

@router.post("/contracts/{job_id}/messages", response_model=ConversationResponse)
async def send_message(
    job_id: str,
    request: ConversationRequest,
    x_llm_provider: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    """
    Ask a follow-up question about a specific contract.
    The full analysis context is injected automatically.

    Example questions:
    - "What does clause § 7 mean in plain language?"
    - "Write me a message asking them to remove clause 12"
    - "Is the deposit amount legal under German law?"
    """
    if job_id not in _session_store:
        raise SessionNotFoundError(
            f"No analysis session found for job '{job_id}'. Run analysis first."
        )

    session = _session_store[job_id]
    provider = _get_provider_from_header(x_llm_provider)

    # Inject full contract context into the system message
    analysis_summary = json.dumps({
        "contract_type": session["analysis"].get("contract_type"),
        "key_terms": session["analysis"].get("key_terms"),
        "flags": session["analysis"].get("flags", [])[:10],   # Top 10 flags
        "summary": session["analysis"].get("summary"),
    }, indent=2)

    system_message = f"""You are a contract advisor helping a user understand their contract.
You have already analyzed this contract. Here is the analysis:

{analysis_summary}

Answer questions clearly and in plain language. If asked to draft text (e.g., a negotiation letter),
write it in the appropriate language for the contract. Always be helpful and practical.
If a question requires a lawyer, say so clearly."""

    history = session.get("history", [])
    messages = [{"role": "system", "content": system_message}]
    messages.extend(history)
    messages.append({"role": "user", "content": request.message})

    llm_service = LLMService()
    response = await llm_service.complete(
        messages=messages,
        provider=provider,
        api_key=x_api_key,
    )

    user_msg = ConversationMessage(role="user", content=request.message)
    assistant_msg = ConversationMessage(role="assistant", content=response.content)

    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": response.content})
    session["history"] = history[-20:]   # Keep last 20 messages to avoid context overflow

    return ConversationResponse(
        session_id=job_id,
        message=assistant_msg,
        history=[user_msg, assistant_msg],
    )

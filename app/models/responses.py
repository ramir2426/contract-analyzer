from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


# ─── Enums ────────────────────────────────────────────────────────────────────

class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FlagSeverity(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class LegalStatus(StrEnum):
    VOID = "void"                           # Unenforceable by law — user can ignore
    VOIDABLE = "voidable"                   # Enforceable unless challenged
    UNFAVORABLE_BUT_VALID = "unfavorable_but_valid"  # Must negotiate
    STANDARD = "standard"                   # Normal, expected clause


class RecommendedAction(StrEnum):
    NONE_REQUIRED = "none_required"         # For void clauses
    NEGOTIATE = "negotiate"
    CONSULT_LAWYER = "consult_lawyer"
    WALK_AWAY = "walk_away"
    ACCEPT = "accept"                       # For green flags


class FlagCategory(StrEnum):
    TERMINATION = "termination"
    FINANCIAL = "financial"
    LIABILITY = "liability"
    PRIVACY = "privacy"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    DISPUTE_RESOLUTION = "dispute_resolution"
    RENEWAL = "renewal"
    REPAIRS = "repairs"
    NON_COMPETE = "non_compete"
    WORKING_CONDITIONS = "working_conditions"
    OTHER = "other"


class JobStatus(StrEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    FAILED = "failed"


# ─── Contract flag ─────────────────────────────────────────────────────────────

class ContractFlag(BaseModel):
    id: str = Field(default_factory=lambda: f"flag_{uuid.uuid4().hex[:8]}")
    severity: FlagSeverity
    legal_status: LegalStatus
    category: FlagCategory
    title: str
    explanation: str                        # Plain-language explanation
    what_this_means: str                    # Practical consequence for the user
    clause_reference: str | None = None     # e.g., "§ 4.2" or "Section 12"
    raw_text: str | None = None             # Exact text from contract
    legal_source: str | None = None         # e.g., "BGB §307, BGH VIII ZR 215/12"
    action: RecommendedAction
    negotiation_suggestion: str | None = None  # Proposed replacement wording


class PositiveClause(BaseModel):
    title: str
    explanation: str
    category: FlagCategory
    clause_reference: str | None = None


# ─── Key metadata extracted from contract ─────────────────────────────────────

class ContractParties(BaseModel):
    first_party: str | None = None          # e.g., "Tenant: Max Mustermann"
    second_party: str | None = None         # e.g., "Landlord: ABC GmbH"
    additional_parties: list[str] = Field(default_factory=list)


class KeyTerms(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    notice_period: str | None = None
    monthly_amount: str | None = None
    deposit: str | None = None
    auto_renewal: bool | None = None
    auto_renewal_date: str | None = None
    jurisdiction: str | None = None
    governing_law: str | None = None
    additional_terms: dict[str, str] = Field(default_factory=dict)


# ─── Analysis result ───────────────────────────────────────────────────────────

class AnalysisMetadata(BaseModel):
    provider: str
    model: str
    prompt_version: str                     # Track which prompt produced this result
    processing_time_ms: int
    pdf_pages: int | None = None
    total_tokens_used: int | None = None
    extraction_method: str | None = None    # "pdfplumber", "pypdf", "ocr", "native"
    pipeline_passes: int = 4


class AnalysisResult(BaseModel):
    analysis_id: str = Field(default_factory=lambda: f"ana_{uuid.uuid4().hex[:12]}")
    contract_type: str
    detected_language: str
    jurisdiction: str | None = None
    parties: ContractParties
    key_terms: KeyTerms
    summary: str
    summary_plain: str                      # ELI5 version — 2-3 sentences max
    overall_risk: RiskLevel
    flags: list[ContractFlag]
    positive_clauses: list[PositiveClause] = Field(default_factory=list)
    missing_required_clauses: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    metadata: AnalysisMetadata
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Job state ─────────────────────────────────────────────────────────────────

class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress_message: str | None = None     # e.g., "Analyzing section 3 of 8..."
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


# ─── Conversation ──────────────────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    role: str                               # "user" or "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationResponse(BaseModel):
    session_id: str
    message: ConversationMessage
    history: list[ConversationMessage]


# ─── Cost estimate ─────────────────────────────────────────────────────────────

class CostEstimate(BaseModel):
    estimated_tokens: int
    estimated_cost_usd: float | None = None  # None for Ollama (free)
    provider: str
    model: str
    note: str | None = None


# ─── Error response ────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

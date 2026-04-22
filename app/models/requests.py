from enum import StrEnum

from pydantic import BaseModel, Field


class LLMProvider(StrEnum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class OutputLanguage(StrEnum):
    ENGLISH = "en"
    GERMAN = "de"
    FRENCH = "fr"
    AUTO = "auto"


class AnalyzeFormData(BaseModel):
    """Parsed from form fields accompanying the file upload."""

    provider: LLMProvider = LLMProvider.OLLAMA
    language: OutputLanguage = OutputLanguage.AUTO
    contract_type: str = "auto"
    focus_areas: list[str] = Field(default_factory=list)
    model_override: str | None = None


class ConversationRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class EstimateRequest(BaseModel):
    provider: LLMProvider
    model_override: str | None = None

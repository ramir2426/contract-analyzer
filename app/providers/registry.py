from dataclasses import dataclass, field


@dataclass
class ProviderCapabilities:
    supports_native_pdf: bool
    requires_api_key: bool
    default_model: str
    supported_models: list[str] = field(default_factory=list)


# Populated fully in Phase 3 — stub values let Phase 1 boot
PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "claude": ProviderCapabilities(
        supports_native_pdf=True,
        requires_api_key=True,
        default_model="claude-3-5-sonnet-20241022",
        supported_models=["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    ),
    "openai": ProviderCapabilities(
        supports_native_pdf=False,
        requires_api_key=True,
        default_model="gpt-4o",
        supported_models=["gpt-4o", "gpt-4o-mini"],
    ),
    "gemini": ProviderCapabilities(
        supports_native_pdf=False,
        requires_api_key=True,
        default_model="gemini-1.5-pro",
        supported_models=["gemini-1.5-pro", "gemini-1.5-flash"],
    ),
    "ollama": ProviderCapabilities(
        supports_native_pdf=False,
        requires_api_key=False,
        default_model="llama3.2",
        supported_models=["llama3.2", "llama3.1", "mistral"],
    ),
}

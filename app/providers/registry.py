from dataclasses import dataclass, field


@dataclass
class ProviderCapabilities:
    litellm_prefix: str  # How LiteLLM identifies this provider
    supports_native_pdf: bool  # Can accept PDF bytes directly?
    requires_api_key: bool
    default_model: str
    supported_models: list[str] = field(default_factory=list)
    base_url: str | None = None  # For Ollama and self-hosted


PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "claude": ProviderCapabilities(
        litellm_prefix="anthropic",
        supports_native_pdf=True,
        requires_api_key=True,
        default_model="claude-3-5-sonnet-20241022",
        supported_models=[
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
            "claude-opus-4-6",
        ],
    ),
    "openai": ProviderCapabilities(
        litellm_prefix="openai",
        supports_native_pdf=False,
        requires_api_key=True,
        default_model="gpt-4o",
        supported_models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    ),
    "gemini": ProviderCapabilities(
        litellm_prefix="gemini",
        supports_native_pdf=False,
        requires_api_key=True,
        default_model="gemini-1.5-pro",
        supported_models=["gemini-1.5-pro", "gemini-1.5-flash"],
    ),
    "ollama": ProviderCapabilities(
        litellm_prefix="ollama",
        supports_native_pdf=False,
        requires_api_key=False,
        default_model="llama3.2",
        supported_models=["llama3.2", "llama3.1", "mistral", "mixtral"],
        base_url="http://localhost:11434",  # Overridden to http://ollama:11434 in Docker
    ),
}


def get_provider(provider: str) -> ProviderCapabilities:
    if provider not in PROVIDER_CAPABILITIES:
        raise KeyError(f"Unknown provider '{provider}'. Supported: {list(PROVIDER_CAPABILITIES)}")
    return PROVIDER_CAPABILITIES[provider]

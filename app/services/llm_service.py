import base64
from dataclasses import dataclass

import litellm
import structlog

from app.exceptions import LLMAuthError, LLMRateLimitError, LLMUnavailableError, MissingAPIKeyError
from app.providers.registry import get_provider

log = structlog.get_logger()

# Disable LiteLLM's verbose logging — we handle our own
litellm.set_verbose = False


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int | None
    provider: str


class LLMService:
    async def complete(
        self,
        messages: list[dict],
        provider: str,
        api_key: str | None,
        model_override: str | None = None,
    ) -> LLMResponse:
        """
        Make an LLM completion request.

        The api_key is the user's own key (BYOK).
        It is passed per-request and never stored anywhere.
        """
        capabilities = get_provider(provider)

        if capabilities.requires_api_key and not api_key:
            raise MissingAPIKeyError(
                f"Provider '{provider}' requires an API key. " f"Pass it via the X-API-Key header."
            )

        model = model_override or capabilities.default_model
        litellm_model = f"{capabilities.litellm_prefix}/{model}"

        kwargs: dict = {
            "model": litellm_model,
            "messages": messages,
            "temperature": 0.1,  # Low for consistent analysis
            "response_format": {"type": "json_object"},
        }

        if api_key:
            kwargs["api_key"] = api_key  # BYOK: injected per-request, never stored

        if capabilities.base_url:
            kwargs["api_base"] = capabilities.base_url

        log.info("llm.request", provider=provider, model=model, message_count=len(messages))

        try:
            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content or ""
            tokens = getattr(response.usage, "total_tokens", None)

            log.info("llm.response", provider=provider, model=model, tokens=tokens, content_length=len(content))

            return LLMResponse(
                content=content,
                model=model,
                tokens_used=tokens,
                provider=provider,
            )

        except litellm.AuthenticationError as e:
            raise LLMAuthError(f"API key rejected by {provider}: {e}") from e
        except litellm.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit hit for {provider}: {e}") from e
        except litellm.ServiceUnavailableError as e:
            raise LLMUnavailableError(f"{provider} is unavailable: {e}") from e
        except Exception as e:
            log.error("llm.unexpected_error", provider=provider, error=str(e))
            raise LLMUnavailableError(f"Unexpected LLM error: {e}") from e

    def build_pdf_message_claude(self, pdf_bytes: bytes) -> dict:
        """
        Build a message that sends a PDF natively to Claude (no local extraction needed).
        Claude understands the PDF directly — other providers need extracted text.
        """
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
        return {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                }
            ],
        }

class ContractAnalyzerError(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"


class InvalidPDFError(ContractAnalyzerError):
    status_code = 422
    error_code = "INVALID_PDF"


class PDFTooLargeError(ContractAnalyzerError):
    status_code = 413
    error_code = "PDF_TOO_LARGE"


class ScannedPDFError(ContractAnalyzerError):
    """Raised when OCR is needed but tesseract is not installed."""

    status_code = 422
    error_code = "SCANNED_PDF_REQUIRES_OCR"


class InvalidProviderError(ContractAnalyzerError):
    status_code = 422
    error_code = "INVALID_PROVIDER"


class MissingAPIKeyError(ContractAnalyzerError):
    status_code = 401
    error_code = "MISSING_API_KEY"


class LLMAuthError(ContractAnalyzerError):
    """User's BYOK key was rejected by the provider."""

    status_code = 401
    error_code = "LLM_AUTH_FAILED"


class LLMRateLimitError(ContractAnalyzerError):
    status_code = 429
    error_code = "LLM_RATE_LIMITED"


class LLMUnavailableError(ContractAnalyzerError):
    status_code = 503
    error_code = "LLM_UNAVAILABLE"


class ParseError(ContractAnalyzerError):
    """LLM returned output that could not be parsed into the expected schema."""

    status_code = 500
    error_code = "PARSE_ERROR"


class JobNotFoundError(ContractAnalyzerError):
    status_code = 404
    error_code = "JOB_NOT_FOUND"


class SessionNotFoundError(ContractAnalyzerError):
    status_code = 404
    error_code = "SESSION_NOT_FOUND"

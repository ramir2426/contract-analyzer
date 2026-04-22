import asyncio

from app.services.analysis_service import AnalysisService
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2)
def analyze_contract_task(
    self,
    pdf_bytes_hex: str,  # bytes serialized as hex for JSON compatibility
    provider: str,
    api_key: str | None,
    language: str,
    contract_type: str,
    model_override: str | None,
):
    pdf_bytes = bytes.fromhex(pdf_bytes_hex)
    service = AnalysisService()

    result = asyncio.run(
        service.analyze(
            pdf_bytes=pdf_bytes,
            provider=provider,
            api_key=api_key,
            output_language=language,
            contract_type=contract_type,
            model_override=model_override,
        )
    )

    return result.model_dump(mode="json")

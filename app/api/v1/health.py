from datetime import datetime
from fastapi import APIRouter
from app.config import settings
from app.providers.registry import PROVIDER_CAPABILITIES

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.version,
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/providers")
async def provider_capabilities():
    return {
        "providers": {
            name: {
                "supports_native_pdf": cap.supports_native_pdf,
                "requires_api_key": cap.requires_api_key,
                "default_model": cap.default_model,
                "supported_models": cap.supported_models,
            }
            for name, cap in PROVIDER_CAPABILITIES.items()
        }
    }

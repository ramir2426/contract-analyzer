import asyncio
import time

import structlog

from app.legal.knowledge_base import knowledge_base
from app.models.responses import (
    AnalysisMetadata,
    AnalysisResult,
    ContractFlag,
    ContractParties,
    FlagCategory,
    FlagSeverity,
    KeyTerms,
    LegalStatus,
    PositiveClause,
    RecommendedAction,
    RiskLevel,
)
from app.services.llm_service import LLMService
from app.services.pdf_service import PDFContent, PDFService
from app.services.prompt_service import (
    PROMPT_VERSION,
    build_metadata_extraction_prompt,
    build_section_analysis_prompt,
    build_synthesis_prompt,
    parse_llm_json,
)

log = structlog.get_logger()


class AnalysisService:
    def __init__(self):
        self.pdf_service = PDFService()
        self.llm_service = LLMService()

    async def analyze(
        self,
        pdf_bytes: bytes,
        provider: str,
        api_key: str | None,
        output_language: str = "en",
        contract_type: str = "auto",
        model_override: str | None = None,
        progress_callback=None,  # async callable(message: str)
    ) -> AnalysisResult:
        """
        Run the full 4-pass analysis pipeline.

        Pass 1: Document Intelligence (no LLM)
        Pass 2: Metadata Extraction (fast LLM call)
        Pass 3: Per-Section Risk Analysis (parallel LLM calls)
        Pass 4: Synthesis (final LLM call)
        """
        start_time = time.time()
        total_tokens = 0

        # ── Pass 1: Document Intelligence ────────────────────────────────────
        if progress_callback:
            await progress_callback("Extracting document structure...")

        log.info("pipeline.pass1.start")
        pdf_content = self.pdf_service.process(pdf_bytes)

        log.info(
            "pipeline.pass1.complete",
            pages=pdf_content.page_count,
            sections=len(pdf_content.sections),
            extraction_method=pdf_content.extraction_method,
            is_scanned=pdf_content.is_scanned,
        )

        # ── Pass 2: Metadata Extraction ───────────────────────────────────────
        if progress_callback:
            await progress_callback("Identifying contract type and key terms...")

        log.info("pipeline.pass2.start")
        metadata_messages = build_metadata_extraction_prompt(pdf_content.extracted_text, contract_type)
        metadata_response = await self.llm_service.complete(
            messages=metadata_messages,
            provider=provider,
            api_key=api_key,
            model_override=model_override,
        )
        total_tokens += metadata_response.tokens_used or 0
        metadata = parse_llm_json(metadata_response.content, context="metadata_extraction")

        log.info("pipeline.pass2.complete", contract_type=metadata.get("contract_type"))

        # ── Pass 3: Per-Section Risk Analysis ─────────────────────────────────
        if progress_callback:
            await progress_callback(f"Analyzing {len(pdf_content.sections)} sections...")

        log.info("pipeline.pass3.start", section_count=len(pdf_content.sections))

        # Analyze sections in parallel (up to 5 at a time to avoid rate limits)
        semaphore = asyncio.Semaphore(5)
        section_results = await asyncio.gather(
            *[
                self._analyze_section(
                    section=section,
                    metadata=metadata,
                    provider=provider,
                    api_key=api_key,
                    model_override=model_override,
                    output_language=output_language,
                    semaphore=semaphore,
                )
                for section in pdf_content.sections
                if len(section.content.strip()) > 50  # Skip empty sections
            ]
        )

        all_flags_raw = []
        for result in section_results:
            all_flags_raw.extend(result.get("flags", []))
            total_tokens += result.get("_tokens", 0)

        log.info("pipeline.pass3.complete", total_flags_found=len(all_flags_raw))

        # ── Pass 4: Synthesis ─────────────────────────────────────────────────
        if progress_callback:
            await progress_callback("Synthesizing final analysis...")

        log.info("pipeline.pass4.start")
        synthesis_messages = build_synthesis_prompt(
            all_section_flags=all_flags_raw,
            metadata=metadata,
            output_language=output_language,
        )
        synthesis_response = await self.llm_service.complete(
            messages=synthesis_messages,
            provider=provider,
            api_key=api_key,
            model_override=model_override,
        )
        total_tokens += synthesis_response.tokens_used or 0
        synthesis = parse_llm_json(synthesis_response.content, context="synthesis")

        log.info("pipeline.pass4.complete", overall_risk=synthesis.get("overall_risk"))

        # ── Build final result ─────────────────────────────────────────────────
        processing_time_ms = int((time.time() - start_time) * 1000)

        return self._build_result(
            metadata=metadata,
            all_flags_raw=all_flags_raw,
            synthesis=synthesis,
            pdf_content=pdf_content,
            provider=provider,
            model=metadata_response.model,
            total_tokens=total_tokens,
            processing_time_ms=processing_time_ms,
        )

    async def _analyze_section(
        self,
        section,
        metadata: dict,
        provider: str,
        api_key: str | None,
        model_override: str | None,
        output_language: str,
        semaphore: asyncio.Semaphore,
    ) -> dict:
        async with semaphore:
            legal_context = knowledge_base.retrieve(
                clause_text=section.content[:500],
                contract_type=metadata.get("contract_type", "unknown"),
            )
            messages = build_section_analysis_prompt(
                section_title=section.title,
                section_text=section.content,
                contract_metadata=metadata,
                legal_context=legal_context or None,
                output_language=output_language,
            )
            try:
                response = await self.llm_service.complete(
                    messages=messages,
                    provider=provider,
                    api_key=api_key,
                    model_override=model_override,
                )
                result = parse_llm_json(response.content, context=f"section:{section.title}")
                result["_tokens"] = response.tokens_used or 0
                return result
            except Exception as e:
                log.warning("pipeline.section_analysis_failed", section=section.title, error=str(e))
                return {"flags": [], "_tokens": 0}

    def _build_result(
        self,
        metadata: dict,
        all_flags_raw: list[dict],
        synthesis: dict,
        pdf_content: PDFContent,
        provider: str,
        model: str,
        total_tokens: int,
        processing_time_ms: int,
    ) -> AnalysisResult:
        flags = [self._parse_flag(f) for f in all_flags_raw if f]
        positive_clauses = [
            PositiveClause(
                title=p.get("title", ""),
                explanation=p.get("explanation", ""),
                category=self._safe_category(p.get("category", "other")),
                clause_reference=p.get("clause_reference"),
            )
            for p in synthesis.get("positive_clauses", [])
        ]

        parties_data = metadata.get("parties", {})
        key_terms_data = metadata.get("key_terms", {})

        def _sanitize(v):
            """Convert string 'null'/'none' to None — smaller LLMs do this."""
            if isinstance(v, str) and v.lower() in ("null", "none", "n/a", ""):
                return None
            return v

        return AnalysisResult(
            contract_type=metadata.get("contract_type", "unknown"),
            detected_language=metadata.get("detected_language", "unknown"),
            jurisdiction=_sanitize(metadata.get("jurisdiction")),
            parties=ContractParties(
                first_party=_sanitize(parties_data.get("first_party")),
                second_party=_sanitize(parties_data.get("second_party")),
                additional_parties=parties_data.get("additional_parties") or [],
            ),
            key_terms=KeyTerms(**{k: _sanitize(v) for k, v in key_terms_data.items() if k in KeyTerms.model_fields}),
            summary=synthesis.get("summary", ""),
            summary_plain=synthesis.get("summary_plain", ""),
            overall_risk=self._safe_enum(RiskLevel, synthesis.get("overall_risk", "medium"), RiskLevel.MEDIUM),
            flags=flags,
            positive_clauses=positive_clauses,
            missing_required_clauses=synthesis.get("missing_required_clauses", []),
            priority_actions=synthesis.get("priority_actions", []),
            metadata=AnalysisMetadata(
                provider=provider,
                model=model,
                prompt_version=PROMPT_VERSION,
                processing_time_ms=processing_time_ms,
                pdf_pages=pdf_content.page_count,
                total_tokens_used=total_tokens,
                extraction_method=pdf_content.extraction_method,
            ),
        )

    def _parse_flag(self, raw: dict) -> ContractFlag:
        return ContractFlag(
            severity=self._safe_enum(FlagSeverity, raw.get("severity", "yellow"), FlagSeverity.YELLOW),
            legal_status=self._safe_enum(LegalStatus, raw.get("legal_status", "standard"), LegalStatus.STANDARD),
            category=self._safe_category(raw.get("category", "other")),
            title=raw.get("title", ""),
            explanation=raw.get("explanation", ""),
            what_this_means=raw.get("what_this_means", ""),
            clause_reference=raw.get("clause_reference"),
            raw_text=raw.get("raw_text"),
            legal_source=raw.get("legal_source"),
            action=self._safe_enum(RecommendedAction, raw.get("action", "negotiate"), RecommendedAction.NEGOTIATE),
            negotiation_suggestion=raw.get("negotiation_suggestion"),
        )

    def _safe_enum(self, enum_class, value: str, default):
        try:
            return enum_class(value)
        except ValueError:
            return default

    def _safe_category(self, value: str) -> FlagCategory:
        return self._safe_enum(FlagCategory, value, FlagCategory.OTHER)

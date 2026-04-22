import json
import re
import structlog
from typing import Any

from app.exceptions import ParseError

log = structlog.get_logger()

# Increment this when you change prompts significantly.
# Stored with every analysis result so you know which prompt produced it.
PROMPT_VERSION = "v1.0"


# ─── System prompts ────────────────────────────────────────────────────────────

METADATA_EXTRACTION_SYSTEM = """
You are a contract data extraction specialist. Extract structured factual information from contracts.
Do not make inferences — only extract what is explicitly stated in the contract.
You MUST respond with valid JSON only. No markdown, no explanation outside the JSON.
"""

RISK_ANALYSIS_SYSTEM = """
You are a legal contract analysis assistant specializing in protecting individuals (not corporations).
You analyze contracts under European and German law where relevant.

CRITICAL DISTINCTION — classify every flagged clause with one of these legal statuses:
- "void": The clause is already unenforceable by law (e.g., BGB §307, specific BGH rulings). The user can sign and safely ignore this clause.
- "voidable": Enforceable unless the user actively challenges it.
- "unfavorable_but_valid": Legally binding and disadvantageous. Must be negotiated before signing.
- "standard": Normal, expected clause. No special concern.

For German contracts: Know these critical areas:
- Schönheitsreparaturen (cosmetic repair clauses): Rigid schedule clauses are void per BGH
- Kaution: Maximum 3 months Kaltmiete per BGB §551
- Kündigungsfrist: Minimum 3 months for residential tenants per BGB §573c
- Non-compete: Only enforceable with 50% compensation per §74 HGB
- DSGVO: Data processing clauses must have legal basis

Always cite the legal source (BGB §, BGH ruling, EU directive) for every flag.
Always provide negotiation_suggestion in the contract's original language for red/yellow flags.

You MUST respond with valid JSON only. No markdown fences, no explanation outside the JSON.
"""

SYNTHESIS_SYSTEM = """
You are a senior legal analyst producing a final summary of a contract analysis.
You have received per-section analysis results. Your job is to:
1. Identify the most critical issues across all sections
2. Detect any contradictions between sections
3. List legally required clauses that are missing
4. Produce a plain-language summary (2-3 sentences) suitable for a non-lawyer
5. Rank the top 3-5 priority actions

You MUST respond with valid JSON only.
"""


# ─── Prompt builders ───────────────────────────────────────────────────────────

def build_metadata_extraction_prompt(contract_text: str, contract_type: str = "auto") -> list[dict]:
    schema = {
        "contract_type": "string (rental/employment/freelance/gym/insurance/service/auto)",
        "detected_language": "string (ISO 639-1 code, e.g. 'de', 'en')",
        "jurisdiction": "string or null",
        "parties": {
            "first_party": "string or null",
            "second_party": "string or null",
            "additional_parties": "array of strings"
        },
        "key_terms": {
            "start_date": "string or null",
            "end_date": "string or null",
            "notice_period": "string or null",
            "monthly_amount": "string or null",
            "deposit": "string or null",
            "auto_renewal": "boolean or null",
            "auto_renewal_date": "string or null",
            "jurisdiction": "string or null",
            "governing_law": "string or null",
            "additional_terms": "object with key-value pairs for other important terms"
        }
    }

    user_message = f"""Extract structured metadata from this contract.
Contract type hint: {contract_type}

CONTRACT TEXT:
{contract_text[:8000]}

Respond with JSON matching this schema:
{json.dumps(schema, indent=2)}"""

    return [
        {"role": "system", "content": METADATA_EXTRACTION_SYSTEM},
        {"role": "user", "content": user_message},
    ]


def build_section_analysis_prompt(
    section_title: str,
    section_text: str,
    contract_metadata: dict,
    legal_context: str | None,
    output_language: str = "en",
) -> list[dict]:
    schema = {
        "flags": [
            {
                "severity": "red | yellow | green",
                "legal_status": "void | voidable | unfavorable_but_valid | standard",
                "category": "termination | financial | liability | privacy | intellectual_property | dispute_resolution | renewal | repairs | non_compete | working_conditions | other",
                "title": "short title",
                "explanation": "plain language explanation",
                "what_this_means": "practical consequence for the user",
                "clause_reference": "e.g. § 4.2 or null",
                "raw_text": "exact text from contract or null",
                "legal_source": "e.g. BGB §307, BGH VIII ZR 215/12 or null",
                "action": "none_required | negotiate | consult_lawyer | walk_away | accept",
                "negotiation_suggestion": "exact replacement wording in contract language or null"
            }
        ]
    }

    legal_context_block = f"\nRELEVANT LEGAL CONTEXT:\n{legal_context}\n" if legal_context else ""

    user_message = f"""Analyze this section of a {contract_metadata.get('contract_type', 'contract')}.

CONTRACT METADATA:
- Type: {contract_metadata.get('contract_type')}
- Jurisdiction: {contract_metadata.get('jurisdiction', 'unknown')}
- Language: {contract_metadata.get('detected_language', 'unknown')}

SECTION: {section_title}
{legal_context_block}
SECTION TEXT:
{section_text[:4000]}

Output language for explanations: {output_language}

Respond with JSON matching this schema:
{json.dumps(schema, indent=2)}

Only flag things that are actually present in this section. Return empty flags array if nothing notable."""

    return [
        {"role": "system", "content": RISK_ANALYSIS_SYSTEM},
        {"role": "user", "content": user_message},
    ]


def build_synthesis_prompt(
    all_section_flags: list[dict],
    metadata: dict,
    output_language: str = "en",
) -> list[dict]:
    schema = {
        "summary": "2-3 sentence summary for a lawyer",
        "summary_plain": "2-3 sentence plain-language summary for a non-lawyer",
        "overall_risk": "low | medium | high",
        "contradictions": ["description of any contradictions found between sections"],
        "missing_required_clauses": ["list of legally required clauses that are absent"],
        "priority_actions": ["top 3-5 specific actions the user should take, ordered by importance"],
        "positive_clauses": [
            {
                "title": "title",
                "explanation": "why this is good",
                "category": "category string"
            }
        ]
    }

    user_message = f"""Synthesize the following section-by-section analysis into a final report.

CONTRACT TYPE: {metadata.get('contract_type')}
JURISDICTION: {metadata.get('jurisdiction', 'unknown')}
OUTPUT LANGUAGE: {output_language}

PER-SECTION FLAGS:
{json.dumps(all_section_flags, indent=2)[:6000]}

Respond with JSON matching this schema:
{json.dumps(schema, indent=2)}"""

    return [
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {"role": "user", "content": user_message},
    ]


# ─── Response parser ───────────────────────────────────────────────────────────

def parse_llm_json(raw: str, context: str = "") -> dict[str, Any]:
    """
    Multi-layer JSON parser. Never trust the LLM to return clean JSON.

    Layers:
    1. Direct parse
    2. Strip markdown code fences
    3. Extract JSON substring with regex
    4. Raise ParseError with raw content for debugging
    """
    text = raw.strip()

    # Layer 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Layer 2: strip markdown fences ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Layer 3: find the largest {...} block
    brace_pattern = re.compile(r"\{[\s\S]*\}", re.DOTALL)
    match = brace_pattern.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    log.error("llm.parse_failed", context=context, raw_length=len(raw), raw_preview=raw[:200])
    raise ParseError(
        f"LLM returned unparseable output for '{context}'. "
        f"Raw content (first 200 chars): {raw[:200]}"
    )

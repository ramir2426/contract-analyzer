import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def async_client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def sample_pdf_bytes():
    """A valid one-page PDF built with pypdf — already a project dependency."""
    import io

    import pypdf

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def mock_llm_metadata_response():
    return (
        '{"contract_type": "rental", "detected_language": "de", "jurisdiction": "DE",'
        '"parties": {"first_party": "Max Mustermann (Mieter)", "second_party": "ABC GmbH (Vermieter)",'
        '"additional_parties": []},'
        '"key_terms": {"start_date": "2026-05-01", "end_date": null, "notice_period": "6 Monate",'
        '"monthly_amount": "1200 EUR", "deposit": "2400 EUR", "auto_renewal": false, "additional_terms": {}}}'
    )


@pytest.fixture
def mock_llm_section_response():
    return (
        '{"flags": [{"severity": "red", "legal_status": "unfavorable_but_valid",'
        '"category": "termination", "title": "Unusual notice period",'
        '"explanation": "6 months required, BGB minimum is 3.",'
        '"what_this_means": "You must give 6 months notice to leave.",'
        '"clause_reference": "§ 4",'
        '"raw_text": "Die Kündigungsfrist beträgt sechs Monate.",'
        '"legal_source": "BGB §573c", "action": "negotiate",'
        '"negotiation_suggestion": "Die Kündigungsfrist beträgt drei Monate zum Monatsende."}]}'
    )


@pytest.fixture
def mock_llm_synthesis_response():
    return (
        '{"summary": "Standard rental contract with one unfavorable clause.",'
        '"summary_plain": "This is a rental agreement. The main issue is the notice period is too long.",'
        '"overall_risk": "medium", "contradictions": [], "missing_required_clauses": [],'
        '"priority_actions": ["Negotiate notice period down to 3 months"], "positive_clauses": []}'
    )

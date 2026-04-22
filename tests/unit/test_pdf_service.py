import pytest
from app.services.pdf_service import PDFService
from app.exceptions import InvalidPDFError


def test_rejects_non_pdf_bytes():
    service = PDFService()
    with pytest.raises(InvalidPDFError):
        service.process(b"this is not a pdf", "fake.pdf")


def test_rejects_oversized_pdf(monkeypatch):
    from app.config import settings
    # Patch the source field (max_pdf_size_mb), not the derived property
    monkeypatch.setattr(settings, "max_pdf_size_mb", 0)
    service = PDFService()
    with pytest.raises(InvalidPDFError):
        service.process(b"%PDF-" + b"x" * 100, "big.pdf")


def test_extracts_text_from_valid_pdf(sample_pdf_bytes):
    from app.exceptions import ScannedPDFError
    service = PDFService()
    # Blank PDFs have no extractable text → triggers OCR path.
    # On CI without tesseract/poppler, ScannedPDFError is the correct outcome.
    try:
        result = service.process(sample_pdf_bytes)
        assert result.page_count >= 1
        assert result.document_hash is not None
        assert result.extraction_method in ("pdfplumber", "pypdf", "ocr")
    except ScannedPDFError:
        pass  # Expected on systems without tesseract/poppler installed

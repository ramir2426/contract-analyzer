import io
import hashlib
import structlog
from dataclasses import dataclass, field

import pdfplumber
import pypdf

from app.exceptions import InvalidPDFError, ScannedPDFError
from app.config import settings

log = structlog.get_logger()

# If extracted text is shorter than this, the PDF is probably scanned
SCANNED_PDF_TEXT_THRESHOLD = 100


@dataclass
class DocumentSection:
    """A logical section of the contract."""
    title: str
    content: str
    page_numbers: list[int] = field(default_factory=list)
    section_number: str | None = None


@dataclass
class PDFContent:
    """Everything extracted from a PDF, used by downstream services."""
    raw_bytes: bytes
    extracted_text: str
    sections: list[DocumentSection]
    page_count: int
    is_scanned: bool
    extraction_method: str                  # "pdfplumber", "pypdf", "ocr"
    document_hash: str                      # SHA256 — used for caching
    detected_language_hint: str | None = None


class PDFService:

    def process(self, pdf_bytes: bytes, filename: str = "contract.pdf") -> PDFContent:
        """
        Main entry point. Validates, detects type, extracts text and structure.
        """
        self._validate(pdf_bytes, filename)

        document_hash = hashlib.sha256(pdf_bytes).hexdigest()
        log.info("pdf.processing", filename=filename, size_bytes=len(pdf_bytes), hash=document_hash[:12])

        # Try pdfplumber first (better for structured documents)
        extracted_text, sections, page_count = self._extract_with_pdfplumber(pdf_bytes)

        # If we got very little text, the PDF is probably scanned
        if len(extracted_text.strip()) < SCANNED_PDF_TEXT_THRESHOLD:
            log.info("pdf.scanned_detected", text_length=len(extracted_text))
            extracted_text, sections, page_count = self._extract_with_ocr(pdf_bytes)
            extraction_method = "ocr"
            is_scanned = True
        else:
            extraction_method = "pdfplumber"
            is_scanned = False

        log.info(
            "pdf.extracted",
            method=extraction_method,
            pages=page_count,
            text_length=len(extracted_text),
            sections=len(sections),
        )

        return PDFContent(
            raw_bytes=pdf_bytes,
            extracted_text=extracted_text,
            sections=sections,
            page_count=page_count,
            is_scanned=is_scanned,
            extraction_method=extraction_method,
            document_hash=document_hash,
        )

    def _validate(self, pdf_bytes: bytes, filename: str) -> None:
        # Check magic bytes — a real PDF starts with %PDF-
        if not pdf_bytes.startswith(b"%PDF-"):
            raise InvalidPDFError(f"File '{filename}' is not a valid PDF (magic bytes check failed).")

        if len(pdf_bytes) > settings.max_pdf_size_bytes:
            raise InvalidPDFError(
                f"File exceeds maximum size of {settings.max_pdf_size_mb}MB."
            )

    def _extract_with_pdfplumber(
        self, pdf_bytes: bytes
    ) -> tuple[str, list[DocumentSection], int]:
        try:
            sections: list[DocumentSection] = []
            full_text_parts: list[str] = []

            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                page_count = len(pdf.pages)

                for page_num, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""

                    # Extract tables and convert to readable text
                    for table in page.extract_tables():
                        table_text = self._table_to_text(table)
                        page_text += f"\n[TABLE]\n{table_text}\n[/TABLE]\n"

                    full_text_parts.append(page_text)

            full_text = "\n\n".join(full_text_parts)
            sections = self._detect_sections(full_text)

            return full_text, sections, page_count

        except Exception as e:
            log.warning("pdf.pdfplumber_failed", error=str(e))
            # Fall back to pypdf
            return self._extract_with_pypdf(pdf_bytes)

    def _extract_with_pypdf(
        self, pdf_bytes: bytes
    ) -> tuple[str, list[DocumentSection], int]:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        pages_text = [page.extract_text() or "" for page in reader.pages]
        full_text = "\n\n".join(pages_text)
        sections = self._detect_sections(full_text)
        return full_text, sections, page_count

    def _extract_with_ocr(
        self, pdf_bytes: bytes
    ) -> tuple[str, list[DocumentSection], int]:
        """OCR for scanned PDFs. Requires tesseract + pdf2image installed."""
        try:
            from pdf2image import convert_from_bytes
            import pytesseract

            images = convert_from_bytes(pdf_bytes, dpi=300)
            page_count = len(images)
            pages_text = []

            for image in images:
                # lang="deu+eng" handles German and English mixed documents
                text = pytesseract.image_to_string(image, lang="deu+eng")
                pages_text.append(text)

            full_text = "\n\n".join(pages_text)
            sections = self._detect_sections(full_text)
            return full_text, sections, page_count

        except ImportError:
            raise ScannedPDFError(
                "This PDF appears to be a scanned document. "
                "OCR processing requires pytesseract and pdf2image to be installed."
            )

    def _detect_sections(self, text: str) -> list[DocumentSection]:
        """
        Simple heuristic section detection.
        Looks for patterns like: §1, § 1, Section 1, Abschnitt 1, 1., 1.1
        """
        import re
        sections = []
        current_title = "Preamble"
        current_lines: list[str] = []

        section_pattern = re.compile(
            r"^(§\s*\d+[\.\d]*|Section\s+\d+|Abschnitt\s+\d+|\d+\.\s+[A-ZÜÄÖ])",
            re.MULTILINE | re.IGNORECASE,
        )

        for line in text.split("\n"):
            if section_pattern.match(line.strip()):
                if current_lines:
                    sections.append(DocumentSection(
                        title=current_title,
                        content="\n".join(current_lines).strip(),
                    ))
                current_title = line.strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Add the last section
        if current_lines:
            sections.append(DocumentSection(
                title=current_title,
                content="\n".join(current_lines).strip(),
            ))

        return sections if sections else [
            DocumentSection(title="Full Contract", content=text)
        ]

    def _table_to_text(self, table: list[list]) -> str:
        """Convert a pdfplumber table (list of rows) to readable text."""
        rows = []
        for row in table:
            cells = [str(cell or "").strip() for cell in row]
            rows.append(" | ".join(cells))
        return "\n".join(rows)

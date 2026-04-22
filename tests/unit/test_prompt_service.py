import pytest

from app.exceptions import ParseError
from app.services.prompt_service import parse_llm_json


def test_parses_clean_json():
    raw = '{"flags": [], "summary": "test"}'
    result = parse_llm_json(raw)
    assert result["summary"] == "test"


def test_parses_json_with_markdown_fences():
    raw = '```json\n{"flags": [], "summary": "test"}\n```'
    result = parse_llm_json(raw)
    assert result["summary"] == "test"


def test_parses_json_with_preamble():
    raw = 'Here is the analysis:\n{"flags": [], "summary": "test"}'
    result = parse_llm_json(raw)
    assert result["summary"] == "test"


def test_raises_on_garbage():
    with pytest.raises(ParseError):
        parse_llm_json("This is completely unparseable text with no JSON")

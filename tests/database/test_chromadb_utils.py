from database.utils.chromadb_utils import (
    ChromaCanonicalValidationError,
    validate_chroma_is_canonical,
)


def test_validate_chroma_detects_mcp_bus(monkeypatch):
    monkeypatch.setattr(
        "database.utils.chromadb_utils.get_root_info",
        lambda h, p: {"text": "MCP Bus Agent"},
    )
    res = validate_chroma_is_canonical("localhost", 8000, raise_on_fail=False)
    assert res["ok"] is False
    assert "MCP Bus Agent" in str(res["root_info"].get("text", ""))

    # Raise-on-fail behavior
    try:
        validate_chroma_is_canonical("localhost", 8000, raise_on_fail=True)
        raise AssertionError("Expected ChromaCanonicalValidationError")
    except ChromaCanonicalValidationError:
        pass

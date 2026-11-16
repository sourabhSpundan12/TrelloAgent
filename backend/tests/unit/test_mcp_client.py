import pytest
from app.integrations.mcp.exceptions import MCPSSRFError
from app.integrations.mcp.tool_adapter import MCPToolAdapter, compute_schema_fingerprint
from app.integrations.mcp.transport import validate_url_ssrf


class DummyMCPTool:
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.input_schema = input_schema


def test_ssrf_validator_blocks_private_and_loopback():
    with pytest.raises(MCPSSRFError):
        validate_url_ssrf("http://127.0.0.1:8000/mcp", allow_internal=False)

    with pytest.raises(MCPSSRFError):
        validate_url_ssrf("http://localhost:8000/mcp", allow_internal=False)

    with pytest.raises(MCPSSRFError):
        validate_url_ssrf("http://10.0.0.5/mcp", allow_internal=False)

    with pytest.raises(MCPSSRFError):
        validate_url_ssrf("http://192.168.1.100/mcp", allow_internal=False)


def test_ssrf_validator_blocks_invalid_schemes():
    with pytest.raises(MCPSSRFError):
        validate_url_ssrf("ftp://example.com/mcp", allow_internal=False)

    with pytest.raises(MCPSSRFError):
        validate_url_ssrf("file:///etc/passwd", allow_internal=False)


def test_ssrf_validator_allows_internal_when_explicit():
    # Should not raise when allow_internal=True
    validate_url_ssrf("http://localhost:8000/mcp", allow_internal=True)
    validate_url_ssrf("http://127.0.0.1:8000/mcp", allow_internal=True)


def test_schema_fingerprint_deterministic():
    schema_a = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "number"}}}
    schema_b = {"properties": {"b": {"type": "number"}, "a": {"type": "string"}}, "type": "object"}
    # Different key ordering must produce identical hash
    hash_a = compute_schema_fingerprint(schema_a)
    hash_b = compute_schema_fingerprint(schema_b)
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_mcp_tool_adapter_adapts_model():
    dummy = DummyMCPTool(
        name="search_cards",
        description="Search cards in Trello board by keyword query",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    server_doc = {
        "server_id": "trello-server",
        "transport_type": "streamable_http",
    }

    tool_model = MCPToolAdapter.adapt_to_tool_model(dummy, server_doc)
    assert tool_model.tool_id == "mcp.trello-server.search_cards"
    assert tool_model.source_type == "MCP"
    assert tool_model.source_id == "trello-server"
    assert tool_model.remote_tool_name == "search_cards"
    assert tool_model.executor_type == "mcp"
    assert tool_model.executor_key == "mcp.trello-server.search_cards"
    assert "query" in tool_model.input_schema["properties"]
    assert tool_model.schema_fingerprint is not None
    assert "search" in tool_model.keywords


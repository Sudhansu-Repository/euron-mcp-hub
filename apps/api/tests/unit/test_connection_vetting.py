from __future__ import annotations

import uuid

import mcp_types as types
import pytest

from mcphub.models.enums import Transport
from mcphub.upstream.connection import UpstreamConnection
from mcphub.upstream.spec import UpstreamProtocolError, UpstreamSpec


def _connection(limit: int = 10_000, **secrets: str) -> UpstreamConnection:
    spec = UpstreamSpec(
        server_id=uuid.uuid4(),
        slug="tickets",
        transport=Transport.STREAMABLE_HTTP,
        config_version=1,
        url="https://tickets.example.com/mcp",
        headers={"authorization": "Bearer tkt_SECRETVALUE123", **secrets},
    )
    return UpstreamConnection(spec, connect_timeout_s=1, max_call_s=1, max_result_bytes=limit)


def _text(value: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=value)])


def test_an_upstream_that_echoes_the_gateways_token_does_not_hand_it_to_the_client() -> None:
    result = _connection()._vet(_text("auth failed for Bearer tkt_SECRETVALUE123, sorry"))

    block = result.content[0]
    assert isinstance(block, types.TextContent)
    assert "tkt_SECRETVALUE123" not in block.text
    assert "[redacted]" in block.text


def test_ordinary_results_pass_through_untouched() -> None:
    original = _text("TCK-1201 is open")

    assert _connection()._vet(original) is not None
    assert _connection()._vet(original).content == original.content


def test_an_oversized_result_is_refused_with_its_size() -> None:
    with pytest.raises(UpstreamProtocolError, match="over the gateway's limit"):
        _connection(limit=1_000)._vet(_text("x" * 5_000))

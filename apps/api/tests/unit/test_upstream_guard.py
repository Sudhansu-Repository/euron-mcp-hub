from __future__ import annotations

import pytest

from mcphub.upstream.guard import check_command, check_resolved, check_url
from mcphub.upstream.spec import UpstreamRefusedError


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://169.254.170.2/v2/credentials",
        "http://metadata.google.internal/computeMetadata",
        "http://[fd00:ec2::254]/",
        "http://[::ffff:169.254.169.254]/",
        "http://0.0.0.0:8080/mcp",
    ],
)
def test_metadata_and_link_local_are_never_allowed(url: str) -> None:
    with pytest.raises(UpstreamRefusedError, match="metadata"):
        check_url(url)
    with pytest.raises(UpstreamRefusedError, match="metadata"):
        check_url(url, ["*"], allow_private=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9000/mcp",
        "http://localhost/mcp",
        "http://10.0.3.4/mcp",
        "http://172.16.0.9/mcp",
        "http://192.168.1.20/mcp",
        "http://100.64.0.5/mcp",
        "http://[::1]/mcp",
        "http://[fd12:3456::1]/mcp",
        "http://[::ffff:10.0.0.1]/mcp",
        "http://tickets.internal/mcp",
    ],
)
def test_private_ranges_are_refused_by_default(url: str) -> None:
    with pytest.raises(UpstreamRefusedError, match="private or local"):
        check_url(url)


def test_private_hosts_can_be_allow_listed_or_enabled_wholesale() -> None:
    assert check_url("http://10.0.3.4/mcp", ["10.0.3.4"]) == "http://10.0.3.4/mcp"
    assert check_url("http://demo-servers:9150/mcp", ["demo-*"])
    assert check_url("http://tickets.internal/mcp", ["*.internal"])
    assert check_url("http://127.0.0.1:9150/mcp", allow_private=True)
    with pytest.raises(UpstreamRefusedError):
        check_url("http://10.0.3.5/mcp", ["10.0.3.4"])


def test_public_addresses_need_no_allow_list() -> None:
    assert check_url("https://mcp.example.com/mcp")
    assert check_url("https://93.184.216.34/mcp")


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com/mcp", "http"),
        ("http:///mcp", "host"),
        ("https://user:pass@example.com/mcp", "credentials"),
        ("http://example.com:0/mcp", "port"),
        ("http://[bad/mcp", "parsed"),
    ],
)
def test_malformed_urls_are_refused(url: str, message: str) -> None:
    with pytest.raises(UpstreamRefusedError, match=message):
        check_url(url)


async def test_a_name_that_resolves_to_a_private_address_is_refused() -> None:
    # localhost resolves to loopback on every machine, so no network is needed.
    with pytest.raises(UpstreamRefusedError, match="private address"):
        await check_resolved("http://localhost:9000/mcp")
    await check_resolved("http://localhost:9000/mcp", ["localhost"])
    await check_resolved("http://localhost:9000/mcp", allow_private=True)


async def test_literal_addresses_and_unresolvable_names_pass_through_the_resolver() -> None:
    await check_resolved("http://127.0.0.1/mcp")
    await check_resolved("http://no-such-host.invalid/mcp")


def test_stdio_needs_an_allow_listed_command() -> None:
    with pytest.raises(UpstreamRefusedError, match="disabled"):
        check_command("npx", [])
    with pytest.raises(UpstreamRefusedError, match="not an allowed"):
        check_command("bash", ["npx", "uvx"])
    with pytest.raises(UpstreamRefusedError, match="needs a command"):
        check_command("  ", ["npx"])
    assert check_command("npx", ["npx"]) == "npx"
    assert check_command("/usr/local/bin/uvx", ["uvx"]) == "/usr/local/bin/uvx"

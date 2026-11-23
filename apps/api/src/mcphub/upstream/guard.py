"""Guards on where the gateway may connect and what it may launch.

Registering a server makes the gateway open connections (and, for stdio, start processes)
on the operator's behalf. These checks keep that from becoming a way to reach the cloud
metadata service or the private network behind the gateway, or to run arbitrary commands
on the gateway host.

The egress policy has three tiers:

1. Cloud metadata and link-local addresses are never allowed, whatever the configuration.
2. Loopback, private and reserved ranges are refused unless the host matches
   UPSTREAM_ALLOWED_HOSTS (or UPSTREAM_ALLOW_PRIVATE is on, for laptops).
3. Everything else, the public internet, is allowed.

`check_url` judges the URL as written; `check_resolved` resolves the host name and judges
every address it points to, so a public-looking name that resolves to a private address is
caught as well.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from collections.abc import Sequence
from fnmatch import fnmatchcase
from urllib.parse import urlsplit

from mcphub.upstream.spec import UpstreamRefusedError

# Instance and task metadata endpoints hand out cloud credentials; never a valid upstream.
_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "169.254.170.2",
        "fd00:ec2::254",
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)
_LOCAL_NAMES = ("localhost", ".localhost", ".local", ".internal", ".localdomain")

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _is_forbidden_always(address: IpAddress) -> bool:
    return bool(address.is_link_local or address.is_multicast or address.is_unspecified)


def _is_private(address: IpAddress) -> bool:
    # `is_global` is false for loopback, RFC 1918, unique local, carrier NAT and the
    # documentation and reserved blocks, which is exactly the set to keep out by default.
    return not address.is_global


def _literal(host: str) -> IpAddress | None:
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _allowed_by_list(host: str, allowed_hosts: Sequence[str]) -> bool:
    return any(fnmatchcase(host, pattern.lower()) for pattern in allowed_hosts)


def check_url(url: str, allowed_hosts: Sequence[str] = (), *, allow_private: bool = False) -> str:
    """The URL if it is acceptable for a streamable HTTP server; raises otherwise."""
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise UpstreamRefusedError("That URL cannot be parsed.") from exc
    if parts.scheme not in {"http", "https"}:
        raise UpstreamRefusedError("Use an http:// or https:// URL.")
    if not host:
        raise UpstreamRefusedError("The URL needs a host name.")
    if parts.username or parts.password:
        raise UpstreamRefusedError(
            "Put credentials in a header secret, not in the URL, so they are encrypted."
        )
    address = _literal(host)
    if host in _METADATA_HOSTS or (address is not None and _is_forbidden_always(address)):
        raise UpstreamRefusedError("Link-local and cloud metadata addresses are not allowed.")
    private = (address is not None and _is_private(address)) or (
        address is None and (host in _LOCAL_NAMES or host.endswith(_LOCAL_NAMES))
    )
    if private and not allow_private and not _allowed_by_list(host, allowed_hosts):
        raise UpstreamRefusedError(
            f"{host} is on a private or local network. Add it to UPSTREAM_ALLOWED_HOSTS "
            "to let this gateway reach it."
        )
    if port == 0:
        raise UpstreamRefusedError("The URL has an invalid port.")
    return url.strip()


async def check_resolved(
    url: str, allowed_hosts: Sequence[str] = (), *, allow_private: bool = False
) -> None:
    """Resolve the URL's host name and refuse it if any address it points to is not allowed."""
    host = (urlsplit(url.strip()).hostname or "").lower()
    if not host or _literal(host) is not None:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
    except OSError:
        # Unresolvable: the connection fails with its own, clearer message.
        return
    for info in infos:
        address = _literal(str(info[4][0]).split("%", 1)[0])
        if address is None:
            continue
        if _is_forbidden_always(address):
            raise UpstreamRefusedError(
                f"Link-local and cloud metadata addresses are not allowed ({host} resolves to one)."
            )
        if _is_private(address) and not allow_private and not _allowed_by_list(host, allowed_hosts):
            raise UpstreamRefusedError(
                f"{host} resolves to a private address. Add it to UPSTREAM_ALLOWED_HOSTS "
                "to let this gateway reach it."
            )


def check_command(command: str, allowed_commands: Sequence[str]) -> str:
    """The command if a stdio server may be launched with it; raises otherwise.

    The allowlist names executables, either bare (`mcphub-demo`, `npx`) or as absolute
    paths. Arguments are passed as a list, never through a shell, so they cannot inject
    a second command.
    """
    value = command.strip()
    if not value:
        raise UpstreamRefusedError("A stdio server needs a command.")
    if not allowed_commands:
        raise UpstreamRefusedError(
            "stdio servers are disabled: set STDIO_ALLOWED_COMMANDS to the executables "
            "this gateway may launch."
        )
    if value not in allowed_commands and os.path.basename(value) not in allowed_commands:
        allowed = ", ".join(sorted(allowed_commands))
        raise UpstreamRefusedError(f"{value} is not an allowed stdio command (allowed: {allowed}).")
    return value

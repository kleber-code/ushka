"""Who is really calling: the client address behind a reverse proxy.

``X-Forwarded-For`` is written by every proxy on the way and by the client
itself, so it can only be believed where *your own* proxies wrote it. The rule:

1. If the direct peer (``scope["client"]``) is not in ``[security]
   trusted_proxies``, every ``X-Forwarded-*`` header is ignored.
2. Otherwise the list is read from the right, skipping trusted proxies. The
   first address that is not one of them is the client. The left-most entry is
   never used on its own: that is the one a client can write.
3. An entry that is not an IP address ends the walk, and the peer is used.

Standard library only (``ipaddress``).
"""

from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

log = logging.getLogger("ushka")

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
Address = ipaddress.IPv4Address | ipaddress.IPv6Address

_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}(:\d{1,5})?$|^\[[0-9A-Fa-f:.]+\](:\d{1,5})?$")


@lru_cache(maxsize=32)
def parse_networks(entries: tuple[str, ...]) -> tuple[Network, ...]:
    """IPs and CIDRs as networks. Invalid entries (and ``*``) are skipped with a warning."""
    networks: list[Network] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError:
            log.warning("[security] trusted_proxies: %r is not an IP address or CIDR; ignored", entry)
    return tuple(networks)


def networks_from_config(value: Any) -> tuple[Network, ...]:
    """Reads the ``trusted_proxies`` setting: a list, or a comma-separated string."""
    if isinstance(value, str):
        value = value.split(",")
    items = tuple(str(v).strip() for v in (value or ()) if str(v).strip())
    return parse_networks(items) if items else ()


def parse_ip(text: Any) -> Address | None:
    """An IP from ``1.2.3.4``, ``::1``, ``[::1]``, ``1.2.3.4:80`` or ``[::1]:80``; else None."""
    value = str(text).strip()
    if not value or len(value) > 64:
        return None
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return None
        rest = value[end + 1 :]
        if rest and not re.fullmatch(r":\d{1,5}", rest):
            return None
        value = value[1:end]
    elif value.count(":") == 1:  # ipv4:port
        value, _, port = value.partition(":")
        if not port.isdigit():
            return None
    value = value.partition("%")[0]  # fe80::1%eth0
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped or ip


def is_trusted(ip: Address | None, networks: Iterable[Network]) -> bool:
    return ip is not None and any(ip in net for net in networks if net.version == ip.version)


def peer_of(scope: dict) -> str | None:
    """The direct peer's address from the ASGI scope, or None (unix sockets)."""
    client = scope.get("client")
    if not client:
        return None
    ip = parse_ip(client[0])
    return str(ip) if ip else None


def _header(scope: dict, name: bytes) -> str:
    """All values of a header, joined like a single comma-separated one."""
    return ",".join(v.decode("latin-1") for k, v in scope.get("headers", ()) if k.lower() == name)


def trusted_peer(scope: dict, networks: tuple[Network, ...]) -> bool:
    return bool(networks) and is_trusted(parse_ip(peer_of(scope) or ""), networks)


def client_ip(scope: dict, networks: tuple[Network, ...]) -> str | None:
    """The client's address as a plain string, or None when it is unknown."""
    peer = peer_of(scope)
    if peer is None or not trusted_peer(scope, networks):
        return peer
    hops = [h for h in _header(scope, b"x-forwarded-for").split(",") if h.strip()]
    for hop in reversed(hops):
        ip = parse_ip(hop)
        if ip is None:
            return peer  # malformed: believe nothing the proxy chain said
        if not is_trusted(ip, networks):
            return str(ip)
    return peer  # every hop is one of ours: the nearest one is all we know


def forwarded_scheme(scope: dict, networks: tuple[Network, ...]) -> str:
    """``http`` or ``https``: what the nearest trusted proxy says, else the scope's."""
    scheme = str(scope.get("scheme", "http"))
    if trusted_peer(scope, networks):
        last = _header(scope, b"x-forwarded-proto").split(",")[-1].strip().lower()
        if last in ("http", "https"):
            return last
    return scheme


def forwarded_host(scope: dict, networks: tuple[Network, ...]) -> str | None:
    """The host the visitor typed, from the nearest trusted proxy; None if not forwarded."""
    if trusted_peer(scope, networks):
        last = _header(scope, b"x-forwarded-host").split(",")[-1].strip()
        if last and _HOST.match(last):
            return last.lower()
    return None

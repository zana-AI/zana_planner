"""
Security checks for outbound content ingestion.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def validate_safe_http_url(url: str) -> None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL host is required")
    host = parsed.hostname.strip().lower()
    if host in ("localhost",):
        raise ValueError("Localhost is not allowed")
    try:
        ip_obj = ipaddress.ip_address(host)
        _ensure_public_ip(ip_obj)
        return
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("Host resolution failed")
    if not infos:
        raise ValueError("Host resolution returned no address")
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        ip_obj = ipaddress.ip_address(ip_str)
        _ensure_public_ip(ip_obj)


def _ensure_public_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        raise ValueError("Private/internal addresses are not allowed")

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

from app.trips.errors import TripError


DEFAULT_ALLOWED_PORTS = {80, 443}
SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "auth",
    "authorization",
    "password",
    "passwd",
    "secret",
    "signature",
    "sig",
    "api_key",
    "apikey",
    "session",
    "sessionid",
    "code",
    "credential",
}
METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
    "instance-data",
}


@dataclass(frozen=True, slots=True)
class NormalizedURL:
    original_url: str
    normalized_url: str
    sanitized_url: str
    scheme: str
    host: str
    port: int
    path: str
    query: str


@dataclass(frozen=True, slots=True)
class ResolvedAddress:
    host: str
    port: int
    ip: str
    family: int


class HostResolver(Protocol):
    def resolve(self, hostname: str, port: int) -> list[ResolvedAddress]:
        ...


class SystemHostResolver:
    def __init__(self, *, timeout_seconds: float = 3.0, max_addresses: int = 16) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_addresses = max_addresses

    def resolve(self, hostname: str, port: int) -> list[ResolvedAddress]:
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout_seconds)
        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise TripError("import_url_dns_failed", "URL host could not be resolved.", 422) from exc
        finally:
            socket.setdefaulttimeout(original_timeout)
        seen: set[str] = set()
        results: list[ResolvedAddress] = []
        for family, _socktype, _proto, _canonname, sockaddr in infos:
            ip = sockaddr[0]
            normalized = normalize_ip_literal(ip)
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append(ResolvedAddress(host=hostname, port=port, ip=normalized, family=family))
            if len(results) >= self.max_addresses:
                break
        if not results:
            raise TripError("import_url_dns_failed", "URL host did not resolve to an address.", 422)
        return results


class URLNetworkPolicy:
    def __init__(self, *, allowed_ports: set[int] | None = None) -> None:
        self.allowed_ports = allowed_ports or DEFAULT_ALLOWED_PORTS

    def normalize_url(self, raw_url: str) -> NormalizedURL:
        value = raw_url.strip()
        if not value:
            raise TripError("import_url_invalid", "URL is empty.", 422)
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise TripError("import_url_invalid", "URL is invalid.", 422) from exc
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise TripError("import_url_scheme_unsupported", "Only HTTP and HTTPS URLs are supported.", 422)
        if parsed.username or parsed.password:
            raise TripError("import_url_userinfo_forbidden", "URL userinfo is not allowed.", 422)
        if not parsed.hostname:
            raise TripError("import_url_host_invalid", "URL host is required.", 422)
        if parsed.hostname.endswith("."):
            raise TripError("import_url_host_invalid", "URL host is ambiguous.", 422)
        host = normalize_hostname(parsed.hostname)
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise TripError("import_url_port_forbidden", "URL port is not allowed.", 422) from exc
        if port not in self.allowed_ports:
            raise TripError("import_url_port_forbidden", "URL port is not allowed.", 422)
        if is_internal_hostname(host):
            raise TripError("import_url_destination_blocked", "URL destination is not public.", 422)
        self._reject_ambiguous_numeric_host(host)
        path = quote(unquote(parsed.path or "/"), safe="/:@!$&'()*+,;=-._~%")
        query = parsed.query
        self._validate_query(query)
        netloc = host if port == (443 if scheme == "https" else 80) else f"{host}:{port}"
        normalized = urlunsplit((scheme, netloc, path, query, ""))
        sanitized = urlunsplit((scheme, netloc, path, redact_query(query), ""))
        return NormalizedURL(
            original_url=value,
            normalized_url=normalized,
            sanitized_url=sanitized,
            scheme=scheme,
            host=host,
            port=port,
            path=path,
            query=query,
        )

    def validate_resolved_addresses(self, addresses: list[ResolvedAddress]) -> None:
        if not addresses:
            raise TripError("import_url_dns_failed", "URL host did not resolve to an address.", 422)
        for address in addresses:
            if not is_public_ip(address.ip):
                raise TripError("import_url_destination_blocked", "URL destination is not public.", 422)

    def validate_peer_address(self, *, peer_ip: str, approved: list[ResolvedAddress]) -> None:
        normalized_peer = normalize_ip_literal(peer_ip)
        if not is_public_ip(normalized_peer):
            raise TripError("import_url_peer_address_mismatch", "URL peer address was not public.", 422)
        approved_ips = {normalize_ip_literal(address.ip) for address in approved}
        if normalized_peer not in approved_ips:
            raise TripError("import_url_peer_address_mismatch", "URL peer address changed after DNS validation.", 422)

    def validate_redirect(self, *, from_url: NormalizedURL, location: str) -> NormalizedURL:
        from urllib.parse import urljoin

        target = self.normalize_url(urljoin(from_url.normalized_url, location))
        if from_url.scheme == "https" and target.scheme == "http":
            raise TripError("import_url_https_downgrade", "HTTPS to HTTP redirects are not allowed.", 422)
        return target

    def _validate_query(self, query: str) -> None:
        for key, _value in parse_qsl(query, keep_blank_values=True):
            if key.strip().lower() in SENSITIVE_QUERY_KEYS:
                raise TripError(
                    "import_url_contains_sensitive_parameters",
                    "URL contains sensitive query parameters.",
                    422,
                )

    def _reject_ambiguous_numeric_host(self, host: str) -> None:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if looks_like_ambiguous_numeric_host(host):
                raise TripError("import_url_host_invalid", "URL host is ambiguous.", 422)
            return
        if not is_public_ip(host):
            raise TripError("import_url_destination_blocked", "URL destination is not public.", 422)


def normalize_hostname(hostname: str) -> str:
    try:
        return hostname.lower().encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise TripError("import_url_host_invalid", "URL host is invalid.", 422) from exc


def is_internal_hostname(host: str) -> bool:
    lowered = host.lower().strip(".")
    if lowered in METADATA_HOSTS or lowered == "localhost" or lowered.endswith(".localhost"):
        return True
    if "." not in lowered and ":" not in lowered:
        return True
    return False


def looks_like_ambiguous_numeric_host(host: str) -> bool:
    lowered = host.lower()
    if lowered.startswith("0x"):
        return True
    if lowered.isdigit() and len(lowered) > 3:
        return True
    parts = lowered.split(".")
    return all(part.isdigit() or part.startswith("0x") for part in parts) and len(parts) != 4


def normalize_ip_literal(value: str) -> str:
    ip = ipaddress.ip_address(value)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return str(ip)


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_global and not ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_multicast)


def redact_query(query: str) -> str:
    if not query:
        return ""
    pairs = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key.strip().lower() in SENSITIVE_QUERY_KEYS:
            pairs.append(f"{quote(key)}=REDACTED")
        else:
            pairs.append(f"{quote(key)}={quote(value)}")
    return "&".join(pairs)

from __future__ import annotations

import gzip
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.imports.dependencies import reset_import_dependencies_for_tests
from app.imports.url_fetcher import (
    FixtureHTTPTransport,
    FixtureHostResolver,
    FixturePage,
    SecureURLFetcher,
    SocketHTTPTransport,
    URLFetchLimits,
    decode_content,
    read_http_response,
)
from app.imports.url_policy import ResolvedAddress, URLNetworkPolicy
from app.main import app
from app.persistence.database import SQLiteConnectionFactory
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from app.trips.errors import TripError
from tests.test_trip_persistence_api import simple_itinerary


class URLImportSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "trip-store.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
                "IMPORT_ARTIFACT_STORE_MODE": "memory",
                "IMPORT_URL_FETCHER_MODE": "fixture",
                "IMPORT_URL_ROBOTS_FAIL_CLOSED": "true",
                "IMPORT_URL_MAX_TEXT_BYTES": "512000",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()
        reset_import_dependencies_for_tests()

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        reset_import_dependencies_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_policy_rejects_sensitive_internal_and_ambiguous_urls(self) -> None:
        policy = URLNetworkPolicy()
        cases = [
            ("file:///etc/passwd", "import_url_scheme_unsupported"),
            ("https://user:pass@example.com/guide", "import_url_userinfo_forbidden"),
            ("https://example.com/guide?access_token=abc", "import_url_contains_sensitive_parameters"),
            ("https://example.com/guide?signature=abc", "import_url_contains_sensitive_parameters"),
            ("https://localhost/guide", "import_url_destination_blocked"),
            ("https://localhost./guide", "import_url_host_invalid"),
            ("https://127.1/guide", "import_url_host_invalid"),
            ("https://2130706433/guide", "import_url_destination_blocked"),
            ("https://0x7f000001/guide", "import_url_destination_blocked"),
            ("https://017700000001/guide", "import_url_destination_blocked"),
            ("https://example.com:22/guide", "import_url_port_forbidden"),
            ("https://[::1]/guide", "import_url_destination_blocked"),
            ("https://[::ffff:127.0.0.1]/guide", "import_url_destination_blocked"),
        ]
        for url, code in cases:
            with self.subTest(url=url), self.assertRaises(TripError) as raised:
                policy.normalize_url(url)
            self.assertEqual(raised.exception.code, code)

    def test_policy_rejects_mixed_dns_and_peer_mismatch(self) -> None:
        policy = URLNetworkPolicy()
        with self.assertRaises(TripError) as mixed:
            policy.validate_resolved_addresses(
                [
                    ResolvedAddress(host="example.com", port=443, ip="93.184.216.34", family=0),
                    ResolvedAddress(host="example.com", port=443, ip="10.0.0.1", family=0),
                ]
            )
        self.assertEqual(mixed.exception.code, "import_url_destination_blocked")
        with self.assertRaises(TripError) as mismatch:
            policy.validate_peer_address(
                peer_ip="127.0.0.1",
                approved=[ResolvedAddress(host="example.com", port=443, ip="93.184.216.34", family=0)],
            )
        self.assertEqual(mismatch.exception.code, "import_url_peer_address_mismatch")

    def test_policy_rejects_reserved_metadata_and_non_global_ip_classes(self) -> None:
        policy = URLNetworkPolicy()
        blocked = [
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "192.0.2.1",
            "198.18.0.1",
            "224.0.0.1",
            "240.0.0.1",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff02::1",
            "::ffff:169.254.169.254",
        ]
        for ip in blocked:
            with self.subTest(ip=ip), self.assertRaises(TripError):
                policy.validate_resolved_addresses([ResolvedAddress(host="example.com", port=443, ip=ip, family=0)])

    def test_url_import_reuses_review_pipeline_and_preserves_provenance(self) -> None:
        client, trip_id = create_saved_trip()
        created = create_url_import(client, trip_id, "https://fixture.invalid/guide")

        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["job"]["input_type"], "url")
        self.assertIn(body["job"]["status"], {"review_ready", "partial"})
        self.assertEqual(body["artifact"]["artifact_type"], "derived_text")
        self.assertEqual(body["source_fetch"]["robots_status"], "allowed")
        self.assertEqual(body["source_fetch"]["redirect_chain"], [])
        self.assertEqual(body["derivation"]["derivation_type"], "html_to_text")

        artifact = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/artifact")
        self.assertEqual(artifact.status_code, 200)
        self.assertIn("豫园", artifact.text)
        self.assertIn("no-store", artifact.headers["cache-control"])
        self.assertEqual(artifact.headers["x-content-type-options"], "nosniff")
        self.assertTrue(
            all(artifact.text[m["start_offset"]:m["end_offset"]] == m["raw_text"] for m in body["mentions"])
        )

    def test_url_import_redirect_robots_and_dynamic_failures_are_explicit(self) -> None:
        client, trip_id = create_saved_trip()
        redirect = create_url_import(client, trip_id, "https://fixture.invalid/redirect", key="url-redirect")
        self.assertEqual(redirect.status_code, 201, redirect.text)
        self.assertEqual(len(redirect.json()["source_fetch"]["redirect_chain"]), 1)

        robots = create_url_import(client, trip_id, "https://blocked.invalid/guide", key="url-robots")
        self.assertEqual(robots.status_code, 422)
        self.assertEqual(robots.json()["error"]["code"], "import_url_robots_disallowed")

        dynamic = create_url_import(client, trip_id, "https://fixture.invalid/js-shell", key="url-js")
        self.assertEqual(dynamic.status_code, 422)
        self.assertEqual(dynamic.json()["error"]["code"], "import_url_dynamic_rendering_required")

        pdf = create_url_import(client, trip_id, "https://fixture.invalid/file.pdf", key="url-pdf")
        self.assertEqual(pdf.status_code, 422)
        self.assertEqual(pdf.json()["error"]["code"], "import_url_unsupported_content_type")

    def test_dns_rebinding_peer_mismatch_is_blocked(self) -> None:
        pages = {
            "https://rebinding.invalid/robots.txt": FixturePage(body=b"User-agent: *\nAllow: /\n", peer_ip="93.184.216.34"),
            "https://rebinding.invalid/guide": FixturePage(
                body=b"<html><body><article>Shanghai guide</article></body></html>",
                peer_ip="127.0.0.1",
            ),
        }
        fetcher = SecureURLFetcher(
            resolver=FixtureHostResolver({"rebinding.invalid": ["93.184.216.34"]}),
            transport=FixtureHTTPTransport(pages),
            limits=URLFetchLimits(),
        )
        with self.assertRaises(TripError) as raised:
            fetcher.fetch("https://rebinding.invalid/guide")
        self.assertEqual(raised.exception.code, "import_url_peer_address_mismatch")

    def test_socket_transport_connects_to_approved_ip_and_ignores_proxy_env(self) -> None:
        policy = URLNetworkPolicy()
        url = policy.normalize_url("http://example.com/guide")
        address = ResolvedAddress(host="example.com", port=80, ip="93.184.216.34", family=0)
        captured: list[tuple[str, int]] = []

        def fake_create_connection(target, timeout):
            captured.append(target)
            return FakeSocket(
                [
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\n\r\nhello",
                ],
                peer_ip="93.184.216.34",
            )

        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:8888", "HTTPS_PROXY": "http://127.0.0.1:8888"}):
            with patch("socket.create_connection", side_effect=fake_create_connection):
                response = SocketHTTPTransport().get(
                    url=url,
                    address=address,
                    user_agent="test-agent",
                    limits=URLFetchLimits(),
                )

        self.assertEqual(captured, [("93.184.216.34", 80)])
        self.assertEqual(response.peer_ip, "93.184.216.34")
        self.assertEqual(response.body, b"hello")

    def test_robots_disallow_prevents_page_request(self) -> None:
        pages = {
            "https://blocked.invalid/robots.txt": FixturePage(body=b"User-agent: *\nDisallow: /\n"),
            "https://blocked.invalid/guide": FixturePage(body=b"<article>Should not be fetched</article>"),
        }
        transport = CountingFixtureHTTPTransport(pages)
        fetcher = SecureURLFetcher(
            resolver=FixtureHostResolver({"blocked.invalid": ["93.184.216.34"]}),
            transport=transport,
            limits=URLFetchLimits(),
        )
        with self.assertRaises(TripError) as raised:
            fetcher.fetch("https://blocked.invalid/guide")
        self.assertEqual(raised.exception.code, "import_url_robots_disallowed")
        self.assertEqual(transport.calls, ["https://blocked.invalid/robots.txt"])

    def test_redirect_escape_targets_are_revalidated(self) -> None:
        pages = {
            "https://fixture.invalid/robots.txt": FixturePage(body=b"User-agent: *\nAllow: /\n"),
            "https://fixture.invalid/private-redirect": FixturePage(
                status_code=302,
                headers={"location": "http://127.0.0.1/metadata"},
                body=b"",
            ),
        }
        fetcher = SecureURLFetcher(
            resolver=FixtureHostResolver({"fixture.invalid": ["93.184.216.34"]}),
            transport=FixtureHTTPTransport(pages),
            limits=URLFetchLimits(),
        )
        with self.assertRaises(TripError) as raised:
            fetcher.fetch("https://fixture.invalid/private-redirect")
        self.assertEqual(raised.exception.code, "import_url_destination_blocked")

    def test_streaming_limits_content_length_and_decompression_are_enforced(self) -> None:
        limits = URLFetchLimits(max_compressed_bytes=12, max_decoded_bytes=40, max_compression_ratio=4)
        content_length_stream = FakeSocket(
            [b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n\r\n"],
        )
        with self.assertRaises(TripError) as raised:
            read_http_response(content_length_stream, limits)
        self.assertEqual(raised.exception.code, "import_url_content_too_large")

        streaming_overflow = FakeSocket(
            [
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n123456",
                b"7890123",
            ],
        )
        with self.assertRaises(TripError) as streamed:
            read_http_response(streaming_overflow, limits)
        self.assertEqual(streamed.exception.code, "import_url_content_too_large")

        malformed = gzip.compress(b"hello")[:6]
        with self.assertRaises(TripError) as malformed_error:
            decode_content(malformed, "gzip", limits=URLFetchLimits(max_decoded_bytes=100))
        self.assertEqual(malformed_error.exception.code, "import_url_invalid_content_encoding")

        decoded_over = gzip.compress(b"x" * 80)
        with self.assertRaises(TripError) as decoded_error:
            decode_content(decoded_over, "gzip", limits=URLFetchLimits(max_decoded_bytes=40, max_compression_ratio=1000))
        self.assertEqual(decoded_error.exception.code, "import_url_decompressed_too_large")

        ratio_over = gzip.compress(b"x" * 2000)
        with self.assertRaises(TripError) as ratio_error:
            decode_content(ratio_over, "gzip", limits=URLFetchLimits(max_decoded_bytes=5000, max_compression_ratio=2))
        self.assertEqual(ratio_error.exception.code, "import_url_decompressed_too_large")

    def test_sensitive_url_rejection_does_not_create_import_records_or_echo_secret(self) -> None:
        client, trip_id = create_saved_trip()
        response = create_url_import(
            client,
            trip_id,
            "https://fixture.invalid/guide?signature=private-secret",
            key="url-sensitive",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "import_url_contains_sensitive_parameters")
        self.assertNotIn("private-secret", response.text)
        factory = SQLiteConnectionFactory(Path(self.temp_dir.name) / "trip-store.sqlite3")
        with factory.connect() as connection:
            import_jobs = connection.execute("SELECT COUNT(*) FROM import_jobs").fetchone()[0]
            artifacts = connection.execute("SELECT COUNT(*) FROM source_artifacts").fetchone()[0]
            snapshots = connection.execute("SELECT COUNT(*) FROM url_fetch_snapshots").fetchone()[0]
        self.assertEqual(import_jobs, 0)
        self.assertEqual(artifacts, 0)
        self.assertEqual(snapshots, 0)

    def test_url_commit_creates_candidate_without_trip_revision(self) -> None:
        client, trip_id = create_saved_trip()
        body = create_url_import(client, trip_id, "https://fixture.invalid/plain.txt").json()
        place_mentions = [mention for mention in body["mentions"] if mention["entity_type"] == "place"]
        review_version = body["job"]["review_version"]
        for index, mention in enumerate(place_mentions):
            decision = client.post(
                f"/trips/{trip_id}/imports/{body['job']['id']}/mentions/{mention['id']}/decisions",
                json={
                    "base_review_version": review_version,
                    "action": "confirm",
                    "selected_resolution_candidate_id": mention["selected_resolution_candidate_id"],
                    "cross_city_confirmed": True,
                },
                headers={"Origin": "http://testserver", "X-Idempotency-Key": f"url-confirm-{index}"},
            )
            self.assertEqual(decision.status_code, 200, decision.text)
            review_version = decision.json()["job"]["review_version"]
        before = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        committed = client.post(
            f"/trips/{trip_id}/imports/{body['job']['id']}/commit",
            json={"base_review_version": review_version},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "url-commit"},
        )
        self.assertEqual(committed.status_code, 200, committed.text)
        after = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        self.assertEqual([revision["id"] for revision in after], [revision["id"] for revision in before])
        candidates = client.get(f"/trips/{trip_id}/candidates").json()["candidates"]
        self.assertEqual({candidate["source_kind"] for candidate in candidates}, {"url_import"})
        self.assertTrue(any(ref.startswith("fetch:") for candidate in candidates for ref in candidate["evidence_refs"]))

    def test_url_fetch_snapshot_is_immutable_in_sqlite(self) -> None:
        client, trip_id = create_saved_trip()
        body = create_url_import(client, trip_id, "https://fixture.invalid/guide").json()
        factory = SQLiteConnectionFactory(Path(self.temp_dir.name) / "trip-store.sqlite3")
        with factory.connect() as connection:
            with self.assertRaises(Exception):
                connection.execute(
                    "UPDATE url_fetch_snapshots SET status_code = 201 WHERE id = ?",
                    (body["source_fetch"]["id"],),
                )


def create_saved_trip() -> tuple[TestClient, str]:
    client = TestClient(app)
    with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary()):
        created = client.post(
            "/trips/plan",
            json={"itinerary_request": {"city": "上海", "trip_days": 1, "scenic_spots": [], "restaurants": []}},
        )
    assert created.status_code == 201, created.text
    return client, created.json()["trip"]["id"]


def create_url_import(client: TestClient, trip_id: str, url: str, *, key: str = "url-import"):
    return client.post(
        f"/trips/{trip_id}/imports/url",
        json={"url": url},
        headers={"Origin": "http://testserver", "X-Idempotency-Key": key},
    )


class CountingFixtureHTTPTransport(FixtureHTTPTransport):
    def __init__(self, pages: dict[str, FixturePage]) -> None:
        super().__init__(pages)
        self.calls: list[str] = []

    def get(self, *, url, address, user_agent, limits):
        self.calls.append(url.normalized_url)
        return super().get(url=url, address=address, user_agent=user_agent, limits=limits)


class FakeSocket:
    def __init__(self, chunks: list[bytes], *, peer_ip: str = "93.184.216.34") -> None:
        self.chunks = list(chunks)
        self.peer_ip = peer_ip
        self.sent = b""

    def recv(self, size: int) -> bytes:
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) > size:
            self.chunks.insert(0, chunk[size:])
            return chunk[:size]
        return chunk

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def getpeername(self):
        return (self.peer_ip, 80)

    def settimeout(self, timeout: float) -> None:
        return None

    def close(self) -> None:
        return None

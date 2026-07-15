from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.imports.dependencies import reset_import_dependencies_for_tests
from app.imports.url_fetcher import FixtureHTTPTransport, FixtureHostResolver, FixturePage, SecureURLFetcher, URLFetchLimits
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
            ("https://localhost/guide", "import_url_destination_blocked"),
            ("https://127.1/guide", "import_url_host_invalid"),
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

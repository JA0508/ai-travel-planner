from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.imports.capability_pack import ImportRuntimeCapabilities, build_import_capability_pack
from app.imports.dependencies import reset_import_dependencies_for_tests
from app.main import app
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from tests.test_trip_persistence_api import simple_itinerary


class ImportCapabilityPackAssemblerTests(unittest.TestCase):
    def test_all_forms_are_available_when_their_safe_prerequisites_are_present(self) -> None:
        snapshot = build_import_capability_pack(
            ImportRuntimeCapabilities(
                text_enabled=True,
                url_enabled=True,
                binary_enabled=True,
                inspection_available=True,
                document_extraction_enabled=True,
                ocr_available=True,
                pdf_renderer_available=True,
            )
        )

        self.assertEqual(snapshot.schema_version, "1.0")
        self.assertEqual([form.form.value for form in snapshot.forms], ["text", "url", "image", "pdf"])
        self.assertEqual([form.availability.value for form in snapshot.forms], ["available"] * 4)
        self.assertTrue(all(not form.reason_codes for form in snapshot.forms))
        self.assertEqual(
            [stage.value for stage in snapshot.forms[0].processing_stages],
            ["source_artifact", "mention_extraction", "resolution", "review"],
        )

    def test_missing_binary_extraction_capabilities_only_degrade_image_and_pdf(self) -> None:
        snapshot = build_import_capability_pack(
            ImportRuntimeCapabilities(
                text_enabled=True,
                url_enabled=True,
                binary_enabled=True,
                inspection_available=True,
                document_extraction_enabled=True,
                ocr_available=False,
                pdf_renderer_available=False,
            )
        )
        forms = {form.form.value: form for form in snapshot.forms}

        self.assertEqual(forms["text"].availability.value, "available")
        self.assertEqual(forms["url"].availability.value, "available")
        self.assertEqual(forms["image"].availability.value, "degraded")
        self.assertEqual(forms["image"].reason_codes, ["ocr_unavailable"])
        self.assertEqual(forms["pdf"].availability.value, "degraded")
        self.assertEqual(forms["pdf"].reason_codes, ["ocr_unavailable", "pdf_renderer_unavailable"])

    def test_disabled_text_and_url_are_unavailable_without_changing_binary_forms(self) -> None:
        snapshot = build_import_capability_pack(
            ImportRuntimeCapabilities(
                text_enabled=False,
                url_enabled=False,
                binary_enabled=True,
                inspection_available=True,
                document_extraction_enabled=True,
                ocr_available=True,
                pdf_renderer_available=True,
            )
        )
        forms = {form.form.value: form for form in snapshot.forms}

        self.assertEqual(forms["text"].availability.value, "unavailable")
        self.assertEqual(forms["text"].reason_codes, ["text_import_disabled"])
        self.assertEqual(forms["url"].availability.value, "unavailable")
        self.assertEqual(forms["url"].reason_codes, ["url_import_disabled"])
        self.assertEqual(forms["image"].availability.value, "available")
        self.assertEqual(forms["pdf"].availability.value, "available")


class ImportCapabilityPackRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.redaction_canary = "capability-redaction-canary"
        self.private_path = str(Path(self.temp_dir.name) / "private-artifacts")
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "trip-store.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
                "IMPORT_ARTIFACT_ROOT": self.private_path,
                "IMPORT_DOCUMENT_OCR_COMMAND": self.redaction_canary,
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

    def test_snapshot_requires_trip_capability_and_does_not_leak_it(self) -> None:
        authorized_client, trip_id = create_saved_trip()
        denied = TestClient(app).get(f"/trips/{trip_id}/imports/capabilities")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "trip_access_denied")
        self.assertNotIn("forms", denied.text)
        self.assertNotIn(self.redaction_canary, denied.text)
        self.assertNotIn(self.private_path, denied.text)

        before_revisions = authorized_client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        response = authorized_client.get(f"/trips/{trip_id}/imports/capabilities")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual([form["form"] for form in payload["forms"]], ["text", "url", "image", "pdf"])
        self.assertNotIn(self.redaction_canary, response.text)
        self.assertNotIn(self.private_path, response.text)
        self.assertNotIn("trip_capability", response.text)
        self.assertEqual(authorized_client.get(f"/trips/{trip_id}/revisions").json()["revisions"], before_revisions)
        self.assertEqual(authorized_client.get(f"/trips/{trip_id}/candidates").json()["candidates"], [])


def create_saved_trip() -> tuple[TestClient, str]:
    client = TestClient(app)
    with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary()):
        created = client.post(
            "/trips/plan",
            json={
                "itinerary_request": {
                    "city": "上海",
                    "trip_days": 1,
                    "scenic_spots": [],
                    "restaurants": [],
                }
            },
        )
    assert created.status_code == 201, created.text
    return client, created.json()["trip"]["id"]

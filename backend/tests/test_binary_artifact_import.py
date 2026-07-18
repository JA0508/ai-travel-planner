from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from app.imports.dependencies import reset_import_dependencies_for_tests
from app.main import app
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from tests.test_trip_persistence_api import simple_itinerary


class BinaryArtifactImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "trip-store.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
                "IMPORT_ARTIFACT_STORE_MODE": "local",
                "IMPORT_ARTIFACT_ROOT": str(Path(self.temp_dir.name) / "artifacts"),
                "IMPORT_BINARY_STAGING_ROOT": str(Path(self.temp_dir.name) / "staging"),
                "IMPORT_BINARY_UPLOAD_CHUNK_BYTES": "17",
                "IMPORT_BINARY_MAX_IMAGE_BYTES": "1048576",
                "IMPORT_BINARY_MAX_PDF_BYTES": "1048576",
                "IMPORT_IMAGE_MAX_PIXELS": "4000000",
                "IMPORT_PDF_MAX_PAGES": "10",
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

    def test_valid_image_is_quarantined_inspected_and_serves_only_sanitized_derivative(self) -> None:
        client, trip_id = create_saved_trip()
        created = upload_binary(client, trip_id, valid_image("PNG"), "image", "guide.png", "image/png")

        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["job"]["input_type"], "image")
        self.assertEqual(body["job"]["status"], "artifact_ready")
        self.assertEqual(body["job"]["mention_count"], 0)
        self.assertEqual(body["artifact"]["artifact_type"], "uploaded_image")
        self.assertNotIn("storage_key", body["artifact"])
        self.assertTrue(body["inspection"]["sanitized_artifact_id"])
        self.assertEqual(body["inspection"]["metadata"]["metadata_present"], False)

        original = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/artifact")
        self.assertEqual(original.status_code, 409)
        self.assertEqual(original.json()["error"]["code"], "import_artifact_original_not_inlineable")

        preview = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/sanitized-image")
        self.assertEqual(preview.status_code, 200)
        self.assertIn(preview.headers["content-type"].split(";")[0], {"image/png", "image/jpeg"})
        self.assertIn("no-store", preview.headers["cache-control"])
        self.assertEqual(preview.headers["x-content-type-options"], "nosniff")

        self.assertEqual(client.get(f"/trips/{trip_id}/candidates").json()["candidates"], [])
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)

    def test_valid_pdf_creates_manifest_without_inline_binary_serving(self) -> None:
        client, trip_id = create_saved_trip()
        created = upload_binary(client, trip_id, valid_pdf(), "pdf", "guide.pdf", "application/pdf")

        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["job"]["input_type"], "pdf")
        self.assertEqual(body["job"]["status"], "artifact_ready")
        self.assertEqual(body["job"]["mention_count"], 0)
        self.assertEqual(body["inspection"]["manifest_artifact_id"], body["derivation"]["child_artifact_id"])
        self.assertEqual(body["inspection"]["metadata"]["page_count"], 1)
        self.assertFalse(body["inspection"]["metadata"]["encrypted"])

        original = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/artifact")
        self.assertEqual(original.status_code, 409)
        preview = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/sanitized-image")
        self.assertEqual(preview.status_code, 409)

    def test_encrypted_and_active_content_pdf_are_explicit_non_ready_states(self) -> None:
        client, trip_id = create_saved_trip()
        encrypted = upload_binary(client, trip_id, encrypted_pdf(), "pdf", "locked.pdf", "application/pdf")
        self.assertEqual(encrypted.status_code, 201, encrypted.text)
        self.assertEqual(encrypted.json()["job"]["status"], "needs_password")
        self.assertEqual(encrypted.json()["inspection"]["findings"][0]["code"], "PDF_ENCRYPTED")

        active = upload_binary(client, trip_id, javascript_pdf(), "pdf", "active.pdf", "application/pdf", key="active-pdf")
        self.assertEqual(active.status_code, 201, active.text)
        self.assertEqual(active.json()["job"]["status"], "rejected")
        finding_codes = {finding["code"] for finding in active.json()["inspection"]["findings"]}
        self.assertIn("PDF_JAVASCRIPT_PRESENT", finding_codes)

    def test_content_detection_rejects_mismatch_polyglot_empty_and_too_large(self) -> None:
        client, trip_id = create_saved_trip()
        mismatch = upload_binary(client, trip_id, valid_pdf(), "image", "guide.jpg", "image/jpeg")
        self.assertEqual(mismatch.status_code, 422)
        self.assertEqual(mismatch.json()["error"]["code"], "import_binary_declared_type_mismatch")

        executable = upload_binary(client, trip_id, b"MZnot-an-image", "image", "guide.jpg", "image/jpeg", key="exe")
        self.assertEqual(executable.status_code, 422)
        self.assertEqual(executable.json()["error"]["code"], "import_binary_signature_mismatch")

        polyglot = upload_binary(client, trip_id, valid_pdf() + b"\nPK\x03\x04", "pdf", "guide.pdf", "application/pdf", key="poly")
        self.assertEqual(polyglot.status_code, 422)
        self.assertEqual(polyglot.json()["error"]["code"], "import_binary_polyglot_suspected")

        empty = upload_binary(client, trip_id, b"", "image", "empty.png", "image/png", key="empty")
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(empty.json()["error"]["code"], "import_binary_empty")

        with patch.dict("os.environ", {"IMPORT_BINARY_MAX_IMAGE_BYTES": "8"}):
            reset_import_dependencies_for_tests()
            oversized = upload_binary(client, trip_id, valid_image("PNG"), "image", "big.png", "image/png", key="big")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["error"]["code"], "import_binary_too_large")

    def test_idempotency_and_reload_preserve_inspection_lineage(self) -> None:
        client, trip_id = create_saved_trip()
        image_bytes = valid_image("JPEG")
        first = upload_binary(client, trip_id, image_bytes, "image", "../CON.jpg", "image/jpeg", key="same-key")
        replay = upload_binary(client, trip_id, image_bytes, "image", "../CON.jpg", "image/jpeg", key="same-key")
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(first.json()["job"]["id"], replay.json()["job"]["id"])
        self.assertNotIn("..", first.json()["artifact"].get("original_label") or "")

        conflict = upload_binary(client, trip_id, valid_image("PNG"), "image", "other.png", "image/png", key="same-key")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "idempotency_conflict")

        inspection = client.get(f"/trips/{trip_id}/imports/{first.json()['job']['id']}/inspection")
        self.assertEqual(inspection.status_code, 200)
        self.assertEqual(inspection.json()["artifact_id"], first.json()["artifact"]["id"])


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


def upload_binary(
    client: TestClient,
    trip_id: str,
    content: bytes,
    declared_kind: str,
    filename: str,
    mime_type: str,
    *,
    key: str = "binary-one",
):
    return client.post(
        f"/trips/{trip_id}/imports/artifacts",
        data={"declared_kind": declared_kind, "original_label": filename},
        files={"file": (filename, content, mime_type)},
        headers={"Origin": "http://testserver", "X-Idempotency-Key": key},
    )


def valid_image(fmt: str) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGBA" if fmt == "PNG" else "RGB", (24, 16), (120, 30, 20, 255) if fmt == "PNG" else (120, 30, 20))
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def valid_pdf(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _index in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def javascript_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_js("app.alert('x')")
    writer._root_object.update({NameObject("/OpenAction"): DictionaryObject({NameObject("/S"): NameObject("/JavaScript")})})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.imports.dependencies import reset_import_dependencies_for_tests
from app.imports.binary_upload import stream_upload_to_staging
from app.imports.inspection_runner import ArtifactInspectionRunner
from app.imports.repository import SQLiteImportRepository
from app.main import app
from app.trips.errors import TripError
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

    def test_stream_upload_stops_after_limit_and_cleans_staging(self) -> None:
        class ChunkedUpload:
            filename = "../dangerous.png"
            content_type = "image/png"

            def __init__(self) -> None:
                self.reads = 0
                self.closed = False
                self.chunks = [b"abcd", b"efgh", b"ijkl", b"mnop"]

            async def read(self, _chunk_bytes: int) -> bytes:
                self.reads += 1
                return self.chunks.pop(0) if self.chunks else b""

            async def close(self) -> None:
                self.closed = True

        upload = ChunkedUpload()
        staging_root = Path(self.temp_dir.name) / "upload-staging"
        with self.assertRaises(TripError) as raised:
            asyncio.run(
                stream_upload_to_staging(
                    upload_file=upload,  # type: ignore[arg-type]
                    staging_root=staging_root,
                    max_bytes=6,
                    chunk_bytes=4,
                    original_label=upload.filename,
                )
            )
        self.assertEqual(raised.exception.code, "import_binary_too_large")
        self.assertEqual(upload.reads, 2)
        self.assertTrue(upload.closed)
        self.assertEqual(list(staging_root.glob("*")), [])

    def test_inspection_runner_enforces_timeout_worker_failure_and_invalid_output(self) -> None:
        runner = ArtifactInspectionRunner(timeout_seconds=0.01, max_memory_mb=64, max_output_bytes=64)
        source = Path(self.temp_dir.name) / "artifact.bin"
        source.write_bytes(valid_image("PNG"))

        with patch("app.imports.inspection_runner.subprocess.Popen", return_value=FakeProcess(timeout=True)), patch(
            "app.imports.inspection_runner.os.killpg"
        ) as killpg:
            with self.assertRaises(TripError) as raised:
                runner.inspect(path=source, declared_kind="image", detected_mime_type="image/png", sanitized_output_path=None, limits={})
            self.assertEqual(raised.exception.code, "import_inspection_timeout")
            killpg.assert_called_once()

        with patch("app.imports.inspection_runner.subprocess.Popen", return_value=FakeProcess(returncode=2)):
            with self.assertRaises(TripError) as raised:
                runner.inspect(path=source, declared_kind="image", detected_mime_type="image/png", sanitized_output_path=None, limits={})
            self.assertEqual(raised.exception.code, "import_inspection_worker_failed")

        with patch("app.imports.inspection_runner.subprocess.Popen", return_value=FakeProcess(stdout=b"not-json")):
            with self.assertRaises(TripError) as raised:
                runner.inspect(path=source, declared_kind="image", detected_mime_type="image/png", sanitized_output_path=None, limits={})
            self.assertEqual(raised.exception.code, "import_inspection_output_invalid")

        with patch("app.imports.inspection_runner.subprocess.Popen", return_value=FakeProcess(stdout=b"x" * 65)):
            with self.assertRaises(TripError) as raised:
                runner.inspect(path=source, declared_kind="image", detected_mime_type="image/png", sanitized_output_path=None, limits={})
            self.assertEqual(raised.exception.code, "import_inspection_output_invalid")

    def test_derivative_bytes_are_removed_when_inspection_transaction_fails(self) -> None:
        client, trip_id = create_saved_trip(raise_server_exceptions=False)

        def fail_after_derivative_write(*_args, **_kwargs):
            raise RuntimeError("forced transaction failure")

        with patch.object(SQLiteImportRepository, "create_completed_artifact_inspection", fail_after_derivative_write):
            failed = upload_binary(client, trip_id, valid_image("PNG"), "image", "guide.png", "image/png")

        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.json()["error"]["code"], "import_binary_quarantine_failed")
        self.assertNotIn(str(self.temp_dir.name), failed.text)
        artifacts_root = Path(self.temp_dir.name) / "artifacts"
        self.assertEqual(list((artifacts_root / "sanitized-image").glob("*")), [])
        self.assertTrue(list((artifacts_root / "uploaded-image").glob("*")))

    def test_pdf_native_text_extraction_creates_document_review_without_trip_mutation(self) -> None:
        client, trip_id = create_saved_trip()
        uploaded = upload_binary(client, trip_id, text_pdf("景点：豫园、上海博物馆"), "pdf", "guide.pdf", "application/pdf")
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        binary_job_id = uploaded.json()["job"]["id"]
        before_revisions = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]

        extracted = client.post(
            f"/trips/{trip_id}/imports/{binary_job_id}/extract-document",
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "extract-pdf-native"},
        )

        self.assertEqual(extracted.status_code, 201, extracted.text)
        body = extracted.json()
        self.assertEqual(body["generation"]["strategy"], "pdf_native_text")
        self.assertEqual(body["generation"]["status"], "review_ready")
        self.assertEqual(body["artifact"]["artifact_type"], "document_text")
        self.assertEqual(body["job"]["input_type"], "document")
        self.assertGreaterEqual(body["job"]["mention_count"], 2)
        self.assertTrue(body["spans"])
        self.assertTrue(all(span["page_number"] == 1 for span in body["spans"]))
        self.assertTrue(all({"x0", "y0", "x1", "y1", "unit"}.issubset(span["bbox"]) for span in body["spans"]))
        text = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/artifact")
        self.assertEqual(text.status_code, 200)
        self.assertIn("豫园", text.text)
        self.assertIn("上海博物馆", text.text)

        review_version = body["job"]["review_version"]
        for index, mention in enumerate([item for item in body["mentions"] if item["entity_type"] == "place"]):
            decision = client.post(
                f"/trips/{trip_id}/imports/{body['job']['id']}/mentions/{mention['id']}/decisions",
                json={
                    "base_review_version": review_version,
                    "action": "confirm",
                    "selected_resolution_candidate_id": mention["selected_resolution_candidate_id"],
                },
                headers={"Origin": "http://testserver", "X-Idempotency-Key": f"confirm-doc-{index}"},
            )
            self.assertEqual(decision.status_code, 200, decision.text)
            review_version = decision.json()["job"]["review_version"]
        committed = client.post(
            f"/trips/{trip_id}/imports/{body['job']['id']}/commit",
            json={"base_review_version": review_version},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "commit-doc"},
        )
        self.assertEqual(committed.status_code, 200, committed.text)
        self.assertEqual(
            [revision["id"] for revision in before_revisions],
            [revision["id"] for revision in client.get(f"/trips/{trip_id}/revisions").json()["revisions"]],
        )
        candidates = client.get(f"/trips/{trip_id}/candidates").json()["candidates"]
        self.assertEqual({candidate["source_kind"] for candidate in candidates}, {"document_import"})

        replay = client.post(
            f"/trips/{trip_id}/imports/{binary_job_id}/extract-document",
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "extract-pdf-native"},
        )
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(replay.json()["job"]["id"], body["job"]["id"])

    def test_rejected_or_unready_binary_artifact_cannot_be_extracted(self) -> None:
        client, trip_id = create_saved_trip()
        rejected = upload_binary(client, trip_id, javascript_pdf(), "pdf", "active.pdf", "application/pdf")
        self.assertEqual(rejected.status_code, 201, rejected.text)
        response = client.post(
            f"/trips/{trip_id}/imports/{rejected.json()['job']['id']}/extract-document",
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "extract-rejected"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "import_document_source_not_ready")

    def test_image_ocr_missing_engine_is_explicit_and_creates_no_review_or_mutation(self) -> None:
        client, trip_id = create_saved_trip()
        uploaded = upload_binary(client, trip_id, valid_image("PNG"), "image", "guide.png", "image/png")
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        before_revisions = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        with patch.dict("os.environ", {"IMPORT_DOCUMENT_OCR_COMMAND": "definitely-not-installed-tesseract"}):
            response = client.post(
                f"/trips/{trip_id}/imports/{uploaded.json()['job']['id']}/extract-document",
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "extract-image-no-ocr"},
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "import_document_ocr_unavailable")
        self.assertEqual(client.get(f"/trips/{trip_id}/candidates").json()["candidates"], [])
        self.assertEqual(
            [revision["id"] for revision in before_revisions],
            [revision["id"] for revision in client.get(f"/trips/{trip_id}/revisions").json()["revisions"]],
        )

    @unittest.skipUnless(shutil.which("tesseract"), "tesseract OCR engine is not installed")
    def test_image_ocr_engine_creates_layout_spans_and_review_artifact(self) -> None:
        client, trip_id = create_saved_trip()
        uploaded = upload_binary(client, trip_id, text_image("Starbucks Reserve Roastery"), "image", "ocr.png", "image/png")
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        with patch.dict("os.environ", {"IMPORT_DOCUMENT_OCR_LANGUAGES": "eng"}):
            response = client.post(
                f"/trips/{trip_id}/imports/{uploaded.json()['job']['id']}/extract-document",
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "extract-image-ocr"},
            )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["generation"]["strategy"], "image_ocr")
        self.assertEqual(body["job"]["input_type"], "document")
        self.assertTrue(body["spans"])
        self.assertTrue(all(span["source_kind"] == "ocr_token" for span in body["spans"]))
        text = client.get(f"/trips/{trip_id}/imports/{body['job']['id']}/artifact")
        self.assertEqual(text.status_code, 200)
        self.assertIn("Starbucks", text.text)


def create_saved_trip(*, raise_server_exceptions: bool = True) -> tuple[TestClient, str]:
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
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


def text_image(text: str) -> bytes:
    image = Image.new("RGB", (760, 140), "white")
    draw = ImageDraw.Draw(image)
    font = load_test_font(42)
    draw.text((24, 42), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def load_test_font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def valid_pdf(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _index in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def text_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=420, height=300)
    font = DictionaryObject()
    font.update(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 16 Tf 40 240 Td ({escaped}) Tj ET".encode("utf-8"))
    page[NameObject("/Contents")] = writer._add_object(stream)
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


class FakeProcess:
    pid = 12345

    def __init__(self, *, stdout: bytes = b"{}", stderr: bytes = b"", returncode: int = 0, timeout: bool = False) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        if timeout is not None and self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired(cmd=["inspection-worker"], timeout=timeout)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True

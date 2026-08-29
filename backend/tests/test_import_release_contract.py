from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import run_import_evaluation


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "backend" / "tests" / "fixtures" / "import_release_manifest.json"


class ImportReleaseContractManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_tracks_real_import_evaluation_fixture_collections(self) -> None:
        collections = {
            "FIXTURES": run_import_evaluation.FIXTURES,
            "URL_FIXTURES": run_import_evaluation.URL_FIXTURES,
            "BINARY_FIXTURES": run_import_evaluation.BINARY_FIXTURES,
            "DOCUMENT_EXTRACTION_FIXTURES": run_import_evaluation.DOCUMENT_EXTRACTION_FIXTURES,
        }

        fixture_collections = self.manifest["fixture_collections"]
        self.assertEqual({item["name"] for item in fixture_collections}, set(collections))
        for item in fixture_collections:
            collection = collections[item["name"]]
            self.assertEqual(
                item["expected_fixture_count"],
                len(collection),
                f"manifest count must match {item['name']}",
            )

        forms = self.manifest["forms"]
        self.assertEqual({form["form"] for form in forms}, {"text", "url", "image", "pdf"})
        for form in forms:
            self.assertTrue(form["fixture_collections"], f"{form['form']} must link to fixture coverage")
            for collection_name in form["fixture_collections"]:
                self.assertIn(collection_name, collections)

        self.assertEqual(
            self.manifest["summary"]["total_fixture_count"],
            sum(len(collection) for collection in collections.values()),
        )
        self.assertEqual(self.manifest["summary"]["invariant_count"], len(run_import_evaluation.INVARIANTS))
        self.assertEqual(
            self.manifest["summary"]["document_extraction_invariant_count"],
            len([invariant for invariant in run_import_evaluation.INVARIANTS if invariant.startswith("DOCUMENT_")]),
        )

    def test_manifest_points_to_existing_contracts_tests_and_current_endpoints(self) -> None:
        for relative_path in self.manifest["contract_documents"]:
            self.assertTrue((ROOT / relative_path).exists(), f"{relative_path} must exist")

        for form in self.manifest["forms"]:
            for relative_path in form["focused_tests"]:
                self.assertTrue((ROOT / relative_path).exists(), f"{relative_path} must exist")

        release_doc = (ROOT / "docs" / "product" / "IMPORT_FULL_FORMAT_RELEASE.md").read_text(encoding="utf-8")
        capability_doc = (ROOT / "docs" / "architecture" / "IMPORT_CAPABILITY_PACK_CONTRACT.md").read_text(encoding="utf-8")
        for form in self.manifest["forms"]:
            self.assertIn(form["entrypoint"], release_doc)
        self.assertIn("backend/tests/fixtures/import_release_manifest.json", release_doc)
        self.assertIn("Batch 00 没有新增 schema、endpoint、环境探测或前端读取逻辑", capability_doc)

    def test_manifest_preserves_batch_00_scope_and_privacy_boundary(self) -> None:
        self.assertEqual(self.manifest["status"], "baseline_contract_only")
        self.assertEqual({gate["status"] for gate in self.manifest["release_gate_commands"]}, {"required_baseline", "ci_baseline"})
        self.assertEqual(self.manifest["future_release_gate_owner"], "Batch 04")

        forbidden_terms = " ".join(self.manifest["must_not_expose"])
        self.assertIn("raw source content", forbidden_terms)
        self.assertIn("API keys or tokens", forbidden_terms)
        self.assertIn("storage keys or absolute paths", forbidden_terms)

if __name__ == "__main__":
    unittest.main()

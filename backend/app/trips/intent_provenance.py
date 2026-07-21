from __future__ import annotations

from dataclasses import dataclass

from app.imports.repository import ImportRepository
from app.trips.candidates import CandidateEvidenceLinkRecord
from app.trips.digests import sha256_digest
from app.trips.errors import TripError
from app.trips.repository import TripRepository

from .intent_contracts import BoundingBox, IntentSourceReference


@dataclass(frozen=True, slots=True)
class CandidateEvidenceAssembly:
    refs: list[IntentSourceReference]
    verification_state: str


class VerifiedIntentEvidenceAssembler:
    """Rehydrates candidate evidence from persisted Import Review records.

    Candidate display strings are deliberately not an authority boundary.  The
    assembly below fails closed when any persisted object is absent or belongs
    to a different Trip.
    """

    def __init__(self, *, trip_repository: TripRepository, import_repository: ImportRepository) -> None:
        self.trip_repository = trip_repository
        self.import_repository = import_repository

    def assemble_candidate_evidence(
        self,
        *,
        trip_id: str,
        trip_candidate_id: str,
    ) -> CandidateEvidenceAssembly:
        candidate = self.trip_repository.get_candidate(trip_id=trip_id, candidate_id=trip_candidate_id)
        links = self.trip_repository.list_candidate_evidence_links(
            trip_id=trip_id,
            candidate_id=trip_candidate_id,
        )
        if not links:
            return CandidateEvidenceAssembly(refs=[], verification_state="legacy_unverified")

        refs: list[IntentSourceReference] = []
        for link in links:
            refs.extend(self._verify_link(trip_id=trip_id, candidate_id=candidate.id, link=link))
        return CandidateEvidenceAssembly(refs=refs, verification_state="verified")

    def _verify_link(
        self,
        *,
        trip_id: str,
        candidate_id: str,
        link: CandidateEvidenceLinkRecord,
    ) -> list[IntentSourceReference]:
        if link.trip_id != trip_id or link.trip_candidate_id != candidate_id:
            self._invalid()
        artifact = self.import_repository.get_artifact(trip_id=trip_id, artifact_id=link.source_artifact_id)
        job = self.import_repository.get_job(trip_id=trip_id, import_job_id=link.import_job_id)
        mention = self.import_repository.get_mention(import_job_id=job.id, mention_id=link.mention_id)
        decision = next(
            (item for item in self.import_repository.list_review_decisions(import_job_id=job.id) if item.id == link.review_decision_id),
            None,
        )
        if (
            job.artifact_id != artifact.id
            or mention.artifact_id != artifact.id
            or mention.import_job_id != job.id
            or decision is None
            or decision.mention_id != mention.id
            or decision.selected_resolution_candidate_id != link.resolution_candidate_id
            or decision.action not in {"confirm", "select_candidate"}
        ):
            self._invalid()
        resolution = self.import_repository.get_resolution_candidate(
            import_job_id=job.id,
            mention_id=mention.id,
            candidate_id=link.resolution_candidate_id,
        )
        expected_digest = sha256_digest(
            {
                "artifact_checksum": artifact.content_checksum,
                "mention_digest": mention.content_digest,
                "review_decision_id": decision.id,
                "resolution_digest": resolution.candidate_digest,
            }
        )
        if link.source_digest != expected_digest:
            self._invalid()

        page_number = link.document_page_number
        boxes = [BoundingBox.model_validate(item) for item in link.bounding_boxes]
        extraction_method = None
        geometry_source = None
        if link.document_generation_id is not None:
            generation = self.import_repository.get_document_extraction_for_derived_job(derived_import_job_id=job.id)
            if generation is None or generation.id != link.document_generation_id:
                self._invalid()
            spans = self.import_repository.list_document_text_spans(generation_id=generation.id)
            span = next((item for item in spans if item.id == link.document_span_id), None)
            if span is None or (page_number is not None and span.page_number != page_number):
                self._invalid()
            if span.span_start >= mention.end_offset or span.span_end <= mention.start_offset:
                self._invalid()
            if boxes and [box.model_dump(mode="json") for box in boxes] != [span.bbox]:
                self._invalid()
            page_number = span.page_number
            extraction_method = span.source_kind
            geometry_source = "document_text_span"

        common = dict(
            artifact_id=artifact.id,
            import_job_id=job.id,
            mention_id=mention.id,
            review_decision_id=decision.id,
            resolution_candidate_id=resolution.id,
            trip_candidate_id=candidate_id,
            page_number=page_number,
            bounding_boxes=boxes,
            extraction_method=extraction_method,
            geometry_source=geometry_source,
            source_digest=link.source_digest,
            authority="review_confirmed",
            confirmed=True,
            provenance_verification_state="verified",
        )
        return [
            IntentSourceReference(source_ref_id=f"artifact:{artifact.id}", source_type="source_artifact", source_id=artifact.id, **common),
            IntentSourceReference(source_ref_id=f"mention:{mention.id}", source_type="import_mention", source_id=mention.id, **common),
            IntentSourceReference(source_ref_id=f"review:{decision.id}", source_type="import_review_decision", source_id=decision.id, **common),
            IntentSourceReference(source_ref_id=f"resolution:{resolution.id}", source_type="resolution_candidate", source_id=resolution.id, **common),
            IntentSourceReference(source_ref_id=f"candidate:{candidate_id}:{mention.id}", source_type="trip_candidate", source_id=candidate_id, **common),
        ]

    @staticmethod
    def _invalid() -> None:
        raise TripError("intent_provenance_invalid", "Intent evidence does not match persisted Import Review lineage.", 422)

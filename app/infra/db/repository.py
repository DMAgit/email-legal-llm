"""Repository boundary that isolates SQLite details from services."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import PersistenceError
from app.domain.enums import ProcessingStage, ProcessingStatus, ReviewQueueStatus, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.document import ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult, DocumentExtraction
from app.domain.models.persistence import (
    DocumentEvaluation,
    ProcessRecord,
    ProcessingOutcome,
    ReviewQueueItem,
)
from app.domain.models.retrieval import RetrievedContextChunk
from app.infra.db.base import create_connection
from app.infra.db.tables import create_schema


class PersistenceRepository:
    """SQLite-backed repository for processing runs and traceability artifacts."""

    def __init__(
        self,
        database_url: str = "sqlite:///./data/app.db",
        *,
        connection: sqlite3.Connection | None = None,
        initialize: bool = True,
    ) -> None:
        self.connection = connection or create_connection(database_url)
        self._owns_connection = connection is None
        self.connection.row_factory = sqlite3.Row
        if initialize:
            try:
                create_schema(self.connection)
            except sqlite3.Error as exc:
                raise PersistenceError(f"Could not initialize persistence schema: {exc}") from exc

    def close(self) -> None:
        """Close the owned SQLite connection."""
        if self._owns_connection:
            self.connection.close()

    def create_processing_run(
        self,
        process_id: str,
        *,
        status: str = ProcessingStage.RECEIVED.value,
        current_stage: str = ProcessingStage.RECEIVED.value,
    ) -> None:
        """Create a run record, preserving any existing terminal state."""
        now = _utc_now()
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO processing_runs (
                        process_id, status, current_stage, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(process_id) DO UPDATE SET
                        updated_at = excluded.updated_at
                    """,
                    (process_id, _enum_value(status), _enum_value(current_stage), now, now),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not create processing run {process_id}: {exc}") from exc

    def update_processing_run(
        self,
        process_id: str,
        *,
        status: str | None = None,
        current_stage: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        final_action: RoutingAction | str | None = None,
        review_required: bool | None = None,
        decision_reason: str | None = None,
    ) -> None:
        """Update mutable lifecycle fields for a processing run."""
        self.create_processing_run(process_id)
        now = _utc_now()
        try:
            with self.connection:
                self.connection.execute(
                    """
                    UPDATE processing_runs
                    SET
                        status = COALESCE(?, status),
                        current_stage = COALESCE(?, current_stage),
                        updated_at = ?,
                        error_type = COALESCE(?, error_type),
                        error_message = COALESCE(?, error_message),
                        final_action = COALESCE(?, final_action),
                        review_required = COALESCE(?, review_required),
                        decision_reason = COALESCE(?, decision_reason)
                    WHERE process_id = ?
                    """,
                    (
                        _enum_value(status),
                        _enum_value(current_stage),
                        now,
                        error_type,
                        error_message,
                        _enum_value(final_action),
                        int(review_required) if review_required is not None else None,
                        decision_reason,
                        process_id,
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not update processing run {process_id}: {exc}") from exc

    def record_failure(
        self,
        process_id: str,
        *,
        current_stage: str,
        error_type: str,
        error_message: str,
        review_required: bool = True,
    ) -> None:
        """Mark a processing run failed while preserving the failing stage."""
        self.update_processing_run(
            process_id,
            status=ProcessingStatus.FAILED.value,
            current_stage=current_stage,
            error_type=error_type,
            error_message=error_message,
            final_action=RoutingAction.MANUAL_REVIEW,
            review_required=review_required,
            decision_reason="Processing failed before deterministic routing could complete.",
        )

    def save_email(self, process_id: str, email: InboundEmail) -> None:
        """Persist inbound email metadata."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO emails (
                        process_id, message_id, sender, recipient, subject, plain_text_body,
                        attachment_count, received_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(process_id) DO UPDATE SET
                        message_id = excluded.message_id,
                        sender = excluded.sender,
                        recipient = excluded.recipient,
                        subject = excluded.subject,
                        plain_text_body = excluded.plain_text_body,
                        attachment_count = excluded.attachment_count,
                        received_at = excluded.received_at
                    """,
                    (
                        process_id,
                        email.message_id,
                        email.sender,
                        email.recipient,
                        email.subject,
                        email.plain_text_body,
                        email.attachment_count,
                        email.received_at.isoformat(),
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save email metadata for {process_id}: {exc}") from exc

    def save_attachments(
        self,
        process_id: str,
        attachments: Sequence[AttachmentMetadata],
    ) -> None:
        """Persist attachment metadata for a process."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                self.connection.execute("DELETE FROM attachments WHERE process_id = ?", (process_id,))
                self.connection.executemany(
                    """
                    INSERT INTO attachments (
                        process_id, filename, content_type, size_bytes, storage_path
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            process_id,
                            attachment.filename,
                            attachment.content_type,
                            attachment.size_bytes,
                            attachment.storage_path,
                        )
                        for attachment in attachments
                    ],
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save attachments for {process_id}: {exc}") from exc

    def save_parsed_documents(
        self,
        process_id: str,
        documents: Sequence[ParsedDocument],
    ) -> None:
        """Persist parsed document artifacts."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                for document in documents:
                    self.connection.execute(
                        """
                        INSERT INTO parsed_documents (
                            process_id, document_id, filename, file_type, parser_name,
                            raw_text, extracted_tables, parse_warnings, confidence_hint
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(process_id, document_id) DO UPDATE SET
                            filename = excluded.filename,
                            file_type = excluded.file_type,
                            parser_name = excluded.parser_name,
                            raw_text = excluded.raw_text,
                            extracted_tables = excluded.extracted_tables,
                            parse_warnings = excluded.parse_warnings,
                            confidence_hint = excluded.confidence_hint
                        """,
                        (
                            process_id,
                            document.document_id,
                            document.filename,
                            document.file_type,
                            document.parser_name,
                            document.raw_text,
                            _json_dump(document.extracted_tables),
                            _json_dump(document.parse_warnings),
                            document.confidence_hint,
                        ),
                    )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save parsed documents for {process_id}: {exc}") from exc

    def save_extractions(
        self,
        process_id: str,
        extractions: Sequence[DocumentExtraction],
    ) -> None:
        """Persist structured extraction results for parsed documents."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                for document_extraction in extractions:
                    self._save_extraction_row(
                        process_id,
                        document_extraction.document_id,
                        document_extraction.extraction,
                    )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save extractions for {process_id}: {exc}") from exc

    def save_extraction(
        self,
        process_id: str,
        document_id: str,
        extraction: ContractExtractionResult,
    ) -> None:
        """Persist one structured extraction result."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                self._save_extraction_row(process_id, document_id, extraction)
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save extraction for {process_id}: {exc}") from exc

    def save_retrieved_contexts(
        self,
        process_id: str,
        document_id: str,
        contexts: Sequence[RetrievedContextChunk],
    ) -> None:
        """Persist retrieved policy context references and bounded excerpts."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                self.connection.execute(
                    "DELETE FROM retrieved_contexts WHERE process_id = ? AND document_id = ?",
                    (process_id, document_id),
                )
                self.connection.executemany(
                    """
                    INSERT INTO retrieved_contexts (
                        process_id, document_id, chunk_id, source, doc_type,
                        clause_type, score, content_excerpt
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            process_id,
                            document_id,
                            context.chunk_id,
                            context.source,
                            context.doc_type,
                            context.clause_type,
                            context.score,
                            _excerpt(context.content),
                        )
                        for context in contexts
                    ],
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save retrieved contexts for {process_id}: {exc}") from exc

    def save_classification(
        self,
        process_id: str,
        classification: ClassificationResult,
    ) -> None:
        """Persist the model risk classification."""
        self.create_processing_run(process_id)
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO classifications (
                        process_id, risk_level, policy_conflicts, recommended_action,
                        rationale, final_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(process_id) DO UPDATE SET
                        risk_level = excluded.risk_level,
                        policy_conflicts = excluded.policy_conflicts,
                        recommended_action = excluded.recommended_action,
                        rationale = excluded.rationale,
                        final_confidence = excluded.final_confidence
                    """,
                    (
                        process_id,
                        classification.risk_level.value,
                        _json_dump(classification.policy_conflicts),
                        classification.recommended_action.value,
                        classification.rationale,
                        classification.final_confidence,
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not save classification for {process_id}: {exc}") from exc

    def save_document_evaluation(self, evaluation: DocumentEvaluation) -> None:
        """Persist one per-document evaluation and its supporting artifacts."""
        self.create_processing_run(evaluation.process_id)
        try:
            with self.connection:
                self._save_extraction_row(
                    evaluation.process_id,
                    evaluation.document_id,
                    evaluation.extraction,
                )
                self.connection.execute(
                    "DELETE FROM retrieved_contexts WHERE process_id = ? AND document_id = ?",
                    (evaluation.process_id, evaluation.document_id),
                )
                self.connection.executemany(
                    """
                    INSERT INTO retrieved_contexts (
                        process_id, document_id, chunk_id, source, doc_type,
                        clause_type, score, content_excerpt
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            evaluation.process_id,
                            evaluation.document_id,
                            context.chunk_id,
                            context.source,
                            context.doc_type,
                            context.clause_type,
                            context.score,
                            _excerpt(context.content),
                        )
                        for context in evaluation.retrieved_contexts
                    ],
                )
                classification = evaluation.classification
                self.connection.execute(
                    """
                    INSERT INTO document_evaluations (
                        process_id, document_id, status, final_action, review_required,
                        decision_reason, errors, risk_level, policy_conflicts,
                        recommended_action, rationale, final_confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(process_id, document_id) DO UPDATE SET
                        status = excluded.status,
                        final_action = excluded.final_action,
                        review_required = excluded.review_required,
                        decision_reason = excluded.decision_reason,
                        errors = excluded.errors,
                        risk_level = excluded.risk_level,
                        policy_conflicts = excluded.policy_conflicts,
                        recommended_action = excluded.recommended_action,
                        rationale = excluded.rationale,
                        final_confidence = excluded.final_confidence
                    """,
                    (
                        evaluation.process_id,
                        evaluation.document_id,
                        evaluation.status.value,
                        _enum_value(evaluation.final_action),
                        int(evaluation.review_required),
                        evaluation.decision_reason,
                        _json_dump(evaluation.errors),
                        classification.risk_level.value if classification is not None else None,
                        _json_dump(
                            classification.policy_conflicts
                            if classification is not None
                            else []
                        ),
                        (
                            classification.recommended_action.value
                            if classification is not None
                            else None
                        ),
                        classification.rationale if classification is not None else None,
                        classification.final_confidence if classification is not None else None,
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Could not save document evaluation for {evaluation.process_id}/{evaluation.document_id}: {exc}"
            ) from exc

    def save_document_evaluations(self, evaluations: Sequence[DocumentEvaluation]) -> None:
        """Persist per-document evaluations."""
        for evaluation in evaluations:
            self.save_document_evaluation(evaluation)

    def save_outcome(self, outcome: ProcessingOutcome) -> None:
        """Persist final deterministic routing fields."""
        current_stage = (
            None
            if outcome.status == ProcessingStatus.FAILED
            else ProcessingStage.PERSISTENCE_COMPLETED.value
        )
        self.update_processing_run(
            outcome.process_id,
            status=outcome.status.value,
            current_stage=current_stage,
            final_action=outcome.final_action,
            review_required=outcome.review_required,
            decision_reason=outcome.decision_reason,
            error_message="; ".join(outcome.errors) if outcome.errors else None,
        )
        if outcome.classification is not None:
            self.save_classification(outcome.process_id, outcome.classification)

    def create_review_queue_item(
        self,
        process_id: str,
        *,
        review_type: RoutingAction | str,
        reason: str,
        status: ReviewQueueStatus | str = ReviewQueueStatus.OPEN,
    ) -> ReviewQueueItem:
        """Create or update the open review queue item for a process."""
        self.create_processing_run(process_id)
        now = _utc_now()
        status_value = _enum_value(status)
        review_type_value = _enum_value(review_type)
        try:
            with self.connection:
                existing = self.connection.execute(
                    """
                    SELECT id
                    FROM review_queue
                    WHERE process_id = ? AND status = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (process_id, status_value),
                ).fetchone()
                if existing is None:
                    cursor = self.connection.execute(
                        """
                        INSERT INTO review_queue (
                            process_id, review_type, reason, status, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (process_id, review_type_value, reason, status_value, now, now),
                    )
                    review_id = int(cursor.lastrowid)
                else:
                    review_id = int(existing["id"])
                    self.connection.execute(
                        """
                        UPDATE review_queue
                        SET review_type = ?, reason = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (review_type_value, reason, now, review_id),
                    )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not create review queue item for {process_id}: {exc}") from exc

        item = self.connection.execute(
            "SELECT * FROM review_queue WHERE id = ?",
            (review_id,),
        ).fetchone()
        if item is None:
            raise PersistenceError(f"Review queue item disappeared after insert: {review_id}.")
        return _review_item_from_row(item)

    def get_process(self, process_id: str) -> ProcessRecord | None:
        """Return persisted processing status and traceability artifacts."""
        try:
            run = self.connection.execute(
                "SELECT * FROM processing_runs WHERE process_id = ?",
                (process_id,),
            ).fetchone()
            if run is None:
                return None

            email_row = self.connection.execute(
                "SELECT * FROM emails WHERE process_id = ?",
                (process_id,),
            ).fetchone()
            attachment_rows = self.connection.execute(
                "SELECT * FROM attachments WHERE process_id = ? ORDER BY id",
                (process_id,),
            ).fetchall()
            document_rows = self.connection.execute(
                "SELECT * FROM parsed_documents WHERE process_id = ? ORDER BY document_id",
                (process_id,),
            ).fetchall()
            extraction_rows = self.connection.execute(
                "SELECT * FROM extracted_contracts WHERE process_id = ? ORDER BY document_id",
                (process_id,),
            ).fetchall()
            context_rows = self.connection.execute(
                "SELECT * FROM retrieved_contexts WHERE process_id = ? ORDER BY score DESC, id",
                (process_id,),
            ).fetchall()
            classification_row = self.connection.execute(
                "SELECT * FROM classifications WHERE process_id = ?",
                (process_id,),
            ).fetchone()
            evaluation_rows = self.connection.execute(
                "SELECT * FROM document_evaluations WHERE process_id = ? ORDER BY document_id",
                (process_id,),
            ).fetchall()
            review_rows = self.connection.execute(
                "SELECT * FROM review_queue WHERE process_id = ? ORDER BY id",
                (process_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not fetch process {process_id}: {exc}") from exc

        attachment_order_by_filename = {
            row["filename"]: index
            for index, row in enumerate(attachment_rows)
        }
        documents = sorted(
            [_document_from_row(row) for row in document_rows],
            key=lambda document: (
                attachment_order_by_filename.get(document.filename, len(attachment_order_by_filename)),
                document.document_id,
            ),
        )
        filenames_by_document = {document.document_id: document.filename for document in documents}
        extraction_rows = sorted(
            extraction_rows,
            key=lambda row: (
                attachment_order_by_filename.get(
                    filenames_by_document.get(row["document_id"], ""),
                    len(attachment_order_by_filename),
                ),
                row["document_id"],
            ),
        )
        evaluation_rows = sorted(
            evaluation_rows,
            key=lambda row: (
                attachment_order_by_filename.get(
                    filenames_by_document.get(row["document_id"], ""),
                    len(attachment_order_by_filename),
                ),
                row["document_id"],
            ),
        )
        extractions_by_document = {
            row["document_id"]: _extraction_from_row(row)
            for row in extraction_rows
        }
        contexts_by_document: dict[str, list[RetrievedContextChunk]] = {}
        for row in context_rows:
            contexts_by_document.setdefault(row["document_id"], []).append(_context_from_row(row))
        return ProcessRecord(
            process_id=process_id,
            status=run["status"],
            current_stage=run["current_stage"],
            created_at=_parse_datetime(run["created_at"]),
            updated_at=_parse_datetime(run["updated_at"]),
            error_type=run["error_type"],
            error_message=run["error_message"],
            final_action=run["final_action"],
            review_required=bool(run["review_required"]),
            decision_reason=run["decision_reason"],
            email=_email_from_row(email_row) if email_row is not None else None,
            attachments=[_attachment_from_row(row) for row in attachment_rows],
            documents=documents,
            extractions=[
                _document_extraction_from_row(row, filenames_by_document)
                for row in extraction_rows
            ],
            retrieved_contexts=[_context_from_row(row) for row in context_rows],
            classification=(
                _classification_from_row(classification_row)
                if classification_row is not None
                else None
            ),
            document_evaluations=[
                _document_evaluation_from_row(
                    row,
                    filenames_by_document,
                    extractions_by_document,
                    contexts_by_document,
                )
                for row in evaluation_rows
                if row["document_id"] in extractions_by_document
            ],
            review_queue=[_review_item_from_row(row) for row in review_rows],
        )

    def list_review_queue(
        self,
        *,
        status: ReviewQueueStatus | str | None = ReviewQueueStatus.OPEN,
    ) -> list[ReviewQueueItem]:
        """List review queue entries, optionally filtered by status."""
        try:
            if status is None:
                rows = self.connection.execute(
                    """
                    SELECT review_queue.*, classifications.risk_level
                    FROM review_queue
                    LEFT JOIN classifications
                        ON classifications.process_id = review_queue.process_id
                    ORDER BY review_queue.created_at DESC, review_queue.id DESC
                    """
                ).fetchall()
            else:
                rows = self.connection.execute(
                    """
                    SELECT review_queue.*, classifications.risk_level
                    FROM review_queue
                    LEFT JOIN classifications
                        ON classifications.process_id = review_queue.process_id
                    WHERE status = ?
                    ORDER BY review_queue.created_at DESC, review_queue.id DESC
                    """,
                    (_enum_value(status),),
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not fetch review queue: {exc}") from exc
        return [_review_item_from_row(row) for row in rows]

    def _save_extraction_row(
        self,
        process_id: str,
        document_id: str,
        extraction: ContractExtractionResult,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO extracted_contracts (
                process_id, document_id, vendor_name, contract_type, payment_terms,
                liability_clause, termination_clause, renewal_clause, governing_law,
                data_usage_clause, key_missing_fields, extraction_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(process_id, document_id) DO UPDATE SET
                vendor_name = excluded.vendor_name,
                contract_type = excluded.contract_type,
                payment_terms = excluded.payment_terms,
                liability_clause = excluded.liability_clause,
                termination_clause = excluded.termination_clause,
                renewal_clause = excluded.renewal_clause,
                governing_law = excluded.governing_law,
                data_usage_clause = excluded.data_usage_clause,
                key_missing_fields = excluded.key_missing_fields,
                extraction_confidence = excluded.extraction_confidence
            """,
            (
                process_id,
                document_id,
                extraction.vendor_name,
                extraction.contract_type,
                extraction.payment_terms,
                extraction.liability_clause,
                extraction.termination_clause,
                extraction.renewal_clause,
                extraction.governing_law,
                extraction.data_usage_clause,
                _json_dump(extraction.key_missing_fields),
                extraction.extraction_confidence,
            ),
        )


SQLiteProcessRepository = PersistenceRepository


def _email_from_row(row: sqlite3.Row) -> InboundEmail:
    return InboundEmail(
        message_id=row["message_id"],
        sender=row["sender"],
        recipient=row["recipient"],
        subject=row["subject"],
        plain_text_body=row["plain_text_body"],
        attachment_count=row["attachment_count"],
        received_at=_parse_datetime(row["received_at"]),
    )


def _attachment_from_row(row: sqlite3.Row) -> AttachmentMetadata:
    return AttachmentMetadata(
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        storage_path=row["storage_path"],
    )


def _document_from_row(row: sqlite3.Row) -> ParsedDocument:
    return ParsedDocument(
        document_id=row["document_id"],
        filename=row["filename"],
        file_type=row["file_type"],
        parser_name=row["parser_name"],
        raw_text=row["raw_text"],
        extracted_tables=_json_load(row["extracted_tables"]),
        parse_warnings=_json_load(row["parse_warnings"]),
        confidence_hint=row["confidence_hint"],
    )


def _document_extraction_from_row(
    row: sqlite3.Row,
    filenames_by_document: dict[str, str],
) -> DocumentExtraction:
    document_id = row["document_id"]
    return DocumentExtraction(
        document_id=document_id,
        filename=filenames_by_document.get(document_id, ""),
        extraction=_extraction_from_row(row),
    )


def _extraction_from_row(row: sqlite3.Row) -> ContractExtractionResult:
    return ContractExtractionResult(
        vendor_name=row["vendor_name"],
        contract_type=row["contract_type"],
        payment_terms=row["payment_terms"],
        liability_clause=row["liability_clause"],
        termination_clause=row["termination_clause"],
        renewal_clause=row["renewal_clause"],
        governing_law=row["governing_law"],
        data_usage_clause=row["data_usage_clause"],
        key_missing_fields=_json_load(row["key_missing_fields"]),
        extraction_confidence=row["extraction_confidence"],
    )


def _context_from_row(row: sqlite3.Row) -> RetrievedContextChunk:
    return RetrievedContextChunk(
        chunk_id=row["chunk_id"],
        source=row["source"],
        doc_type=row["doc_type"],
        clause_type=row["clause_type"],
        content=row["content_excerpt"] or "",
        score=row["score"],
    )


def _classification_from_row(row: sqlite3.Row) -> ClassificationResult:
    return ClassificationResult(
        risk_level=row["risk_level"],
        policy_conflicts=_json_load(row["policy_conflicts"]),
        recommended_action=row["recommended_action"],
        rationale=row["rationale"],
        final_confidence=row["final_confidence"],
    )


def _document_evaluation_from_row(
    row: sqlite3.Row,
    filenames_by_document: dict[str, str],
    extractions_by_document: dict[str, ContractExtractionResult],
    contexts_by_document: dict[str, list[RetrievedContextChunk]],
) -> DocumentEvaluation:
    document_id = row["document_id"]
    classification = None
    if row["risk_level"] is not None:
        classification = ClassificationResult(
            risk_level=row["risk_level"],
            policy_conflicts=_json_load(row["policy_conflicts"]),
            recommended_action=row["recommended_action"],
            rationale=row["rationale"],
            final_confidence=row["final_confidence"],
        )
    return DocumentEvaluation(
        process_id=row["process_id"],
        document_id=document_id,
        filename=filenames_by_document.get(document_id, ""),
        extraction=extractions_by_document[document_id],
        retrieved_contexts=contexts_by_document.get(document_id, []),
        classification=classification,
        status=row["status"],
        review_required=bool(row["review_required"]),
        final_action=row["final_action"],
        decision_reason=row["decision_reason"],
        errors=_json_load(row["errors"]),
    )


def _review_item_from_row(row: sqlite3.Row) -> ReviewQueueItem:
    return ReviewQueueItem(
        id=row["id"],
        process_id=row["process_id"],
        review_type=row["review_type"],
        reason=row["reason"],
        risk_level=row["risk_level"] if _has_column(row, "risk_level") else None,
        status=row["status"],
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def _json_load(value: str | None) -> Any:
    if not value:
        return []
    return json.loads(value)


def _excerpt(value: str, limit: int = 1200) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _has_column(row: sqlite3.Row, name: str) -> bool:
    return name in row.keys()

"""Export / Import endpoints for device-to-device data transfer."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.schemas.transfer import DataExportBundle, ExportMetadata, ImportResult
from backend.app.services import transfer as transfer_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/transfer",
    tags=["transfer"],
)


@router.get(
    "/export",
    response_model=DataExportBundle,
    summary="Export all application data",
    description=(
        "Downloads a JSON bundle containing every table's data. "
        "Use this to move your DevLog+ data to another machine. "
        "Embeddings and processing logs are excluded — they will be "
        "regenerated automatically on the new machine."
    ),
)
async def export_data(db: AsyncSession = Depends(get_db)) -> DataExportBundle:
    bundle = await transfer_service.export_all(db)
    return bundle


@router.post(
    "/import",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
    summary="Import application data from an export bundle",
    description=(
        "Upload a JSON export file produced by the /export endpoint. "
        "**This is destructive** — all existing data will be replaced "
        "with the contents of the uploaded file. Intended for migrating "
        "your DevLog+ instance to a new machine."
    ),
)
async def import_data(
    file: UploadFile,
    confirm_overwrite: bool = Query(
        False,
        description=(
            "Must be true when importing into a database that already "
            "contains data. Prevents accidental overwrites."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    # Validate content type (be lenient — allow application/json and application/octet-stream)
    if file.content_type and file.content_type not in (
        "application/json",
        "application/octet-stream",
        "text/plain",
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected a JSON file, got {file.content_type}",
        )

    body = await file.read()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        bundle = DataExportBundle.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid export bundle: {exc.error_count()} validation error(s). "
            f"First error: {exc.errors()[0]['msg']}",
        ) from exc

    if bundle.format_version != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported format_version {bundle.format_version}. This server supports version 1.",  # noqa: E501
        )

    try:
        result = await transfer_service.import_all(db, bundle, confirm_overwrite=confirm_overwrite)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return result


@router.get(
    "/export/metadata",
    response_model=ExportMetadata,
    summary="Preview export metadata without downloading the full bundle",
    description=(
        "Returns table row counts and metadata so you can verify "
        "what will be exported before triggering the full download."
    ),
)
async def export_metadata(db: AsyncSession = Depends(get_db)) -> ExportMetadata:
    bundle = await transfer_service.export_all(db)
    table_counts = {
        "journal_entries": len(bundle.journal_entries),
        "journal_entry_versions": len(bundle.journal_entry_versions),
        "topics": len(bundle.topics),
        "topic_relationships": len(bundle.topic_relationships),
        "profile_snapshots": len(bundle.profile_snapshots),
        "quiz_sessions": len(bundle.quiz_sessions),
        "quiz_questions": len(bundle.quiz_questions),
        "quiz_answers": len(bundle.quiz_answers),
        "quiz_evaluations": len(bundle.quiz_evaluations),
        "reading_recommendations": len(bundle.reading_recommendations),
        "reading_allowlist": len(bundle.reading_allowlist),
        "weekly_projects": len(bundle.weekly_projects),
        "project_tasks": len(bundle.project_tasks),
        "project_evaluations": len(bundle.project_evaluations),
        "feedback": len(bundle.feedback),
        "triage_items": len(bundle.triage_items),
        "user_settings": len(bundle.user_settings),
        "onboarding_state": len(bundle.onboarding_state),
    }
    return ExportMetadata(
        format_version=bundle.format_version,
        exported_at=bundle.exported_at,
        app_version=bundle.app_version,
        table_counts=table_counts,
    )

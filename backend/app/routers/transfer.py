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
    from datetime import UTC, datetime

    table_counts = await transfer_service.count_tables(db)
    return ExportMetadata(
        format_version=1,
        exported_at=datetime.now(UTC),
        app_version=transfer_service.APP_VERSION,
        table_counts=table_counts,
    )

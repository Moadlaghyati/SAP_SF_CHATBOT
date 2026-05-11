from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.dependencies import get_container, get_demo_user_id
from app.schemas.api import UploadAttachmentResponse
from app.services.container import AppContainer

router = APIRouter(tags=["upload"])

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload-attachment", response_model=UploadAttachmentResponse)
async def upload_attachment(
    file: UploadFile,
    container: AppContainer = Depends(get_container),
    demo_user_id: str = Depends(get_demo_user_id),
) -> UploadAttachmentResponse:
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit.")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    record_key = f"CHAT_{uuid.uuid4().hex[:16].upper()}"
    file_name = file.filename or "attachment"

    # Store pending upload in container's temp store — the record_key is later used
    # as the EmployeeTime externalCode so SAP can link attachment → time-off record.
    container.pending_attachments[record_key] = {
        "file_bytes": file_bytes,
        "file_name": file_name,
        "mime_type": file.content_type or "application/octet-stream",
        "demo_user_id": demo_user_id,
    }

    return UploadAttachmentResponse(
        record_key=record_key,
        file_name=file_name,
        file_size=len(file_bytes),
    )

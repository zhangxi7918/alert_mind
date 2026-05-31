from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.response import UploadResponse
from app.services.document_splitter_service import document_splitter_service
from app.services.vector_index_service import vector_index_service

UPLOAD_DIR = Path("uploads")

router = APIRouter()


@router.post("/files/upload", response_model=UploadResponse)
async def upload_file(file: Annotated[UploadFile, File(...)]) -> UploadResponse:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="上传文件名不能为空")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / filename

    async with aiofiles.open(file_path, "wb") as output_file:
        while chunk := await file.read(1024 * 1024):
            await output_file.write(chunk)

    async with aiofiles.open(file_path, encoding="utf-8") as input_file:
        content = await input_file.read()

    chunks = document_splitter_service.split_document(content, str(file_path))
    chunks_count = vector_index_service.index_documents(chunks)

    return UploadResponse(
        filename=filename,
        chunks_count=chunks_count,
        status="success",
    )

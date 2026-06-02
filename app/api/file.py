from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.response import UploadResponse
from app.services.document_splitter_service import document_splitter_service
from app.services.vector_index_service import vector_index_service

UPLOAD_DIR = Path("uploads")
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".markdown"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

router = APIRouter()


@router.post("/files/upload", response_model=UploadResponse)
async def upload_file(file: Annotated[UploadFile, File(...)]) -> UploadResponse:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="上传文件名不能为空")

    if Path(filename).suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="只支持上传 TXT 或 Markdown 文件")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / filename

    uploaded_size = 0
    async with aiofiles.open(file_path, "wb") as output_file:
        while chunk := await file.read(1024 * 1024):
            uploaded_size += len(chunk)
            if uploaded_size > MAX_UPLOAD_BYTES:
                file_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="文件大小不能超过50MB")

            await output_file.write(chunk)

    try:
        async with aiofiles.open(file_path, encoding="utf-8") as input_file:
            content = await input_file.read()
    except UnicodeDecodeError as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件必须使用 UTF-8 编码") from exc

    if not content.strip():
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件内容不能为空")

    chunks = document_splitter_service.split_document(content, str(file_path))
    if not chunks:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件内容无法切分出有效 chunk")

    index_result = vector_index_service.index_documents(chunks)

    return UploadResponse(
        filename=filename,
        chunks_count=index_result.chunks_count,
        inserted_count=index_result.inserted_count,
        skipped_count=index_result.skipped_count,
        status="success",
    )

from typing import Literal

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Response payload returned after a file upload is processed."""

    filename: str = Field(description="上传的文件名")
    chunks_count: int = Field(description="切分出的 chunk 数量")
    status: Literal["success", "error"] = Field(description="上传处理状态")
    message: str | None = Field(default=None, description="可选的描述信息")

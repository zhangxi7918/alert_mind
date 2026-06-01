from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for a chat query."""

    question: str = Field(description="用户问题")
    session_id: str = Field(description="会话 ID")

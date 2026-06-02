from langgraph.config import get_stream_writer


def emit_status(message: str) -> None:
    """在 LangGraph custom stream 中输出 AIOps 阶段状态。"""
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return

    writer({"type": "status", "message": message})

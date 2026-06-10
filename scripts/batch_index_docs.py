"""批量将 uploads/ 目录下的文档入库到向量数据库。

已入库的文档通过 SHA-256 内容哈希自动去重，可安全重复执行。

用法：
    uv run python scripts/batch_index_docs.py
"""

from pathlib import Path

from loguru import logger

from app.services.document_splitter_service import document_splitter_service
from app.services.vector_index_service import vector_index_service

UPLOADS_DIR = Path("uploads")
SUPPORTED_SUFFIXES = {".md", ".txt", ".markdown"}


def index_file(file_path: Path) -> tuple[int, int]:
    """返回 (inserted, skipped) 数量。"""
    content = file_path.read_text(encoding="utf-8")
    chunks = document_splitter_service.split_document(content, str(file_path))
    if not chunks:
        logger.warning("无法切分，跳过：{}", file_path.name)
        return 0, 0
    result = vector_index_service.index_documents(chunks)
    return result.inserted_count, result.skipped_count


def main() -> None:
    files = sorted(
        f for f in UPLOADS_DIR.iterdir()
        if f.suffix.lower() in SUPPORTED_SUFFIXES and not f.name.startswith(".")
    )

    if not files:
        logger.error("uploads/ 目录下没有找到支持的文档")
        return

    logger.info("共找到 {} 个文档，开始入库...", len(files))

    total_inserted = total_skipped = 0
    for file_path in files:
        try:
            inserted, skipped = index_file(file_path)
            total_inserted += inserted
            total_skipped += skipped
            status = "新增" if inserted > 0 else "已存在"
            logger.info("[{}] {} — 新增 {} chunks，跳过 {} chunks",
                        status, file_path.name, inserted, skipped)
        except Exception as e:
            logger.error("入库失败：{} — {}", file_path.name, e)

    logger.info("完成。总计新增 {} chunks，跳过 {} chunks（已存在）",
                total_inserted, total_skipped)


if __name__ == "__main__":
    main()

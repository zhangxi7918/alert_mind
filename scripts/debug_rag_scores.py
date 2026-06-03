"""
调试 RAG 检索分数分布，帮助校准 rag_score_threshold。

用法：
    uv run python scripts/debug_rag_scores.py
    uv run python scripts/debug_rag_scores.py "CPU 占用高怎么处理"
"""

import sys
from pathlib import Path

# 将项目根目录加入 path，使 app.* 可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.milvus_client import milvus_manager
from app.services.vector_store_manager import vector_store_manager
from app.config import config

QUERIES = [
    "CPU 占用高怎么处理",
    "磁盘空间不足",
    "服务超时怎么排查",
    "今天天气怎么样",   # 故意放一个无关查询，score 应该很低
]


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else None
    queries = [query] if query else QUERIES

    milvus_manager.connect()
    vector_store_manager.initialize()

    print(f"\n当前阈值 rag_score_threshold = {config.rag_score_threshold}\n")
    print("=" * 60)

    for q in queries:
        print(f"\n查询：{q}")
        print("-" * 40)
        results = vector_store_manager._get_vector_store().similarity_search_with_relevance_scores(q, k=5)

        if not results:
            print("  (无结果)")
            continue

        for doc, score in results:
            source = doc.metadata.get("_file_name", "未知")
            content_preview = doc.page_content[:60].replace("\n", " ")
            passed = "✓" if score >= config.rag_score_threshold else "✗"
            print(f"  {passed} score={score:.4f}  [{source}]  {content_preview}...")

    milvus_manager.close()


if __name__ == "__main__":
    main()

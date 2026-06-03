"""
Rerank 前后检索结果对比。

用法：
    uv run python scripts/compare_rerank.py
    uv run python scripts/compare_rerank.py "数据库连接超时怎么处理"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import config
from app.core.milvus_client import milvus_manager
from app.services.rerank_service import rerank_service
from app.services.vector_store_manager import vector_store_manager

# 这些查询故意选会让 ANN 排序出现偏差的场景
QUERIES = [
    "数据库连接超时怎么处理",     # 预期：db_connection_pool，但 ANN 可能召回 service_timeout
    "容器 OOM 被杀掉如何排查",    # 预期：container_restart，但 ANN 可能召回 high_memory
    "磁盘写满导致服务中断复盘",    # 预期：postmortem_db_outage，但 ANN 可能召回 disk_space
    "告警阈值怎么配置合理",       # 预期：reference_alert_rules，但 ANN 可能召回多个 runbook
]

TOP_N_CANDIDATES = 10  # 粗召回数量
TOP_K = 3              # 最终取几条


def show_results(label: str, results: list) -> None:
    print(f"\n  [{label}]")
    for i, doc in enumerate(results, 1):
        source = doc.metadata.get("_file_name", "未知")
        preview = doc.page_content[:60].replace("\n", " ")
        print(f"  {i}. [{source}]  {preview}...")


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else None
    queries = [query] if query else QUERIES

    milvus_manager.connect()
    vector_store_manager.initialize()

    print(f"\n对比参数：粗召回 top-{TOP_N_CANDIDATES}，最终 top-{TOP_K}")
    print("=" * 70)

    for q in queries:
        print(f"\n查询：{q}")
        print("-" * 50)

        # ANN 直接取 top-k
        ann_results = vector_store_manager.similarity_search(q, k=TOP_K)
        show_results("ANN top-3（无 rerank）", ann_results)

        # 粗召回 + rerank
        candidates = vector_store_manager.similarity_search(q, k=TOP_N_CANDIDATES)
        reranked = rerank_service.rerank(q, candidates, top_n=TOP_K, model=config.rag_rerank_model)
        show_results(f"ANN top-{TOP_N_CANDIDATES} → Rerank top-3", reranked)

        # 标出差异
        ann_sources = [d.metadata.get("_file_name", "") for d in ann_results]
        rerank_sources = [d.metadata.get("_file_name", "") for d in reranked]
        changed = ann_sources != rerank_sources
        print(f"\n  {'⚡ 排序有变化' if changed else '— 排序无变化'}")

    milvus_manager.close()


if __name__ == "__main__":
    main()

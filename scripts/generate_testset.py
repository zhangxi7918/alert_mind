"""
使用 RAGAS TestsetGenerator 从知识库文档生成测试集。

输出到 eval/rag_generated.jsonl（待人工 review 后合并进 rag_golden.jsonl）。

用法：
    PYTHONPATH=. uv run python scripts/generate_testset.py [--size 50]
"""

import argparse
import json
import os
from pathlib import Path

from langchain_qwq import ChatQwen
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.testset import TestsetGenerator
from ragas.testset.synthesizers import (
    MultiHopAbstractQuerySynthesizer,
    MultiHopSpecificQuerySynthesizer,
    SingleHopSpecificQuerySynthesizer,
)

from app.config import config, get_dashscope_api_key
from app.services.document_splitter_service import document_splitter_service
from app.services.vector_embedding_service import DashScopeEmbeddings

UPLOADS_DIR = Path("uploads")
OUTPUT_FILE = Path("eval/rag_generated.jsonl")
SUPPORTED_SUFFIXES = {".md", ".txt", ".markdown"}

# 跳过无关文档（客服手册不属于 AIOps 运维知识库范畴）
SKIP_FILES = {"test.md", ".gitkeep", "# 云杉智能客服平台使用手册.md"}


def load_documents() -> list[Document]:
    """加载 uploads/ 下的文档，切分成 chunk 并携带 source 元数据。"""
    docs: list[Document] = []
    for file_path in sorted(UPLOADS_DIR.iterdir()):
        if file_path.name in SKIP_FILES:
            continue
        if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        content = file_path.read_text(encoding="utf-8")
        chunks = document_splitter_service.split_document(content, str(file_path))
        for chunk in chunks:
            # RAGAS 需要 source 在 metadata 里，用于追溯 expected_sources
            chunk.metadata["source"] = file_path.name
        docs.extend(chunks)
        logger.debug("加载 {} → {} chunks", file_path.name, len(chunks))
    logger.info("共加载 {} 个文档块，来自 {} 个文件", len(docs), len(set(d.metadata["source"] for d in docs)))
    return docs


def extract_sources(reference_contexts: list[str], all_docs: list[Document]) -> list[str]:
    """从 context 文本反查对应的源文件名（前缀匹配）。"""
    sources: set[str] = set()
    for ctx in reference_contexts:
        ctx_stripped = ctx.strip()[:200]  # 只比较前 200 字符，避免尾部差异
        for doc in all_docs:
            if doc.page_content.strip()[:200] == ctx_stripped:
                sources.add(doc.metadata["source"])
                break
    return sorted(sources)


def main(testset_size: int) -> None:
    api_key = get_dashscope_api_key()
    os.environ.setdefault("DASHSCOPE_API_KEY", api_key)

    logger.info("初始化 LLM 和 Embedding...")
    llm = LangchainLLMWrapper(
        ChatQwen(
            model=config.rag_model,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        DashScopeEmbeddings(api_key=api_key, model=config.dashscope_embedding_model)
    )

    docs = load_documents()

    # 三种题型分布：单跳具体 60%，多跳具体 20%，多跳抽象 20%
    query_distribution = [
        (SingleHopSpecificQuerySynthesizer(llm=llm), 0.6),
        (MultiHopSpecificQuerySynthesizer(llm=llm), 0.2),
        (MultiHopAbstractQuerySynthesizer(llm=llm), 0.2),
    ]

    logger.info("开始生成测试集，目标 {} 条...", testset_size)
    generator = TestsetGenerator(llm=llm, embedding_model=embeddings)
    dataset = generator.generate_with_langchain_docs(
        docs,
        testset_size=testset_size,
        query_distribution=query_distribution,
    )

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    written = 0
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for i, row in enumerate(dataset.to_pandas().itertuples()):
            query = getattr(row, "user_input", None)
            contexts = getattr(row, "reference_contexts", []) or []
            synth = getattr(row, "synthesizer_name", "unknown")
            if not query:
                continue

            sources = extract_sources(list(contexts), docs)
            is_multihop = "multi_hop" in synth
            entry = {
                "id": f"gen_{i+1:03d}",
                "query": query,
                # multi-hop 题的 sources 需人工标注，先置 null
                "expected_sources": sources if (sources or not is_multihop) else None,
                "category": f"generated_{synth}",
                "needs_review": is_multihop and not sources,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            written += 1

    logger.info("生成完成，共写入 {} 条到 {}", written, OUTPUT_FILE)
    logger.info("请人工 review 后，将有效条目合并到 eval/rag_golden.jsonl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=50, help="生成测试集大小")
    args = parser.parse_args()
    main(args.size)

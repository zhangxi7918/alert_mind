from typing import Literal

from loguru import logger

from app.agent.orchestrator.graph import orchestrator_graph


class OrchestratorService:
    async def classify(self, input_text: str) -> Literal["rag", "aiops"]:
        """对用户输入做意图分类，返回 'rag' 或 'aiops'。分类失败时降级到 rag。"""
        try:
            result = await orchestrator_graph.ainvoke({"input": input_text, "intent": None})
            intent = result["intent"]
            logger.info("意图分类：{!r} → {}", input_text[:50], intent)
            return intent
        except Exception as exc:
            logger.warning("意图分类失败，降级到 rag：{}", exc)
            return "rag"


orchestrator_service = OrchestratorService()

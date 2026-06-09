from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.utils.logger import setup_logger
from app.api import aiops
from app.api import chat
from app.api import file
from app.api import health
from app.api import unified
from app.config import config
from app.services.rag_agent_service import rag_agent_service
from app.services.rag_stream_run_service import rag_stream_run_service
from app.services.vector_store_manager import vector_store_manager

NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers.update(NO_CACHE_HEADERS)

        return response


setup_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("服务启动中...")
    await rag_agent_service.initialize_checkpointer()
    await rag_stream_run_service.initialize()
    try:
        vector_store_manager.initialize()
        yield
    finally:
        vector_store_manager.close()
        await rag_stream_run_service.close()
        await rag_agent_service.close()


app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        "{} {} {} {:.0f}ms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

app.include_router(health.router)
app.include_router(chat.router, prefix="/api", tags=["智能问答"])
app.include_router(unified.router, prefix="/api", tags=["Unified"])
app.include_router(file.router, prefix="/api", tags=["文件管理"])
app.include_router(aiops.router, prefix="/api", tags=["AIOps"])


# 挂载静态文件
static_dir = "static"
app.mount("/static", NoCacheStaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    """返回首页"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers=NO_CACHE_HEADERS)
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs"
    }

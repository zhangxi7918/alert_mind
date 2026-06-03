import sys
from loguru import logger


def setup_logger(log_dir: str = "logs") -> None:
    """配置 loguru：保留控制台输出，新增文件输出（按天轮转，保留 7 天）。"""
    # 移除默认 stderr sink，统一格式后重新添加
    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 控制台
    logger.add(sys.stderr, format=fmt, level="INFO", colorize=True)

    # 文件：按天轮转，保留 7 天，UTF-8 防乱码
    logger.add(
        f"{log_dir}/alert_mind_{{time:YYYY-MM-DD}}.log",
        format=fmt,
        level="DEBUG",
        rotation="00:00",   # 每天午夜切割
        retention="7 days",
        encoding="utf-8",
        colorize=False,
    )

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG UV_DEFAULT_INDEX=https://pypi.org/simple
ENV UV_DEFAULT_INDEX=${UV_DEFAULT_INDEX}

RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY mcp_servers ./mcp_servers
COPY static ./static

RUN mkdir -p uploads logs

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]

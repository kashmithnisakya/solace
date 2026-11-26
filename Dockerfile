FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY solace ./solace
RUN useradd -m solace && mkdir -p data && chown solace data
USER solace
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uv", "run", "--no-dev", "uvicorn", "solace.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

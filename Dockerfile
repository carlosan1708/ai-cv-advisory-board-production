FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["sh", "-c", "uvicorn src.advisory.web:app --host 0.0.0.0 --port ${PORT}"]


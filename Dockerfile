FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt* pyproject.toml* ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] jinja2 aiosqlite sse-starlette python-multipart boto3 cryptography

# Copy application code
COPY core/ core/
COPY web/ web/
COPY migrations/ migrations/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]

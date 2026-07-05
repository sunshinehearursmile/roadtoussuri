# Road to Ussuri — container image (serves the browser UI + MCP tools).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/tmp/road_to_ussuri.db

WORKDIR /app

# runtime deps only (no google-adk / pytest — ADK is optional, engine runs without it)
RUN pip install \
    "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "pyyaml>=6.0" "groq>=0.5.0" \
    "click>=8.0" "rich>=13.0" "httpx>=0.27.0" "python-dotenv>=1.0.0" "jinja2>=3.1.0"

# app source — run from the tree so config/ resolves via PROJECT_ROOT=/app
COPY mcp_server/ ./mcp_server/
COPY agents/ ./agents/
COPY cli/ ./cli/
COPY web/ ./web/
COPY config/ ./config/

# Cloud Run injects $PORT; web.serve honours it (defaults to 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "web.serve"]

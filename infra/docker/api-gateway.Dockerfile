FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
COPY services/api-gateway/ /app/services/api-gateway/
COPY services/mcp-host/ /app/services/mcp-host/
COPY services/knowledge-service/ /app/services/knowledge-service/
COPY services/orchestrator/ /app/services/orchestrator/
COPY services/model-serving/ /app/services/model-serving/
ENV PYTHONPATH="/app/services/api-gateway:/app/services/mcp-host:/app/services/knowledge-service:/app/services/orchestrator:/app/services/model-serving"
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

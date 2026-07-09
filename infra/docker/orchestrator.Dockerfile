FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
COPY services/orchestrator/ /app/services/orchestrator/

ENV PYTHONPATH="/app/services/orchestrator"
EXPOSE 8002
CMD ["uvicorn", "daypilot_orchestrator.agent_runtime:app", "--host", "0.0.0.0", "--port", "8002"]

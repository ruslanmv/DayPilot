FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
COPY services/knowledge-service/ /app/services/knowledge-service/
COPY alembic.ini ./
COPY alembic/ /app/alembic/
ENV PYTHONPATH="/app/services/knowledge-service"
EXPOSE 8004
CMD ["uvicorn", "daypilot_knowledge.pipeline:app", "--host", "0.0.0.0", "--port", "8004"]

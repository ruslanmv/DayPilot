FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
COPY services/mcp-host/ /app/services/mcp-host/

ENV PYTHONPATH="/app/services/mcp-host"
EXPOSE 8003
CMD ["uvicorn", "daypilot_mcp_host.server:app", "--host", "0.0.0.0", "--port", "8003"]

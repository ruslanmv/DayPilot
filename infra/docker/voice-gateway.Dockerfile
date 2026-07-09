FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
COPY services/voice-gateway/ /app/services/voice-gateway/

ENV PYTHONPATH="/app/services/voice-gateway"
EXPOSE 8006
CMD ["uvicorn", "daypilot_voice.pipeline:app", "--host", "0.0.0.0", "--port", "8006"]

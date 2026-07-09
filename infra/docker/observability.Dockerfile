FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt
COPY services/observability/ /app/services/observability/

ENV PYTHONPATH="/app/services/observability"
EXPOSE 8010
CMD ["uvicorn", "daypilot_observability.traces:app", "--host", "0.0.0.0", "--port", "8010"]

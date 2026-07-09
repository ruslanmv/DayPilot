# Docker Images

Each DayPilot Python microservice has a dedicated Dockerfile:

- `api-gateway.Dockerfile` -> port 8080
- `orchestrator.Dockerfile` -> port 8002
- `mcp-host.Dockerfile` -> port 8003
- `knowledge-service.Dockerfile` -> port 8004
- `model-serving.Dockerfile` -> port 8005
- `voice-gateway.Dockerfile` -> port 8006
- `observability.Dockerfile` -> port 8010

Build all services with:

```bash
docker compose up --build
```

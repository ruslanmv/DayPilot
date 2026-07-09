# DayPilot Operationalization Gap Analysis

This file captures the production-readiness gaps found after reviewing the initial `daypilot-enterprise` scaffold and records the concrete files added in the v0.2 operationalization pass.

## 1. Infrastructure was documentation-only

Resolved by adding:

- `infra/docker/*.Dockerfile` for every Python microservice.
- `docker-compose.yml` with API gateway, orchestrator, MCP host, knowledge-service, model-serving, voice-gateway, observability, Postgres, Redis, Qdrant, and Prometheus profiles.
- `infra/kubernetes/*.yaml` Kustomize-compatible manifests for all services and core dependencies.
- `infra/terraform/*.tf` AWS bootstrap resources: ECR repositories, VPC, private subnets, service security group, CloudWatch log groups, and ECS cluster.

## 2. Microservices were shallow stubs

Resolved by adding concrete FastAPI surfaces and foundational runtime logic:

- `orchestrator/daypilot_orchestrator/agent_runtime.py`: approval-first run planner, state machine, REST API, Prometheus metrics.
- `knowledge-service/daypilot_knowledge/pipeline.py`: document ingest, SQLite/Postgres-backed chunk persistence, search API, metrics.
- `model-serving/daypilot_models/connectors.py`: mock, Ollama, and OpenAI-compatible/vLLM connectors.
- `voice-gateway/daypilot_voice/pipeline.py`: mock ASR/TTS contracts, voice-stage description, REST API, metrics.
- `observability/daypilot_observability/*`: JSON logging, trace buffer, metrics collectors.
- `mcp-host/daypilot_mcp_host/server.py`: MCP tool inventory and HomePilot `.hpersona` preview endpoint.

## 3. Persistence lacked schema governance

Resolved by adding:

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/0001_initial_core_schema.py`
- `services/knowledge-service/daypilot_knowledge/db/` with SQLAlchemy models and session handling.
- `scripts/init_db.py`

Core tables now include users, personas, calendar accounts, inbox accounts, documents, document chunks, and audit logs.

## 4. UI bridge lacked atomic components

Resolved by adding a shared React design system foundation:

- `Button.tsx`
- `Card.tsx`
- `DashboardLayout.tsx`
- `StatusPill.tsx`
- `TerminalWindow.tsx`
- `ApprovalQueue.tsx`

The `SpaceBridgeShell` now composes these shared components, making the web, PWA, and Tauri shells immediately reusable.

## 5. Testing was under-represented

Resolved by adding tests for the orchestrator state machine, knowledge persistence, model router, voice pipeline, observability tracing, and API gateway health behavior.

This remains a scaffold, but it is no longer documentation-only: every service has a container target, a health endpoint, a metrics endpoint, and at least one executable behavior.

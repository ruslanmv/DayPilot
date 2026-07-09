# Architecture

DayPilot separates experience, control, execution, intelligence, local data, and observability.

```text
Operator UI → API Gateway → Orchestrator → MCP Host → Tools / Knowledge / Models
                              ↓
                         Approval Queue
                              ↓
                         Observability
```

The HomePilot bridge lives inside the MCP host because `.hpersona` import is treated as a governed tool operation.

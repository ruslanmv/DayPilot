# HomePilot Integration

DayPilot integrates HomePilot through portable `.hpersona` packages.

## Import Flow

1. User selects `.hpersona`.
2. DayPilot validates ZIP structure.
3. DayPilot reads `manifest.json`.
4. DayPilot reads `blueprint/persona_agent.json`.
5. DayPilot reads dependency manifests.
6. DayPilot creates a local persona record.
7. DayPilot creates a restrictive policy.
8. User reviews the policy.
9. Persona can be enabled for read-only or approval-gated work.

## Security Posture

- Imported personas are disabled by default.
- HomePilot tool names are mapped to DayPilot MCP namespaces.
- Write actions remain blocked until explicitly enabled.
- Dependencies are reported before installation.
- Package contents are never executed during preview.

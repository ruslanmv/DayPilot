# Security and Governance

DayPilot uses a policy-first design.

## Defaults

- Local-first storage.
- Dry-run MCP writes.
- Approval required for all mutating actions.
- Imported HomePilot personas are disabled by default.
- Tool scopes are explicit.
- Prompt injection controls are required before production.

## High-Risk Actions

- Sending external messages.
- Deleting or moving user data.
- Writing code or changing repositories.
- Creating calendar events.
- Calling external phone numbers.
- Reading sensitive local folders.

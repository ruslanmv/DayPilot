# HomePilot bridge — failure matrix (A11)

DayPilot degrades honestly: it never hides a problem, never fabricates a reply,
and never loses the user's words. Every failure has one defined behavior.

| Condition | What DayPilot does | Where |
| --- | --- | --- |
| **HomePilot offline** | Agents shown **offline**; the conversation is served from **local history** (`session.degraded=true`), and the workspace shows "showing your saved conversation". | `get_agent_session`, `AgentChatPanel` |
| **Persona removed in HomePilot** | The agent link is marked **offline**, never deleted — historical tasks + conversations survive. | `sync_agents` |
| **Persona not shared** (published) | Enabled but not chat-capable → status **offline/unavailable**; the card + workspace say so. | `_derive_status` |
| **Invalid / rejected key** | Connection status **unauthorized**; the settings panel asks the user to **reconnect**. | `_probe`, connection panel |
| **Chat timeout** | The user's message is **retained** (committed before the call); the endpoint returns **504** and the composer shows **Retry** (re-sends the same text). | `turn` → `code="timeout"`, `AgentChatPanel` |
| **Chat unreachable** | Same as timeout with **502**; message retained + **Retry**. | `turn` → `code="unreachable"` |
| **Invalid directive** | The plain-text reply is **kept**; the offending directive is **dropped** (re-validated defensively) — nothing partial is applied. | `directives.validate_directives` |
| **Avatar fetch fails** | The card / header fall back to the agent's **initials**. | `AgentCard`, `AgentWorkspaceHeader` |
| **Unsupported / legacy bridge** | Capability probe on connect sets `chatMode="chat_only"`; the persona still **replies**, but **no directives/tasks** are proposed. The UI says "chat-only". | `_store_chat_mode`, `AgentChatPanel`, connection panel |
| **Account mismatch** | A turn to an agent bound to a **different** HomePilot account is refused (409). | `turn` → `code="account_mismatch"` |
| **Chat feature off** | Session + turn endpoints **404**; the panel drops to a read-only notice. | `_require_chat` |

## Continuity (persistent remote session mapping)

- Each agent gets one durable `ChatSession` (`kind="agent"`, `agent_link_id`),
  carrying a **stable** `remote_session_id` sent to HomePilot as
  `X-HomePilot-Session-ID` on every turn — so the persona keeps its own thread
  across turns, refreshes, and devices.
- HomePilot's conversation id (from `x_homepilot.conversation_id`, else the
  response `id`) is captured **once** into `remote_conversation_id` and reused —
  DayPilot stores only the reference; HomePilot owns the conversation.
- A capability probe on connect records `chatMode` (`bridge` vs `chat_only`) so
  the UI states the mode up front instead of discovering it turn by turn.

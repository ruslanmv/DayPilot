# Setup, onboarding, and Ollabridge pairing

This guide covers getting a new user productive: the first-run wizard, creating
projects, pairing with Ollabridge (local **or** cloud), and the end-to-end week
simulation you can run to verify the whole loop.

---

## 1. First-run onboarding

On first launch DayPilot shows a **minimalist three-step wizard**. It captures
only the essentials and stores them in the local profile
(`localStorage['daypilot.profile']`); a completion flag
(`localStorage['daypilot.onboarded']`) stops it re-appearing.

| Step | What you provide | Why |
|---|---|---|
| **You** | Name + work email | Identity for the workspace and default mailbox. |
| **Mailbox** | Mailbox address | So the Email Sentinel can draft replies (it never sends without approval). |
| **Knowledge** | One local folder **or** Box location | A source the AI can read + index for RAG over your projects. |

**Skip for now** is always available. Everything advanced — IMAP/SMTP server
details, additional sources, provider keys — lives in **Settings**, not the
wizard. On phones the same wizard renders full-screen.

> Reset onboarding for a demo: clear `daypilot.onboarded` from local storage.

## 2. Create a project

A small, essentials-only **project wizard** captures name, goal, stack,
repository, and the first milestone. Open it from:

- the **⌘K** command palette → *New project*,
- the **Projects** view → *+ New project*, or
- the **mobile drawer** → *New project*.

Creating a project adds a live card and opens it. Deeper configuration happens
inside the project afterwards.

## 3. Profile essentials

**Settings → Profile & workspace** shows identity (name, email, role,
workspace, mode) and the *connected essentials* at a glance — mailbox, number of
granted knowledge sources, and the active AI provider. The settings panel has an
in-panel section rail so every section (Providers, Mail, Knowledge sources,
Permissions, …) is reachable from one entry point, including on phones.

---

## 4. Pair with Ollabridge — local or cloud

DayPilot talks to Ollabridge as a **consumer**: one OpenAI-compatible base URL
plus a Bearer key. The **local gateway** and **Ollabridge Cloud** expose the same
`/v1/models` and `/v1/chat/completions` contract, so pairing is identical — only
the endpoint and key format differ.

| | Local gateway | Ollabridge Cloud |
|---|---|---|
| Endpoint | `http://localhost:11435/v1` | `https://<your-node>.hf.space/v1` |
| Key | `sk-ollabridge-…` (printed at startup) | `ob_live_…` / `ob_test_…` (Bearer) |
| Pairing | none needed | API key **or** TV-style `ABCD-1234` device code |
| Nature | private-by-default, no telemetry | relay (zero port-forwarding), premium routing, federation |

### Configure

```bash
OLLABRIDGE_MODE=local                 # local | cloud — picks the default endpoint
OLLABRIDGE_URL=http://localhost:11435/v1                             # local gateway
OLLABRIDGE_CLOUD_URL=https://ruslanmv-ollabridge-cloud.hf.space/v1  # used when MODE=cloud
OLLABRIDGE_API_KEY=                    # sk-ollabridge-… (local) or ob_live_… (cloud)
OLLABRIDGE_DEFAULT_MODEL=llama3.1
```

`OLLABRIDGE_MODE` selects the default endpoint; an explicit `OLLABRIDGE_URL` /
`OLLABRIDGE_BASE_URL` always wins. Keys are sent as a Bearer token and are never
logged. In the UI, **Settings → AI providers** shows both modes side by side with
the active one highlighted, a *Test connection* action, and a *Pair with Cloud
(device code)* action.

### How it maps to code

`services/model-serving/daypilot_models/ollabridge_client.py`:

- `OllabridgeConnector(base_url, api_key, model, mode)` — `generate()`,
  `list_models()`, `ping()`.
- Cloud device pairing: `start_pairing()` (`POST /device/start`) and
  `poll_pairing(device_code)` (`POST /device/poll` → returns the minted key).
- `connector_from_env()` builds the connector for the selected mode.

### With a real local Ollama

```bash
# on a machine with network + GPU/CPU
ollama pull qwen2.5:0.5b          # any light model
# start the Ollabridge local gateway (see the ollabridge repo), then:
export DAYPILOT_MODEL_BACKEND=ollabridge
export OLLABRIDGE_MODE=local
export OLLABRIDGE_URL=http://localhost:11435/v1
```

DayPilot pairs with it unchanged — same connector, same `/v1` contract.

---

## 5. Verify end to end — the week simulation

`make sim` runs a real, reproducible **five-day week** for a principal AI/ML
engineer:

1. Starts a local OpenAI/Ollama-compatible **light-model server** (stand-in for
   `ollama` + a small model, since the CI sandbox blocks the public Ollama
   download) and pairs to it with the production `OllabridgeConnector` — `ping()`
   is a real HTTP handshake.
2. Seeds three projects with backlogs.
3. For **Mon–Fri**, makes real inferences for planning, a coding patch, an email
   draft, and a grounded RAG answer, and drives the day-plan lifecycle
   (`DRAFT → PROPOSED → APPROVED → ACTIVE → WRAPPED`) with wrap-up and
   continue-from-yesterday against a real SQLite database.

The governance contract holds across the week: **20 real inferences, 0 emails
sent, 0 unapproved writes, 5/5 approvals, 3 projects carried by continuity**. The
report is written to [`simulation/week_report.md`](simulation/week_report.md) and
metrics to `simulation/week_metrics.json`.

```bash
make sim
# or:  uv run python scripts/e2e_week_simulation.py
```

The fast CI check `tests/test_e2e_pairing_inference.py` locks the pairing +
inference path without downloading a model.

# Future: an Alexa skill and APL widget for DayPilot

**Status: plan only.** Nothing here is built or deployed. The web display (`/echo`, see
[README.md](README.md)) is the Echo Show integration that exists today; this is the separate,
native path for voice and for the Echo home screen, which a web page cannot reach.

## Why a separate integration

A page in Silk cannot use the wake word, cannot run in the background, cannot put anything on the
Echo's home screen and is closed whenever the device shows other content. Those are exactly what
the Alexa Skills Kit is for:

| Need | Web display (`/echo`) | Alexa skill |
|---|---|---|
| Touch dashboard, approvals with confirmation | ✓ | — |
| "Alexa, ask DayPilot what's next" | — | ✓ custom skill intents |
| A summary on the home screen without opening a browser | — | APL widget, where the device supports it |
| A spoken or on-screen notice when an approval arrives | — | Proactive Events (needs certification and user permission) |

## Scope of a first version (read-only)

Summaries only. **No decisions by voice** in v1: approvals gate sensitive actions, a voice "yes"
is easy to trigger by accident in a shared room, and the server's audit trail expects a signed-in
person. Approving stays in the DayPilot app or the `/echo` display.

Draft files in [`alexa/`](alexa/):

- [`interaction-model.en-US.json`](alexa/interaction-model.en-US.json) — invocation "day pilot";
  `TodaySummaryIntent`, `ApprovalsSummaryIntent`, `CalendarSummaryIntent`, `ProjectsAtRiskIntent`
  and the required built-in intents.
- [`today-summary.apl.json`](alexa/today-summary.apl.json) — an APL document for the Today summary
  on landscape Echo Show screens (no external packages; sizes scale with the viewport).
- [`summary.sample.json`](alexa/summary.sample.json) — the data the document binds to.

| Intent | Spoken answer (example) | Screen (APL) |
|---|---|---|
| TodaySummary | "Now: patch auth token refresh, until 12. Next: finish the Client Alpha release notes at 10." | Today summary |
| ApprovalsSummary | "Three approvals are waiting, one high risk. Open DayPilot to decide." | Today summary |
| CalendarSummary | "Next meeting: Client Alpha weekly sync at 11. It overlaps the release check-in." | Today summary |
| ProjectsAtRisk | "Client Alpha portal is high risk: the SSO certificate is blocked." | Today summary |

## What DayPilot needs first

1. **Account linking (OAuth 2.0 authorization-code grant).** Alexa calls the skill backend with an
   access token for the linked DayPilot user. DayPilot has cookie sessions only, so it needs an
   authorization endpoint, a token endpoint and scoped, revocable tokens (e.g. `summary:read`).
   This is the main prerequisite.
2. **A read-only summary endpoint**, proposed as `GET /v1/voice/summary`: greeting name, Now/Next,
   the four counts already computed by `/v1/today`, the next calendar event and the count and
   highest risk of pending approvals — titles only, no email bodies, document content or
   approval payloads. One request per utterance; the same numbers as the web display because it
   reads the same services.
3. **Server-side role checks on the token**, so a linked account can never do more than read the
   summary.

## Architecture

```
Echo Show ── voice / touch ──▶ Alexa service ──▶ skill backend (AWS Lambda or Alexa-hosted)
                                                     │  HTTPS + OAuth access token (account linking)
                                                     ▼
                                       DayPilot gateway  GET /v1/voice/summary  (read-only)
```

- **Skill backend:** ASK SDK (Python or Node). Maps intents to one summary call, renders speech
  and, when the device supports APL (`Alexa.Presentation.APL` in the request's supported
  interfaces), sends `Alexa.Presentation.APL.RenderDocument` with the Today document.
- **Home-screen widget:** Amazon offers APL widgets for some Echo Show devices, with data updated
  through the Alexa Data Store API. Confirm current device and region support in the Alexa Skills
  Kit documentation before committing to it; a widget would push the same summary on a schedule
  and when counts change, from a DayPilot job.
- **Notifications:** the Proactive Events API can announce "an approval is waiting"; it needs
  skill certification and per-user permission, and should carry no sensitive text.

## Privacy and safety

- A shared device speaks to whoever is in the room: v1 speaks titles and counts only. Use Alexa
  voice personalisation (recognised speaker) before reading anything more detailed.
- Unlinking the skill or revoking the token in DayPilot stops all access immediately.
- Log each summary request in DayPilot's audit log with the linked user.

## Milestones

1. OAuth provider in DayPilot with a `summary:read` scope; token revocation in settings.
2. `GET /v1/voice/summary` with tests that its numbers equal `/v1/today`'s.
3. Skill backend with the four intents, speech only; certification build in development stage.
4. APL Today document on Echo Show 15/21 (landscape) and smaller hubs.
5. Optional: home-screen widget via the Data Store API; proactive "approval waiting" notice.
6. Device test pass on an Echo Show 21, like the [web display checklist](README.md#on-device-verification-checklist).

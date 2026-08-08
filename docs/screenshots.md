# Screenshots

Every image in the documentation is captured from the running application against
a seeded workspace. None of them is a mockup, a design comp, or an edited export.

```bash
make shots          # seed a throwaway workspace, run the app, capture everything
```

That single command is the whole pipeline. It stands up a throwaway SQLite
database and two throwaway ports, seeds them through the real engines, runs the
API and the web UI, and drives a real browser through the product. A developer's
own workspace is never touched and never photographed.

## Why it works this way

A screenshot is a claim about the product. Taken by hand, months apart, the claims
drift: different themes, different data, screens that no longer look like that,
and — worst — screens showing content the product cannot actually produce.

So the pipeline is arranged to make drift visible instead of invisible:

- **The seeders drive the real engines.** The standup draft in the documentation
  is compiled by the shipped collector and compiler from the shipped evidence
  rows. If a bullet in the docs looks wrong, the code is wrong.
- **The shooter drives the real UI.** Screens are opened with the real keyboard
  shortcuts, the real command palette, and the real buttons — not by mounting a
  component with props. A shortcut that broke would break the screenshots.
- **One pass, one workspace, one size.** Everything is captured in a single run,
  so no two images disagree about what day it is or how much work exists.

## What is captured

| Set | Path | Contents |
|---|---|---|
| Product tour | `docs/assets/screenshots/tour/` | Home, command palette, Focus Mode, Approval Center, Planning, Projects, Documents, Email (dark + light), project wizard, patch review, Matrix Designer, four Settings sections, first-run onboarding, and four phone screens. |
| Daily Standup | `docs/assets/screenshots/standup/` | The 6:00 PM review, the evidence drawer, setup, the Home card, and the review on a phone. |
| Agents | `docs/assets/screenshots/agents/` | The agents directory, an agent workspace, the add-agent flow, and the workspace on a phone. Three of these need gallery access for portraits — see [`agents-ui-screenshots.md`](agents-ui-screenshots.md). |

## Capture settings

Desktop **1440×900**, phone **414×896**, both at `device_scale_factor=2`. GitHub
scales images down for display, so a 1× capture reads as soft on exactly the
displays this product is used on.

The desktop tour runs in dark theme; the Email workspace is captured a second time
in light theme, because that pair is the claim the README makes about theming.

## The pieces

| File | Role |
|---|---|
| `scripts/screenshots/capture.sh` | The pipeline: throwaway DB, seed, run, shoot, clean up. |
| `scripts/screenshots/seed_workspace.py` | One believable working day — four projects, a planned day, work in flight, decisions waiting. |
| `scripts/screenshots/seed_standup.py` | A day of real work, then the actual collector and compiler. |
| `scripts/screenshots/seed_agents.py` | HomePilot personas for the agents directory. |
| `scripts/screenshots/shoot_tour.py` | The README product tour. |
| `scripts/screenshots/shoot_standup.py` | The standup review, evidence drawer and setup. |
| `scripts/screenshots/shoot.py` | The agents UI. |

Seed order matters: the standup seeder runs **before** the workspace seeder,
because it compiles its draft from the day's evidence and the wider tour data
would otherwise crowd its three bullets.

## Adding a screen

Add the route (or the palette action) to `shoot_tour.py` with a selector that
proves the pane actually rendered, and reference the file from the document that
makes the claim. If a screen needs data to be worth photographing, seed it in
`seed_workspace.py` through the ordinary tables — never straight into a view.

Two things to keep in mind, both learned the hard way:

- A `goto` to the same `#/hash` is a same-document navigation, so React keeps its
  state and any open modal stays up to swallow the next click. Use `reset()`.
- Screens that autofocus draw a focus ring the moment they mount, which
  photographs as a stray box around a heading. `goto()` blurs for this reason.

## The optional Email module

The capture runs the API with `DAYPILOT_EMAIL_ENABLED=true` and
`DAYPILOT_EMAIL_PROVIDER=mock` — the documented mock backend — so the Email
screenshots show the workspace rather than the connect-your-mailbox state.
Sending stays approval-gated in every configuration, mock included.

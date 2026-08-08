# Regenerating the agents-UI screenshots

The images in `docs/assets/screenshots/agents/` are part of the one documentation
capture pipeline, so there is nothing agent-specific to run:

```bash
make shots
```

That seeds a throwaway workspace, runs the app, and captures every documentation
screenshot — the agents set included. See [`screenshots.md`](screenshots.md) for
how the pipeline works and how to add a screen.

Routes captured (hash-routed SPA): `#/agents`, `#/agents/scarlett`, `#/agents/add`,
plus a narrow-viewport workspace shot. Edit `scripts/screenshots/seed_agents.py`
to change the demo staff.

## Portraits need network access

Read this before re-running `make shots` on these three files.

`seed_agents.py` pulls each agent's portrait from the HomePilot Community Gallery.
Without access to it the seed still succeeds, but every card falls back to
initials — and portraits are the point of the agents directory, so
`agents-directory.png`, `agent-workspace.png` and `agent-workspace-mobile.png` are
checked in from a **networked** capture. A run on a machine that cannot reach the
gallery will overwrite them with initials circles. If that happens, restore the
three files rather than committing the regression.

To capture on a machine without gallery access, pre-download the bundles once and
point the seed at them:

```bash
mkdir -p /tmp/portraits
for id in scarlett_exec_secretary atlas_research_assistant felix_project_navigator \
          luca_calendar_strategist priya_inbox_alchemist elena_knowledge_curator \
          soren_shell_operator diana_office_navigator; do
  curl -sSL -o "/tmp/portraits/$id.hpersona" \
    "https://homepilot-persona-gallery.cloud-data.workers.dev/p/$id/1.0.0"
done

SEED_PORTRAIT_DIR=/tmp/portraits make shots
```

# From an idea (or a repo) to merged code

DayPilot builds software two ways, and they meet in the same place.

## Path A — you already have a repository

Nothing to design. Point a project at the repo once, then every run inherits it:

```
POST /v1/projects        { name, repository }
POST /v1/coding/runs     { task, projectId, mode }        ← repo is inherited
POST /v1/coding/runs/{id}/review   { decision: "approve" }
POST /v1/coding/runs/{id}/write    ← refused without an approved approval
```

`repo` is optional on a run: what you pass wins, otherwise the project's
repository is used, and a run with neither is refused rather than quietly
building nothing.

## Path B — you have an idea

Matrix Designer proposes plans, you choose one, and the chosen plan becomes
scheduled work that Path A then builds, batch by batch:

```
POST /v1/design/blueprints  { idea }                  → 3 candidate plans
POST /v1/design/refine      { idea, message, candidateId }   (optional)
POST /v1/design/review      { idea | bundle }                (optional)
POST /v1/design/bundles     { idea, candidateId, repository }
```

In the app this is one surface — **Plan a new build from an idea** (⌘K): describe
the idea, compare the three plans side by side with their effort, difficulty and
batch roadmap, adjust one in words ("add SSO"), optionally check it against the
designer's own rules, name the repository, and schedule it. Nothing is created
until that last step.

`/v1/design/bundles` designs the chosen plan in full and takes it in: one
project, one task per batch, in dependency order — the first batch active, the
rest scheduled, anything with unmet dependencies blocked. Each batch keeps the
`allowedFiles` and `mustNotChange` the design gave it, so the run that builds it
is scoped to exactly what the plan permits.

Using Matrix Designer is optional. Path A never touches it.

## Two independent choices per run

| | What it decides | Where it comes from |
|---|---|---|
| **Executor** | The governed pipeline: throwaway checkout, path policy, sandbox, risk score, draft PR | `GET /v1/coding/executors` |
| **Coder** | Only who *writes* the diff — the built-in model, Claude Code, Codex, or any headless agent | `GET /v1/coding/coders` |

Changing the coder changes nothing about governance. The coder list is asked of
the executor, which probes its own host, so an agent whose CLI or credential is
missing arrives marked unavailable *with the reason* instead of failing once a
run is already under way. Omit `coder` and the executor's deployment default is
used.

## What stays true on every path

* No write without an approved approval — enforced on the server, not in the UI.
* A run that cannot clone the repository fails; it never invents a patch for code
  it could not read. Private repositories need a credential on the executor
  (`GITPILOT_GIT_TOKEN`); see GitPilot's `docs/AI_CODERS.md`.
* Design, executor, and coder services that are unreachable are reported as
  unreachable — never as an empty plan or an empty picker.

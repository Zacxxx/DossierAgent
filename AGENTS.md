# Agent Development Workflow

This repository is developed issue by issue. The goal is to keep implementation aligned with `spec-AgentDossier.md` and prevent drift from the package architecture.

## Source Of Truth

The source of truth for product behavior and technical scope is:

- `spec-AgentDossier.md`
- `ARCHITECTURE.md`
- the active GitHub issue

When these disagree, stop and comment on the issue with the conflict. Do not silently invent a third direction.

## Required Workflow

1. Start from a GitHub issue.
2. Read the relevant section of `spec-AgentDossier.md`.
3. Identify the owning package before editing.
4. Confirm that the change does not require a feature package to import another feature package.
5. Implement the smallest vertical change that satisfies the issue.
6. Run relevant checks from the root.
7. Comment on the GitHub issue with:
   - what changed
   - spec section used
   - files touched
   - commands run
   - remaining gaps or follow-up issue numbers
8. Mark the issue complete only when all acceptance criteria are met.

## Issue Discipline

Each issue should contain:

- sprint milestone
- package label
- priority label
- spec references
- concrete acceptance criteria

If an issue is too broad to finish cleanly, split it before implementation.

## Package Discipline

Feature packages must stay independent:

```text
agent        must not import database/search_engine/browser/processing
database     must not import agent/processing/search_engine
browser      must not import processing/database/search_engine
processing   must not import database/search_engine/browser
schedule     must not import agent/browser/database
mcp          must not import search_engine/database
frontend     must call HTTP/API contracts only
```

The allowed composition point is `packages/core`.

When a package needs another concern, define a port or callable and have `core` provide the implementation at runtime.

## Frontend Foundation

The current static HTML frontend is only a root-launch smoke surface. Do not grow product UI on top of it.

Before implementing dashboard, listings, dossier, contact packet, or E2E frontend work, establish the frontend foundation in `packages/frontend`:

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- lucide-react
- TanStack Query for API state
- React Router for page routing
- Zod for frontend API contract validation when route payloads are non-trivial

Frontend rules:

- UI must read from API routes backed by SQLite seed data or implemented runtime flows.
- Do not hardcode product/demo state into components.
- Use shadcn/ui primitives for buttons, panels, inputs, tables, dialogs, tabs, badges, dropdowns, and forms unless there is a clear reason not to.
- Use lucide-react icons for icon buttons and status affordances.
- Keep API access in a typed client under `packages/frontend/src/api`.
- Keep reusable UI primitives under `packages/frontend/src/components/ui`.
- Keep route-level screens under `packages/frontend/src/routes`.
- Build dense, desktop-first operational screens as described in `spec-AgentDossier.md`; do not create a marketing landing page.
- Remove the temporary static shell once the Vite app is root-launchable.

## Spec Reference Format

Use this format in issue comments and PR descriptions:

```text
Spec reference:
- Section: <section title in spec-AgentDossier.md>
- Requirement: <short quote or paraphrase>
- Implementation: <how this change satisfies it>
```

Examples:

```text
Spec reference:
- Section: Schéma SQLite recommandé
- Requirement: SQLite must use WAL and contain users, listings, dossier, packets, checks, notifications, and run tables.
- Implementation: Added migration 0001 with the required tables and indexes.
```

## Completion Rules

Do not close an issue just because code was written.

An issue is complete only when:

- acceptance criteria are implemented
- tests or smoke checks were run
- root `bun run check` passes unless the issue explicitly changes the check system
- docs are updated if behavior or commands changed
- a GitHub issue comment records verification

## Commit And PR Expectations

Keep commits scoped to the issue. The preferred branch naming pattern is:

```text
issue-<number>-short-name
```

Pull request descriptions should include:

- linked issue
- package ownership
- spec reference
- verification commands
- known limitations

## No Drift Rules

Do not add:

- autonomous email sending
- login-requiring scraping
- captcha bypass
- multi-VM SQLite assumptions
- cross-package feature imports
- large abstractions not demanded by the active issue

Create a new issue for any tempting expansion.

# `frontend`

Desktop-first DossierAgent command center.

## Stack

- Vite
- React
- TypeScript
- Tailwind CSS
- shadcn/ui-compatible primitives in `src/components/ui`
- lucide-react
- TanStack Query
- React Router
- Zod API validation

## Owns

- dashboard UI
- watches UI
- listings master-detail UI
- dossier upload and preview UI
- contact packet editor UI
- pending checks and notifications UI
- frontend API client

## Does Not Own

- persistence
- scraping
- ranking
- document extraction
- agent reasoning

## Public Surface

The frontend talks to the backend through the `/api/v1` HTTP contract from the specification.

## Local Commands

- `bun run dev`
- `bun run check`
- `bun run build`

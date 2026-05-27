# DossierAgent Sprint Roadmap

This roadmap mirrors `spec-AgentDossier.md` and is represented as GitHub milestones and issues.

## Sprint 0 - Repo And Workflow Foundation

Goal: make the project understandable, executable from root, and ready for issue-based development.

- Package architecture
- Root launcher
- GitHub metadata
- Agent workflow
- README, issue templates, PR template

## Sprint 1 - Database And Core API Foundation

Goal: create the transactional foundation.

- SQLite connection and WAL setup
- Initial migration from the spec schema
- Repository interfaces
- Demo seed data
- FastAPI composition app in `core`
- `/health` and `/api/v1/dashboard`

## Sprint 2 - Watches, Agent Runs, And Scheduling

Goal: support the first rental watch lifecycle.

- Frontend foundation with Vite, React, TypeScript, Tailwind, shadcn/ui, lucide-react, TanStack Query, React Router, and Zod
- Criteria and market watch APIs
- Run-now endpoint
- Agent run and event timeline
- Due-watch policy
- Cron route
- Dashboard polling data

## Sprint 3 - Listings, Search, And Processing

Goal: make market memory useful.

- Listing normalization
- Exact and quasi-exact dedupe
- Deterministic ranking
- Elastic mappings
- Indexing and hybrid search
- Listings API and frontend master-detail view

## Sprint 4 - Browser Worker

Goal: extract controlled listing data from seed and allowed sources.

- Browser job model
- Source adapter contract
- URL direct extraction
- List page extraction
- Artifact writing
- Compliance guard

## Sprint 5 - Dossier And Contact Packets

Goal: analyze user documents and prepare supervised contact packets.

- Multipart upload
- Local PDF text extraction
- Document classification
- Readiness snapshot
- Contact packet draft
- User checks and notifications

## Sprint 6 - MCP, Demo, And Deployment

Goal: make the partner/demo story credible.

- Elastic Agent Builder MCP config
- Docker Compose with Elasticsearch and Kibana
- Demo seed script
- Playwright E2E smoke test
- VM deployment notes
- Final polish

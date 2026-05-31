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
- VM deployment notes in `docs/DEPLOYMENT_AND_DEMO.md`
- Final demo runbook in `docs/DEPLOYMENT_AND_DEMO.md`

## Sprint 7 - Auth And Spec Endpoint Completion

Goal: close missing spec-backed endpoint and lifecycle gaps after the first demo path.

- Supabase auth API and frontend session foundation
- Remaining core endpoint coverage
- Idempotency for contact packets and user checks
- Listing search indexing pipeline
- Dossier preview/delete endpoints
- Contact packet lifecycle API and editor UI
- Watch management, run history, notification center, and command composer
- Listing URL import and browser extraction orchestration

## Sprint 8 - AI Orchestration And Listing UX

Goal: expose platform tools through AI chat/MCP and make provider setup safe.

- Provider-backed AI chat over platform tools
- Local stdio MCP server for DossierAgent tools
- Listing card links, images, and explore actions
- AI chat and MCP evaluation suite
- Secure AI provider settings UI and encrypted server-side secret store
- Supabase register, login, logout, and forgotten-password frontend flows

## Sprint 9 - Final Agent Promise And Cloud Launch

Goal: close the remaining gaps required for a credible personal AI real-estate agent.

- #42 verified accessible VM demo deployment
- #51 full watch execution pipeline
- #52 compliant real-source adapters and source settings
- #49 semantic and hybrid search with embeddings
- #53 provider-backed constrained AI reasoning for ranking, dossier, and packet outputs
- #54 Elastic Agent Builder MCP verification in deployed stack
- #56 production scheduler and observability smoke checks
- #57 real app user provisioning from Supabase auth
- #58 cloud split with Vercel frontend and hosted API runtime

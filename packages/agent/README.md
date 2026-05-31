# `agent`

Supervised agent package.

## Owns

- free-text command parsing
- agent run intent planning
- prompt contracts
- supervised tool definitions
- user-check creation policy at the agent boundary
- AI chat system prompt and guardrail wording

## Does Not Own

- SQLite access
- Elastic queries
- Playwright extraction
- PDF parsing
- frontend UI

## Public Surface

- `parse_command`
- `ai_chat_system_prompt`
- `plan_agent_run`
- `listing_ranker_prompt`
- `build_contact_packet_instruction`
- `classify_dossier_instruction`

## Command Parser Contract

`parse_command` converts a free-text user command into a small structured
intent with `status`, `intent`, `action`, `parameters`, and `guardrails`.
It has no side effects and does not import database, browser, processing,
search, or frontend code. `core` decides whether and how an accepted command is
executed.

The MVP parser accepts supervised commands for market-watch runs, simple watch
creation, dossier analysis, and recommendation display. It rejects autonomous
external contact such as sending email or contacting a landlord directly.

## AI Chat Contract

`ai_chat_system_prompt` defines the provider-facing assistant boundary. It keeps
the chat aligned with supervised platform tools and repeats the no-autonomous
external-contact rule. Provider HTTP clients and secret loading stay in `core`.

## Listing Ranker Contract

The listing ranker prompt requires JSON only, forbids inventing missing data,
and treats the deterministic score from `processing` as immutable.

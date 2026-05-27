# `agent`

Supervised agent package.

## Owns

- free-text command parsing
- agent run intent planning
- prompt contracts
- supervised tool definitions
- user-check creation policy at the agent boundary

## Does Not Own

- SQLite access
- Elastic queries
- Playwright extraction
- PDF parsing
- frontend UI

## Public Surface

- `parse_command`
- `plan_agent_run`
- `build_contact_packet_instruction`
- `classify_dossier_instruction`


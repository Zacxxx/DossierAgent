# `core`

Tiny composition package for DossierAgent.

## Purpose

`core` lets developers stitch independently maintained packages together without turning a feature package into a dependency hub.

## Owns

- package manifests
- capability registry
- runtime orchestration
- lifecycle wiring
- Supabase auth adapter for API boundary authentication
- provider-backed AI chat adapters at the API boundary

## Does Not Own

- domain algorithms
- database queries
- Elastic mappings
- browser extraction
- UI state
- prompt text

## Public Surface

- `PackageManifest`
- `Capability`
- `PackageRegistry`
- `DossierAgentCore`

## Auth Boundary

`core` owns the Supabase Auth HTTP adapter because authentication is an API boundary concern. Feature packages must not import Supabase or depend on authenticated HTTP concepts. User-scoped routes resolve the current local user id in `core`, then pass that id into database repositories or package callables.

## Command Boundary

`core` exposes `POST /api/v1/agent/commands` as the composition point for
supervised natural-language commands. The agent package only parses and returns
structured intent. With `execute: false`, `core` returns the structured plan
without side effects. With `execute: true`, `core` resolves the current user,
checks guardrails, and orchestrates accepted actions through repository and
package callables.

The command endpoint must not send external messages. Contact remains a contact
packet plus user-check workflow.

## AI Chat Boundary

`core` exposes `GET /api/v1/ai/providers`,
`GET/PATCH /api/v1/ai/provider-settings`, and `POST /api/v1/ai/chat`.
Provider API keys stay in environment variables on the API process or in the
encrypted local secret store. The frontend receives provider availability,
runtime-fetched model metadata, and redacted configured field names, but never
receives secret values.

Tool-like chat messages are parsed by `packages/agent` and executed through the
same supervised command path before any provider call is attempted. Unsupported
messages can be forwarded to OpenAI, Anthropic, Google, or a local
Codex-compatible executable when configured.

Settings endpoints require a resolved authenticated user when auth is required.
In unauthenticated local-demo mode they accept local clients only.

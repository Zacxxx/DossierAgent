# `database`

SQLite persistence package.

## Owns

- SQLite WAL setup
- migrations
- table schemas
- repository primitives
- transaction boundaries local to persistence

## Does Not Own

- business scoring
- browser extraction
- Elastic search
- agent prompts

## Public Surface

- migration runner
- connection factory
- repositories for spec tables


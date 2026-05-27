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

## Connection

```python
from dossieragent_database import create_connection

connection = create_connection("data/dossieragent.db")
```

The connection factory applies the required MVP pragmas:

- `PRAGMA journal_mode=WAL`
- `PRAGMA foreign_keys=ON`
- `PRAGMA synchronous=NORMAL`

The path can be passed explicitly or configured through `DOSSIERAGENT_SQLITE_PATH`.

## Migrations

```python
from dossieragent_database import create_connection, run_migrations

connection = create_connection("data/dossieragent.db")
run_migrations(connection)
```

SQL files in `src/dossieragent_database/migrations` are applied in filename order. Applied migrations are tracked in `schema_migrations` and skipped on later runs when the checksum matches.

PACKAGE_MANIFEST = {
    "name": "database",
    "concern": "SQLite source of truth, migrations, and repositories.",
    "owns": (
        "sqlite wal setup",
        "schema migrations",
        "repository primitives",
        "transaction boundaries",
    ),
    "exposes": (
        "create_connection",
        "run_migrations",
        "build_repositories",
    ),
    "events": (
        "database.migrated",
    ),
}


def get_manifest() -> dict[str, object]:
    return dict(PACKAGE_MANIFEST)


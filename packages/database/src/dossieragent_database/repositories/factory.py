from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .base import SQLiteTableRepository
from .dashboard import DashboardRepository
from .dossier import DossierDocumentRepository
from .idempotency import IdempotencyKeyRepository
from .listings import ListingRepository
from .runs import AgentEventRepository, AgentRunRepository


@dataclass(frozen=True, slots=True)
class DatabaseRepositories:
    users: SQLiteTableRepository
    refresh_tokens: SQLiteTableRepository
    search_criteria: SQLiteTableRepository
    market_watches: SQLiteTableRepository
    listings: ListingRepository
    dossier_documents: DossierDocumentRepository
    dossier_snapshots: SQLiteTableRepository
    contact_packets: SQLiteTableRepository
    user_checks: SQLiteTableRepository
    notifications: SQLiteTableRepository
    agent_runs: AgentRunRepository
    agent_events: AgentEventRepository
    idempotency_keys: IdempotencyKeyRepository
    dashboard: DashboardRepository


def build_repositories(connection: sqlite3.Connection) -> DatabaseRepositories:
    return DatabaseRepositories(
        users=SQLiteTableRepository(connection, "users", user_scoped=False),
        refresh_tokens=SQLiteTableRepository(connection, "refresh_tokens"),
        search_criteria=SQLiteTableRepository(connection, "search_criteria"),
        market_watches=SQLiteTableRepository(connection, "market_watches"),
        listings=ListingRepository(connection),
        dossier_documents=DossierDocumentRepository(connection),
        dossier_snapshots=SQLiteTableRepository(connection, "dossier_snapshots"),
        contact_packets=SQLiteTableRepository(connection, "contact_packets"),
        user_checks=SQLiteTableRepository(connection, "user_checks"),
        notifications=SQLiteTableRepository(connection, "notifications"),
        agent_runs=AgentRunRepository(connection),
        agent_events=AgentEventRepository(connection),
        idempotency_keys=IdempotencyKeyRepository(connection),
        dashboard=DashboardRepository(connection),
    )

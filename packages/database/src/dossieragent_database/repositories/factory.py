from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .base import SQLiteTableRepository
from .contact_packets import ContactPacketRepository
from .dashboard import DashboardRepository
from .dossier import DossierDocumentRepository, DossierSnapshotRepository
from .idempotency import IdempotencyKeyRepository
from .listings import ListingRepository
from .notifications import NotificationRepository
from .runs import AgentEventRepository, AgentRunRepository
from .user_checks import UserCheckRepository


@dataclass(frozen=True, slots=True)
class DatabaseRepositories:
    users: SQLiteTableRepository
    refresh_tokens: SQLiteTableRepository
    search_criteria: SQLiteTableRepository
    market_watches: SQLiteTableRepository
    listings: ListingRepository
    dossier_documents: DossierDocumentRepository
    dossier_snapshots: DossierSnapshotRepository
    contact_packets: ContactPacketRepository
    user_checks: UserCheckRepository
    notifications: NotificationRepository
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
        dossier_snapshots=DossierSnapshotRepository(connection),
        contact_packets=ContactPacketRepository(connection),
        user_checks=UserCheckRepository(connection),
        notifications=NotificationRepository(connection),
        agent_runs=AgentRunRepository(connection),
        agent_events=AgentEventRepository(connection),
        idempotency_keys=IdempotencyKeyRepository(connection),
        dashboard=DashboardRepository(connection),
    )

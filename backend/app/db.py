from __future__ import annotations

import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "app.db"
MIGRATIONS = sorted(Path(__file__).resolve().parents[1].glob("migrations/*.sql"))
SEED_TIMESTAMP = "2026-01-01T00:00:00Z"
REQUIRED_TABLES = frozenset(
    {
        "schema_migrations",
        "dining_tables",
        "menu_items",
        "table_sessions",
        "restaurant_orders",
        "restaurant_order_lines",
        "kitchen_tickets",
        "payments",
        "receipts",
        "inventory",
        "stock_movements",
        "suppliers",
        "purchases",
        "purchase_lines",
        "warehouses",
        "audit_events",
        "idempotency_keys",
    }
)
RESET_STATEMENTS = tuple(
    f"DROP TABLE IF EXISTS {table}"
    for table in (
        "receipts", "payments", "kitchen_tickets", "restaurant_order_lines",
        "restaurant_orders", "table_sessions", "inventory", "menu_items",
        "menu_categories", "dining_tables", "dining_areas", "notifications", "settings",
        "attendance", "stock_movements", "purchase_lines", "purchases", "suppliers",
        "customers", "catalog_items", "idempotency_keys", "audit_events", "auth_sessions", "auth_user_roles", "auth_roles", "auth_users",
        "warehouses",
        "schema_migrations",
    )
)


def _migration_statements(sql: str):
    """Yield individual DDL statements so SQLite keeps one outer transaction."""
    return (statement.strip() for statement in sql.split(";") if statement.strip())


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATABASE_PATH, timeout=5, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def initialize(reset: bool = False) -> None:
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        if reset:
            for statement in RESET_STATEMENTS:
                c.execute(statement)
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for path in MIGRATIONS:
            version = int(path.name.split("_", 1)[0])
            if c.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
                continue
            for statement in _migration_statements(path.read_text(encoding="utf-8")):
                c.execute(statement)
            c.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, SEED_TIMESTAMP),
            )
        from .seed import seed
        seed(c)
        available = {row["name"] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(REQUIRED_TABLES - available)
        if missing:
            raise RuntimeError(f"Database initialization is incomplete; missing tables: {', '.join(missing)}")
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def reset() -> None:
    initialize(reset=True)

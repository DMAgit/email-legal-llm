"""Database connection setup for local SQLite persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.exceptions import PersistenceError
from app.infra.db.tables import create_schema


def create_connection(database_url: str) -> sqlite3.Connection:
    """Create a SQLite connection from a DATABASE_URL value."""
    database = sqlite_database_name(database_url)
    if database != ":memory:" and not database.startswith("file:"):
        Path(database).parent.mkdir(parents=True, exist_ok=True)

    try:
        connection = sqlite3.connect(
            database,
            check_same_thread=False,
            uri=database.startswith("file:"),
        )
    except sqlite3.Error as exc:
        raise PersistenceError(f"Could not connect to SQLite database: {exc}") from exc

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_url: str) -> None:
    """Create database tables for the configured SQLite database."""
    connection = create_connection(database_url)
    try:
        create_schema(connection)
    finally:
        connection.close()


def sqlite_database_name(database_url: str) -> str:
    """Return the sqlite3 database name for a sqlite:/// URL."""
    if not database_url.startswith("sqlite:///"):
        raise PersistenceError("Only sqlite:/// DATABASE_URL values are supported.")

    database = database_url.removeprefix("sqlite:///")
    if not database:
        raise PersistenceError("SQLite DATABASE_URL must include a database path.")
    return database

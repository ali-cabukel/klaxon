"""Encrypted Slack installation (token) storage."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet

from klaxon.settings import get_settings


@dataclass
class InstallationRecord:
    team_id: str
    team_name: str
    bot_token: str
    bot_user_id: str
    scopes: str
    installer_user_id: str
    refresh_token: str | None = None
    expires_at: int | None = None
    enterprise_id: str | None = None

    @property
    def is_expiring(self) -> bool:
        return self.expires_at is not None and self.expires_at - time.time() < 600


class InstallationStore(Protocol):
    def save(self, installation: InstallationRecord) -> None: ...
    def find(self, team_id: str) -> InstallationRecord | None: ...
    def delete(self, team_id: str) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS installations (
    team_id           TEXT PRIMARY KEY,
    team_name         TEXT NOT NULL,
    bot_token_enc     BLOB NOT NULL,
    bot_user_id       TEXT NOT NULL,
    scopes            TEXT NOT NULL,
    installer_user_id TEXT NOT NULL,
    refresh_token_enc BLOB,
    expires_at        INTEGER,
    enterprise_id     TEXT,
    updated_at        INTEGER NOT NULL
);
"""


class SQLiteInstallationStore:
    def __init__(
        self,
        database_path: str | None = None,
        encryption_key: str | None = None,
    ):
        settings = get_settings()
        path = database_path or settings.sqlite_path
        if path.endswith(".db"):
            path = path.replace(".db", "_slack.db")
        else:
            path = f"{path}_slack.db"
        self.path = path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        key = encryption_key or settings.token_encryption_key
        if not key:
            key = Fernet.generate_key().decode()
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _enc(self, value: str | None) -> bytes | None:
        return self._fernet.encrypt(value.encode()) if value else None

    def _dec(self, value: bytes | None) -> str | None:
        return self._fernet.decrypt(value).decode() if value else None

    def save(self, installation: InstallationRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO installations (
                    team_id, team_name, bot_token_enc, bot_user_id, scopes,
                    installer_user_id, refresh_token_enc, expires_at,
                    enterprise_id, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name=excluded.team_name,
                    bot_token_enc=excluded.bot_token_enc,
                    bot_user_id=excluded.bot_user_id,
                    scopes=excluded.scopes,
                    installer_user_id=excluded.installer_user_id,
                    refresh_token_enc=excluded.refresh_token_enc,
                    expires_at=excluded.expires_at,
                    enterprise_id=excluded.enterprise_id,
                    updated_at=excluded.updated_at
                """,
                (
                    installation.team_id,
                    installation.team_name,
                    self._enc(installation.bot_token),
                    installation.bot_user_id,
                    installation.scopes,
                    installation.installer_user_id,
                    self._enc(installation.refresh_token),
                    installation.expires_at,
                    installation.enterprise_id,
                    int(time.time()),
                ),
            )

    def find(self, team_id: str) -> InstallationRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM installations WHERE team_id = ?", (team_id,)
            ).fetchone()
        if row is None:
            return None
        return InstallationRecord(
            team_id=row["team_id"],
            team_name=row["team_name"],
            bot_token=self._dec(row["bot_token_enc"]) or "",
            bot_user_id=row["bot_user_id"],
            scopes=row["scopes"],
            installer_user_id=row["installer_user_id"],
            refresh_token=self._dec(row["refresh_token_enc"]),
            expires_at=row["expires_at"],
            enterprise_id=row["enterprise_id"],
        )

    def delete(self, team_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM installations WHERE team_id = ?", (team_id,))


@lru_cache(maxsize=1)
def get_installation_store() -> SQLiteInstallationStore:
    return SQLiteInstallationStore()

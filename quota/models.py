import json
import os
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .api import QuotaError, Server

GB = 1_000_000_000


def format_size(value):
    return f"{value / GB:,.1f} GB"


def _gb_setting(env, name, default, *, allow_zero=False):
    try:
        value = Decimal(env.get(name, str(default)))
        if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
            raise ValueError
        return int(value * GB)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError(f"{name} must be a positive number of GB.") from None


@dataclass(frozen=True)
class QuotaConfig:
    limit: int = 500 * GB
    movie_estimate: int = 20 * GB
    episode_estimate: int = 2 * GB
    movie_4k_estimate: int = 80 * GB
    episode_4k_estimate: int = 8 * GB
    reserve_downloads: bool = True
    state_file: str = ".data/quota.sqlite3"
    server_urls: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        reserve = env.get("QUOTA_RESERVE_DOWNLOADS", "true").lower()
        if reserve not in ("true", "false"):
            raise ValueError("QUOTA_RESERVE_DOWNLOADS must be true or false.")
        urls = json.loads(env.get("QUOTA_SERVER_URLS", "{}"))
        if not isinstance(urls, dict) or any(not isinstance(v, str) for v in urls.values()):
            raise ValueError("QUOTA_SERVER_URLS must map server IDs to URLs.")
        return cls(
            limit=_gb_setting(env, "AUTO_APPROVE_QUOTA_GB", 500, allow_zero=True),
            movie_estimate=_gb_setting(env, "QUOTA_MOVIE_ESTIMATE_GB", 20),
            episode_estimate=_gb_setting(env, "QUOTA_EPISODE_ESTIMATE_GB", 2),
            movie_4k_estimate=_gb_setting(env, "QUOTA_4K_MOVIE_ESTIMATE_GB", 80),
            episode_4k_estimate=_gb_setting(env, "QUOTA_4K_EPISODE_ESTIMATE_GB", 8),
            reserve_downloads=reserve == "true",
            state_file=env.get("QUOTA_STATE_FILE", ".data/quota.sqlite3"),
            server_urls=urls,
        )


@dataclass
class StorageItem:
    key: str
    title: str
    server: Server
    item_id: int
    media_type: str
    tmdb_id: int | None
    tvdb_id: int | None
    season: int | None
    size: int
    owners: frozenset[int]
    request_ids: tuple[int, ...]
    removable: bool
    reason: str = ""


@dataclass
class Snapshot:
    user_id: int
    limit: int
    used: int
    reserved: int
    items: list[StorageItem]
    requests: list[dict]
    inventories: list[dict] = field(default_factory=list, repr=False)

    @property
    def free(self):
        return max(0, self.limit - self.used - self.reserved)


@dataclass
class Approval:
    approved: bool
    message: str
    snapshot: Snapshot | None = None


class ApprovalJournal:
    """Keep uncertain approvals reserved across a bot/container restart."""

    def __init__(self, filename):
        self.filename = filename

    def _connect(self):
        try:
            Path(self.filename).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.filename, timeout=5)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS approvals "
                "(request_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "bytes INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS removed_units "
                "(request_id INTEGER NOT NULL, season INTEGER NOT NULL, "
                "PRIMARY KEY (request_id, season))"
            )
            return connection
        except (OSError, sqlite3.Error) as error:
            raise QuotaError("The bot cannot access its quota state file.") from error

    def pending(self, user_id):
        connection = self._connect()
        try:
            return dict(connection.execute(
                "SELECT request_id, bytes FROM approvals WHERE user_id = ?", (user_id,)
            ))
        finally:
            connection.close()

    def reserve(self, request_id, user_id, size):
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO approvals VALUES (?, ?, ?)", (request_id, user_id, size)
                )
                connection.execute(
                    "DELETE FROM removed_units WHERE request_id = ?", (request_id,)
                )
        finally:
            connection.close()

    def clear(self, request_id):
        connection = self._connect()
        try:
            with connection:
                connection.execute("DELETE FROM approvals WHERE request_id = ?", (request_id,))
        finally:
            connection.close()

    def removed_units(self):
        connection = self._connect()
        try:
            return set(connection.execute("SELECT request_id, season FROM removed_units"))
        finally:
            connection.close()

    def mark_removed(self, request_ids, season):
        connection = self._connect()
        try:
            with connection:
                connection.executemany(
                    "INSERT OR IGNORE INTO removed_units VALUES (?, ?)",
                    [(request_id, season if season is not None else -1)
                     for request_id in request_ids],
                )
        finally:
            connection.close()

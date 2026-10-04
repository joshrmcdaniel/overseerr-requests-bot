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

    @property
    def retention_key(self):
        media_id = self.tvdb_id if self.media_type == "tv" else self.tmdb_id
        return self.server.key, self.media_type, media_id, self.season if self.season is not None else -1


def retention_applies(keys, key):
    return key in keys or (*key[:3], -1) in keys


@dataclass
class RetainedItem:
    user_id: int
    server_key: str
    media_type: str
    media_id: int
    season: int
    title: str
    server_name: str
    size: int = 0

    @property
    def retention_key(self):
        return self.server_key, self.media_type, self.media_id, self.season

    @property
    def key(self):
        return ":".join(str(part) for part in self.retention_key)

    @classmethod
    def from_storage(cls, user_id, item, *, whole_series=False):
        server_key, kind, media_id, season = item.retention_key
        if not isinstance(media_id, int) or media_id <= 0:
            raise QuotaError("Cannot identify this title reliably. Refresh and try again.")
        title = item.title
        if whole_series and kind == "tv":
            season = -1
            title = title.removesuffix(f" — Season {item.season}")
        return cls(user_id, server_key, kind, media_id, season, title, item.server.name, item.size)


@dataclass
class Snapshot:
    user_id: int
    limit: int
    used: int
    reserved: int
    items: list[StorageItem]
    requests: list[dict]
    inventories: list[dict] = field(default_factory=list, repr=False)
    retained_items: list[RetainedItem] = field(default_factory=list)

    @property
    def free(self):
        return max(0, self.limit - self.used - self.reserved)


@dataclass
class Approval:
    approved: bool
    message: str
    snapshot: Snapshot | None = None


class ApprovalJournal:
    """Persist approval reservations, removals, and admin retention decisions."""

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
            connection.execute(
                "CREATE TABLE IF NOT EXISTS retained_items "
                "(user_id INTEGER NOT NULL, server_key TEXT NOT NULL, "
                "media_type TEXT NOT NULL, media_id INTEGER NOT NULL, season INTEGER NOT NULL, "
                "title TEXT NOT NULL, server_name TEXT NOT NULL, admin_id INTEGER NOT NULL, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "PRIMARY KEY (user_id, server_key, media_type, media_id, season))"
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

    def retained_items(self):
        connection = self._connect()
        try:
            return [RetainedItem(*row) for row in connection.execute(
                "SELECT user_id, server_key, media_type, media_id, season, title, server_name "
                "FROM retained_items ORDER BY title, season"
            )]
        finally:
            connection.close()

    def retain(self, item, admin_id):
        connection = self._connect()
        try:
            with connection:
                if item.season == -1:
                    # Keeping a whole show replaces this user's individual-season exceptions.
                    connection.execute(
                        "DELETE FROM retained_items WHERE user_id = ? AND server_key = ? "
                        "AND media_type = ? AND media_id = ?",
                        (item.user_id, *item.retention_key[:3]),
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO retained_items "
                    "(user_id, server_key, media_type, media_id, season, title, server_name, admin_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (item.user_id, *item.retention_key, item.title, item.server_name, admin_id),
                )
        finally:
            connection.close()

    def restore_retained(self, item):
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "DELETE FROM retained_items WHERE user_id = ? AND server_key = ? "
                    "AND media_type = ? AND media_id = ? AND season = ?",
                    (item.user_id, *item.retention_key),
                )
        finally:
            connection.close()

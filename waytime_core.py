"""Shared logic for waytime: per-app limits, evaluation, and storage.

This module is imported by both the CLI (`waytime`) and the daemon
(`waytime-daemon`). It deliberately has no D-Bus or GLib imports so it can be
unit-tested without a session bus.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import tomllib
from dataclasses import dataclass

DEFAULT_WARN_MINUTES = (15, 5, 1)
VALID_ACTIONS = ("close", "kill")
CONFIG_PATH = os.path.expanduser("~/.config/waytime/config.toml")
DB_PATH = os.path.expanduser("~/.local/share/waytime/waytime.db")


@dataclass(frozen=True)
class Limit:
    """A daily allowance for one application (KWin resourceClass)."""

    app: str
    minutes: int
    warn_minutes: tuple[int, ...] = DEFAULT_WARN_MINUTES
    action: str = "close"


def today() -> str:
    return dt.date.today().isoformat()


def normalize_app(app: str) -> str:
    return str(app).strip().casefold()


def pretty_app(app: str) -> str:
    name = str(app)
    for prefix in ("org.kde.", "org.gnome.", "com.", "io.", "net.", "dev."):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = name.split(".")[-1]
    return name.replace("-", " ").title() if name.islower() else name


def _parse_warn(value) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return DEFAULT_WARN_MINUTES
    seen = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        minutes = int(item)
        if minutes > 0:
            seen.add(minutes)
    return tuple(sorted(seen, reverse=True)) or DEFAULT_WARN_MINUTES


def load_limits(path: str = CONFIG_PATH) -> list[Limit]:
    """Read the limits config. Missing or malformed files mean "no limits".

    Failing open keeps the tracker running if the user edits the file by hand.
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError,
            tomllib.TOMLDecodeError):
        return []

    limits: list[Limit] = []
    entries = data.get("limits", [])
    if not isinstance(entries, list):
        return []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        app = str(entry.get("app", "")).strip()
        minutes = entry.get("minutes")
        if not app or isinstance(minutes, bool) or not isinstance(minutes, int):
            continue
        if minutes <= 0:
            continue
        action = str(entry.get("action", "close")).strip().lower()
        if action not in VALID_ACTIONS:
            action = "close"
        limits.append(
            Limit(
                app=app,
                minutes=minutes,
                warn_minutes=_parse_warn(entry.get("warn_minutes")),
                action=action,
            )
        )
    return limits


def save_limits(limits: list[Limit], path: str = CONFIG_PATH) -> None:
    """Write the limits config atomically, replacing the file."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    lines = ["# waytime per-app daily limits", "# managed by `waytime limit ...`", ""]
    for limit in limits:
        warn = ", ".join(str(w) for w in limit.warn_minutes)
        lines += [
            "[[limits]]",
            f"app = {json.dumps(limit.app)}",
            f"minutes = {limit.minutes}",
            f"warn_minutes = [{warn}]",
            f"action = {json.dumps(limit.action)}",
            "",
        ]
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.replace(tmp, path)


def find_limit(limits: list[Limit], app: str) -> Limit | None:
    key = normalize_app(app)
    for limit in limits:
        if normalize_app(limit.app) == key:
            return limit
    return None


def remaining_seconds(limit: Limit, used_seconds: float) -> float:
    return limit.minutes * 60 - used_seconds


def is_exhausted(limit: Limit, used_seconds: float) -> bool:
    return remaining_seconds(limit, used_seconds) <= 0


def due_warning(limit: Limit, remaining: float, fired: set[int]) -> int | None:
    """Return the warning (in minutes) that just became due, if any.

    `fired` is updated in place: every threshold at or below the current
    remaining time is marked as fired, so a long daemon stall or a jump in
    usage does not produce a burst of stale warnings.
    """
    if remaining <= 0:
        return None
    crossed = [
        w
        for w in limit.warn_minutes
        if w < limit.minutes and w * 60 >= remaining and w not in fired
    ]
    if not crossed:
        return None
    fired.update(crossed)
    return min(crossed)


class Store:
    """SQLite storage shared by the daemon and the CLI."""

    def __init__(self, path: str = DB_PATH):
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS usage (
                   date TEXT NOT NULL,
                   app TEXT NOT NULL,
                   seconds REAL NOT NULL DEFAULT 0,
                   PRIMARY KEY (date, app)
               )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS sites (
                   date TEXT NOT NULL,
                   site TEXT NOT NULL,
                   seconds REAL NOT NULL DEFAULT 0,
                   PRIMARY KEY (date, site)
               )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   ts TEXT NOT NULL,
                   date TEXT NOT NULL,
                   app TEXT NOT NULL,
                   kind TEXT NOT NULL,
                   detail TEXT NOT NULL DEFAULT ''
               )"""
        )
        self.db.commit()

    def add(self, app: str, site: str, seconds: float, date: str | None = None) -> None:
        day = date or today()
        self.db.execute(
            """INSERT INTO usage (date, app, seconds) VALUES (?, ?, ?)
               ON CONFLICT(date, app) DO UPDATE SET seconds = seconds + excluded.seconds""",
            (day, app, seconds),
        )
        if site:
            self.db.execute(
                """INSERT INTO sites (date, site, seconds) VALUES (?, ?, ?)
                   ON CONFLICT(date, site) DO UPDATE SET seconds = seconds + excluded.seconds""",
                (day, site, seconds),
            )
        self.db.commit()

    def usage(self, app: str, date: str | None = None) -> float:
        row = self.db.execute(
            "SELECT seconds FROM usage WHERE date = ? AND app = ?",
            (date or today(), app),
        ).fetchone()
        return float(row[0]) if row else 0.0

    def log_event(self, app: str, kind: str, detail: str = "") -> None:
        now = dt.datetime.now()
        self.db.execute(
            "INSERT INTO events (ts, date, app, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (now.isoformat(timespec="seconds"), now.date().isoformat(), app, kind, detail),
        )
        self.db.commit()

    def events(self, date: str | None = None) -> list[tuple[str, str, str, str]]:
        rows = self.db.execute(
            "SELECT ts, app, kind, detail FROM events WHERE date = ? ORDER BY ts",
            (date or today(),),
        ).fetchall()
        return [tuple(row) for row in rows]

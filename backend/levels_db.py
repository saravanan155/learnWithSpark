"""Versioned SQLite store for published levels (B13).

publish_level is the gated WRITE; get_level / list_levels are autonomous READS. A revisit bumps the
version and atomically swaps which version is `live` (the old one flips to `archived`).
"""

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent / "levels.sqlite"


@contextmanager
def _conn(db_path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS levels (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                level_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                title TEXT,
                concept TEXT,
                mechanic TEXT,
                spec_json TEXT NOT NULL,
                code TEXT NOT NULL,
                created_at REAL NOT NULL)"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_levels_live ON levels(level_id,status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_levels_version ON levels(level_id,version)")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _slug(text: str, fallback: str = "level") -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or fallback


def _level_id(spec: dict) -> str:
    """Stable public id for the level.

    The research gate uses transient ids like idea_a/idea_b, so prefer an explicit `level_id`, then a
    real LessonSpec id, and otherwise derive one from concept/title.
    """
    explicit = spec.get("level_id")
    if explicit:
        return _slug(str(explicit))
    spec_id = str(spec.get("id") or "")
    if spec_id and not re.fullmatch(r"idea_[a-z]", spec_id):
        return _slug(spec_id)
    return _slug(spec.get("concept") or spec.get("title"))


def publish_level(spec: dict, code: str, db_path: Path | str = DB_PATH) -> dict:
    """WRITE (gated): insert a new live version of a level, archiving the previous live one."""
    if not code.strip():
        raise ValueError("cannot publish an empty generated level")
    level_id = _level_id(spec)
    created_at = time.time()
    with _conn(db_path) as c:
        prev = c.execute("SELECT MAX(version) FROM levels WHERE level_id=?", (level_id,)).fetchone()
        version = (prev[0] or 0) + 1
        c.execute("UPDATE levels SET status='archived' WHERE level_id=? AND status='live'", (level_id,))
        c.execute(
            "INSERT INTO levels (level_id,version,status,title,concept,mechanic,spec_json,code,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                level_id,
                version,
                "live",
                spec.get("title", ""),
                spec.get("concept", ""),
                spec.get("mechanic", ""),
                json.dumps(spec, ensure_ascii=False),
                code,
                created_at,
            ),
        )
    return {
        "level_id": level_id,
        "version": version,
        "status": "live",
        "title": spec.get("title", ""),
        "created_at": created_at,
    }


def get_level(level_id: str, version: int | None = None, db_path: Path | str = DB_PATH) -> dict | None:
    """READ: a level by id (the live version unless a specific version is given)."""
    with _conn(db_path) as c:
        if version is None:
            r = c.execute(
                "SELECT spec_json,code,version,status,title,created_at FROM levels "
                "WHERE level_id=? AND status='live'",
                (level_id,),
            ).fetchone()
        else:
            r = c.execute(
                "SELECT spec_json,code,version,status,title,created_at FROM levels "
                "WHERE level_id=? AND version=?",
                (level_id, version),
            ).fetchone()
    return None if not r else {
        "level_id": level_id,
        "spec": json.loads(r[0]),
        "code": r[1],
        "version": r[2],
        "status": r[3],
        "title": r[4],
        "created_at": r[5],
    }


def list_levels(db_path: Path | str = DB_PATH) -> list[dict]:
    """READ: every level/version (id, version, status, title)."""
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT level_id,version,status,title,created_at FROM levels ORDER BY level_id,version"
        ).fetchall()
    return [
        {"level_id": a, "version": b, "status": s, "title": t, "created_at": created_at}
        for a, b, s, t, created_at in rows
    ]

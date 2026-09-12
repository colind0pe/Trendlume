"""Recreate the local development database.

This command is intentionally explicit and must never run during application
startup. It is only for local development where preserving old records is not
required:

    python backend/scripts/rebuild_dev_db.py --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.core.config import settings  # noqa: E402


def _database_path() -> Path:
    database_url = settings.database_url
    if not database_url.startswith("sqlite"):
        raise RuntimeError("rebuild_dev_db.py 仅允许用于 SQLite 数据库")

    marker = ":///"
    if marker not in database_url:
        raise RuntimeError(f"无法解析 SQLite 数据库路径: {database_url}")

    raw_path = database_url.split(marker, 1)[1].split("?", 1)[0]
    if not raw_path or raw_path == ":memory:" or raw_path.startswith("file:"):
        raise RuntimeError("rebuild_dev_db.py 仅支持文件型 SQLite 数据库")

    database_path = Path(raw_path)
    if not database_path.is_absolute():
        database_path = settings.base_dir / database_path
    return database_path.resolve()


def _backup_database(database_path: Path) -> Path | None:
    if not database_path.exists():
        return None

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = database_path.with_name(f"{database_path.name}.backup-{timestamp}")
    source = sqlite3.connect(str(database_path))
    target = sqlite3.connect(str(backup_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_path


def _remove_database_files(database_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{database_path}{suffix}")
        if candidate.exists():
            candidate.unlink()


def rebuild() -> None:
    database_path = _database_path()
    backup_path = _backup_database(database_path)
    _remove_database_files(database_path)

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
    )

    print(f"Rebuilt development database at: {database_path}")
    if backup_path:
        print(f"SQLite backup created at: {backup_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Trendlume SQLite development database")
    parser.add_argument("--yes", action="store_true", help="确认删除并重建现有数据库")
    args = parser.parse_args()
    if not args.yes:
        parser.error("This is destructive. Re-run with --yes to confirm.")
    rebuild()


if __name__ == "__main__":
    main()

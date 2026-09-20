import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command
from src.core.config import settings
from src.models import Base

ROOT = Path(__file__).resolve().parents[1]


def _run(url: str, revision: str, downgrade=False):
    original = settings.database_url
    try:
        settings.database_url = url
        config = Config(str(ROOT / "backend" / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
        (command.downgrade if downgrade else command.upgrade)(config, revision)
    finally:
        settings.database_url = original


def test_initial_schema_upgrade_downgrade_upgrade(tmp_path: Path):
    path = tmp_path / "schema.db"
    url = f"sqlite+aiosqlite:///{path.as_posix()}"
    _run(url, "head")
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("select name from sqlite_master where type='table'")
            if not row[0].startswith("sqlite_")
        }
        assert tables == set(Base.metadata.tables) | {"alembic_version"}
        assert connection.execute("select version_num from alembic_version").fetchone() == ("001",)
        assert connection.execute("pragma foreign_key_check").fetchall() == []
    _run(url, "base", downgrade=True)
    with sqlite3.connect(path) as connection:
        assert {
            row[0]
            for row in connection.execute("select name from sqlite_master where type='table'")
            if not row[0].startswith("sqlite_")
        } == {"alembic_version"}
    _run(url, "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("select version_num from alembic_version").fetchone() == ("001",)

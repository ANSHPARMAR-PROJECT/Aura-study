"""Create a consistent SQLite or PostgreSQL backup for AURA Study.

Run from the project root:
    python backend/scripts/backup_database.py
    python backend/scripts/backup_database.py --output-dir D:\\AURA-Backups
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")


def sqlite_backup(database_path: Path, output_path: Path) -> None:
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")
    source = sqlite3.connect(str(database_path))
    destination = sqlite3.connect(str(output_path))
    try:
        source.backup(destination)
        check = destination.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {check}")
    finally:
        destination.close()
        source.close()


def postgres_backup(url, output_path: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError("pg_dump was not found. Install PostgreSQL client tools and add pg_dump to PATH.")
    env = os.environ.copy()
    if url.username:
        env["PGUSER"] = url.username
    if url.password:
        env["PGPASSWORD"] = url.password
    if url.host:
        env["PGHOST"] = url.host
    if url.port:
        env["PGPORT"] = str(url.port)
    if url.database:
        env["PGDATABASE"] = url.database
    if "sslmode" in url.query:
        env["PGSSLMODE"] = str(url.query["sslmode"])
    subprocess.run([pg_dump, "--format=custom", "--no-owner", "--file", str(output_path)],
                   env=env, check=True, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the AURA Study database.")
    parser.add_argument("--output-dir", default=str(BACKEND_DIR / "backups"), help="Directory for backup files")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    database_url = os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'study_planner.db').as_posix()}")
    url = make_url(database_url)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if url.get_backend_name() == "sqlite":
        db_path = Path(url.database or "")
        if not db_path.is_absolute():
            db_path = (PROJECT_DIR / db_path).resolve()
        if str(db_path) == ":memory:":
            raise RuntimeError("In-memory SQLite databases cannot be backed up by this script.")
        output_path = output_dir / f"aura-study-{timestamp}.sqlite3"
        sqlite_backup(db_path, output_path)
    elif url.get_backend_name() == "postgresql":
        output_path = output_dir / f"aura-study-{timestamp}.dump"
        postgres_backup(url, output_path)
    else:
        raise RuntimeError(f"Unsupported database backend: {url.get_backend_name()}")

    print(f"Backup created: {output_path}")
    print(f"Size: {output_path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

"""Read-only database health and schema verification for AURA Study."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")
from database import engine  # noqa: E402

REQUIRED_TABLES = {
    "users", "subjects", "study_logs", "projects", "tasks", "schedule_events",
    "study_sessions", "user_preferences", "resources", "learning_quizzes",
    "quiz_attempts", "flashcards", "revision_items", "notifications", "reminders",
    "achievements", "study_groups", "study_group_members", "study_group_posts", "api_rate_limits",
}


def main() -> int:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    tables = set(inspect(engine).get_table_names())
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        print("Missing tables:", ", ".join(missing))
        print("Run database migrations or start AURA with AUTO_CREATE_DB=true.")
        return 1
    print(f"Database connection: OK ({engine.dialect.name})")
    print(f"Required tables: OK ({len(REQUIRED_TABLES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Database setup for AURA Study.

SQLite is used by default so a fresh clone runs without extra infrastructure.
Set DATABASE_URL to a PostgreSQL SQLAlchemy URL to use PostgreSQL instead.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String,
    Table, Text, UniqueConstraint, create_engine, event, select
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "study_planner.db"
# Preserve the legacy database automatically when users copy this backend into
# a project folder that already contains study_planner.db.
LEGACY_DB_PATH = BASE_DIR.parent / "study_planner.db"
if not os.getenv("DATABASE_URL") and not DEFAULT_DB_PATH.exists() and LEGACY_DB_PATH.exists():
    shutil.copy2(LEGACY_DB_PATH, DEFAULT_DB_PATH)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def utcnow_naive() -> datetime:
    """Return UTC time as naive datetime for legacy SQLAlchemy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


project_tags = Table(
    "project_tags", Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    subjects: Mapped[list["Subject"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    preferences: Mapped[Optional["UserPreferences"]] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)


class Subject(Base):
    """Legacy enrolled-course model; column names preserve the original SQLite schema."""
    __tablename__ = "subjects"
    __table_args__ = (CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_subject_difficulty"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    exam_date: Mapped[str] = mapped_column(String(10), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    target_hours: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    completed_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    user: Mapped[User] = relationship(back_populates="subjects")


class StudyLog(Base):
    """Legacy manual study logs; kept compatible with the uploaded project."""
    __tablename__ = "study_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    log_date: Mapped[str] = mapped_column(String(10), nullable=False)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color: Mapped[str] = mapped_column(String(30), default="sage")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    user: Mapped[User] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(secondary=project_tags, back_populates="projects")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    due_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    project: Mapped[Project] = relationship(back_populates="tasks")


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    color: Mapped[str] = mapped_column(String(30), default="lavender")
    event_type: Mapped[str] = mapped_column(String(30), default="study")
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_key", name="uq_study_session_user_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    session_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(30), default="sage")
    projects: Mapped[list[Project]] = relationship(secondary=project_tags, back_populates="tags")
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_user_name"),)


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    pomodoro_minutes: Mapped[int] = mapped_column(Integer, default=25)
    short_break_minutes: Mapped[int] = mapped_column(Integer, default=5)
    long_break_minutes: Mapped[int] = mapped_column(Integer, default=15)
    daily_goal_hours: Mapped[float] = mapped_column(Float, default=3.5)
    peak_focus_hours: Mapped[str] = mapped_column(String(120), default="09:00-12:00")
    theme: Mapped[str] = mapped_column(String(20), default="cream", nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user: Mapped[User] = relationship(back_populates="preferences")


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), default="link")
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stored_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class StudyGroup(Base):
    __tablename__ = "study_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    invite_code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class StudyGroupMember(Base):
    __tablename__ = "study_group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_study_group_member"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class StudyGroupPost(Base):
    __tablename__ = "study_group_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id: Mapped[Optional[int]] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content: Mapped[Text] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class LearningQuiz(Base):
    __tablename__ = "learning_quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    topic: Mapped[str] = mapped_column(String(180), default="General study")
    difficulty: Mapped[str] = mapped_column(String(20), default="standard")
    source: Mapped[str] = mapped_column(String(80), default="AURA")
    questions_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("learning_quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class Flashcard(Base):
    __tablename__ = "flashcards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    front: Mapped[str] = mapped_column(String(700), nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="manual")
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    due_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class RevisionItem(Base):
    __tablename__ = "revision_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)



class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notification_user_dedupe"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(String(600), nullable=False)
    action_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(180), nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_key", name="uq_achievement_user_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    achievement_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str] = mapped_column(String(30), default="award", nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)



class ApiRateLimitBucket(Base):
    """Hashed fixed-window rate-limit counters; raw IP addresses are never stored."""
    __tablename__ = "api_rate_limits"
    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


def init_db() -> None:
    """Create missing tables and add a default preference row for existing users."""
    Base.metadata.create_all(bind=engine)
    # create_all() creates new Phase 3 tables. Add preference/dismissal columns
    # safely for databases created by earlier AURA ZIP releases (SQLite/PostgreSQL).
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    existing_columns = {column["name"] for column in inspector.get_columns("user_preferences")}
    notification_columns = {column["name"] for column in inspector.get_columns("notifications")} if "notifications" in table_names else set()
    resource_columns = {column["name"] for column in inspector.get_columns("resources")} if "resources" in table_names else set()
    with engine.begin() as connection:
        if "theme" not in existing_columns:
            connection.execute(text("ALTER TABLE user_preferences ADD COLUMN theme VARCHAR(20) NOT NULL DEFAULT 'cream'"))
        if "notifications_enabled" not in existing_columns:
            connection.execute(text("ALTER TABLE user_preferences ADD COLUMN notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE"))
        if "dismissed_at" not in notification_columns:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN dismissed_at TIMESTAMP"))
        # Phase 4 adds document metadata without rebuilding or deleting legacy resources.
        if "description" not in resource_columns:
            connection.execute(text("ALTER TABLE resources ADD COLUMN description TEXT NOT NULL DEFAULT ''"))
        if "category" not in resource_columns:
            connection.execute(text("ALTER TABLE resources ADD COLUMN category VARCHAR(40) NOT NULL DEFAULT 'other'"))
        if "mime_type" not in resource_columns:
            connection.execute(text("ALTER TABLE resources ADD COLUMN mime_type VARCHAR(120)"))
        if "file_size" not in resource_columns:
            connection.execute(text("ALTER TABLE resources ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0"))
        if "updated_at" not in resource_columns:
            connection.execute(text("ALTER TABLE resources ADD COLUMN updated_at TIMESTAMP"))
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        for user in users:
            if user.preferences is None:
                user.preferences = UserPreferences()
        db.commit()


def get_db():
    return SessionLocal()

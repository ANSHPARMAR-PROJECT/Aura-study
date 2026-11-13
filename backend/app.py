from __future__ import annotations

import math
import os
import json
import secrets
import uuid
import mimetypes
import logging
import time
import hashlib
import hmac
from logging.handlers import RotatingFileHandler
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, redirect, send_from_directory, send_file, g
from sqlalchemy import and_, or_, select, func, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash
import jwt
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from database import (
    Flashcard, LearningQuiz, Project, QuizAttempt, Resource, RevisionItem,
    Achievement, ApiRateLimitBucket, Notification, Reminder, ScheduleEvent, SessionLocal, StudyLog, StudySession, Subject, Tag, Task, engine,
    StudyGroup, StudyGroupMember, StudyGroupPost, User, UserPreferences, init_db,
)
from ai_engine import get_ai_recommendations
from learning_engine import build_daily_plan, generate_flashcards, generate_quiz, next_flashcard_review

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "txt", "md", "png", "jpg", "jpeg", "webp"}

is_production = os.getenv("FLASK_ENV", "development").lower() == "production"
secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
if not secret_key:
    if is_production:
        raise RuntimeError("FLASK_SECRET_KEY must be set in production. Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
    secret_key = secrets.token_urlsafe(48)
    print("[AURA] No FLASK_SECRET_KEY found. A temporary development key was generated; sessions will reset on restart.")
if len(secret_key.encode("utf-8")) < 32:
    raise RuntimeError("FLASK_SECRET_KEY is too short. It must contain at least 32 UTF-8 bytes. Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
if is_production and not cookie_secure:
    raise RuntimeError("Set COOKIE_SECURE=true when running AURA Study in production behind HTTPS.")
if is_production and os.getenv("FLASK_DEBUG", "false").lower() == "true":
    raise RuntimeError("FLASK_DEBUG must be false in production.")

app = Flask(__name__)
allowed_hosts_setting = os.getenv("AURA_ALLOWED_HOSTS", "").strip()
if is_production and not allowed_hosts_setting:
    raise RuntimeError("Set AURA_ALLOWED_HOSTS to the exact host name(s) that serve AURA Study in production.")
allowed_hosts = [host.strip() for host in (allowed_hosts_setting or "localhost,127.0.0.1").split(",") if host.strip()]
auto_create_db = os.getenv("AUTO_CREATE_DB", "true").lower() == "true"
if is_production and auto_create_db:
    raise RuntimeError("Set AUTO_CREATE_DB=false in production and run `alembic upgrade head` before starting AURA.")
app.config.update(
    SECRET_KEY=secret_key,
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=cookie_secure,
    SESSION_COOKIE_NAME="aura_session",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    JWT_ACCESS_TOKEN_HOURS=int(os.getenv("JWT_ACCESS_TOKEN_HOURS", "12")),
    AUTO_CREATE_DB=auto_create_db,
    TRUSTED_HOSTS=allowed_hosts,
)

trusted_proxy_count = max(0, int(os.getenv("TRUSTED_PROXY_COUNT", "0")))
if trusted_proxy_count:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxy_count, x_proto=trusted_proxy_count,
                            x_host=trusted_proxy_count, x_port=trusted_proxy_count)

# Local logs rotate to disk; production logs go to stderr for the WSGI/container
# supervisor to collect (RotatingFileHandler is not multiprocess-safe).
LOG_DIR = BASE_DIR / "logs"
if not is_production:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
        file_handler = RotatingFileHandler(LOG_DIR / "aura.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        app.logger.addHandler(file_handler)
else:
    if not any(isinstance(handler, logging.StreamHandler) for handler in app.logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)

if app.config["AUTO_CREATE_DB"]:
    init_db()
else:
    from sqlalchemy import inspect
    required_tables = {"users", "api_rate_limits", "subjects", "study_logs"}
    missing_tables = required_tables - set(inspect(engine).get_table_names())
    if missing_tables:
        raise RuntimeError(
            "Database migrations are incomplete. Run `alembic upgrade head` from the project root. "
            f"Missing tables: {', '.join(sorted(missing_tables))}"
        )


def json_body() -> dict:
    return request.get_json(silent=True) or {}


def current_user_id() -> int:
    return int(g.user_id)


def token_user_id() -> int | None:
    token = request.cookies.get("aura_access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"], issuer="aura-study")
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def auth_cookie_response(payload: dict, user_id: int):
    issued_at = datetime.now(timezone.utc)
    token = jwt.encode({
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(hours=app.config["JWT_ACCESS_TOKEN_HOURS"]),
        "iss": "aura-study",
    }, app.config["SECRET_KEY"], algorithm="HS256")
    response = jsonify(payload)
    response.set_cookie(
        "aura_access_token", token, httponly=True,
        secure=app.config["SESSION_COOKIE_SECURE"], samesite="Lax",
        max_age=app.config["JWT_ACCESS_TOKEN_HOURS"] * 60 * 60, path="/",
    )
    return response


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rate_limit_for_request():
    """Return (scope, max_hits, window_seconds, user_scoped) for sensitive endpoints."""
    rules = {
        "/api/login": ("login", 8, 300, False),
        "/api/register": ("register", 5, 3600, False),
        "/api/learning/quizzes/generate": ("quiz-generate", 12, 60, True),
        "/api/learning/flashcards/generate": ("flashcards-generate", 12, 60, True),
        "/api/groups/join": ("group-join", 10, 3600, True),
    }
    return rules.get(request.path)


def _consume_rate_limit(scope: str, identity: str, max_hits: int, window_seconds: int) -> tuple[bool, int]:
    """Atomic DB-backed fixed-window limiter shared across app workers.

    Only an HMAC-SHA-256 digest is stored; raw IP addresses and identifiers are never persisted.
    SQLite and PostgreSQL both support INSERT .. ON CONFLICT.
    """
    window_id = int(time.time() // window_seconds)
    raw_key = f"{scope}:{identity}:{window_id}"
    bucket_key = hmac.new(app.config["SECRET_KEY"].encode("utf-8"), raw_key.encode("utf-8"), hashlib.sha256).hexdigest()
    retry_after = max(1, ((window_id + 1) * window_seconds) - int(time.time()))
    expires_at = _utc_naive_now() + timedelta(seconds=retry_after + 60)
    dialect = engine.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        raise RuntimeError(f"Database dialect '{dialect}' is not supported by the AURA rate limiter.")

    statement = dialect_insert(ApiRateLimitBucket).values(
        bucket_key=bucket_key, hit_count=1, expires_at=expires_at
    ).on_conflict_do_update(
        index_elements=[ApiRateLimitBucket.bucket_key],
        set_={"hit_count": ApiRateLimitBucket.hit_count + 1, "expires_at": expires_at},
    )
    with engine.begin() as connection:
        connection.execute(statement)
        hits = connection.execute(
            select(ApiRateLimitBucket.hit_count).where(ApiRateLimitBucket.bucket_key == bucket_key)
        ).scalar_one()
        if int(time.time()) % 300 == 0:
            connection.execute(delete(ApiRateLimitBucket).where(ApiRateLimitBucket.expires_at < _utc_naive_now()))
    return int(hits) <= max_hits, retry_after


@app.before_request
def attach_request_context():
    g.request_id = uuid.uuid4().hex
    g.request_started = time.perf_counter()


@app.before_request
def enforce_sensitive_endpoint_limits():
    rule = _rate_limit_for_request()
    if not rule:
        return None
    scope, max_hits, window_seconds, user_scoped = rule
    user_id = token_user_id() if user_scoped else None
    identity = f"user:{user_id}" if user_id is not None else f"ip:{request.remote_addr or 'unknown'}"
    try:
        allowed, retry_after = _consume_rate_limit(scope, identity, max_hits, window_seconds)
    except Exception:
        app.logger.exception("Rate limiter failed request_id=%s scope=%s", getattr(g, "request_id", "-"), scope)
        if is_production:
            return jsonify({"error": "Request protection is temporarily unavailable. Please try again shortly."}), 503
        # In development, don't make the whole local app unavailable if the limiter table is missing.
        return None
    if not allowed:
        response = jsonify({"error": "Too many requests. Please wait before trying again.", "retry_after_seconds": retry_after})
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response
    return None


@app.before_request
def protect_mutations():
    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.path in {"/api/login", "/api/register"}:
            return None
        if request.cookies.get("aura_access_token"):
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not supplied or not secrets.compare_digest(supplied, expected):
                return jsonify({"error": "Your session security token is missing or expired. Refresh the page and try again."}), 403
    return None


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
        "form-action 'self'; img-src 'self' data: blob:; font-src 'self' data: https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self'; connect-src 'self'; frame-src 'self' blob:"
    )
    response.headers.setdefault("X-Request-ID", getattr(g, "request_id", uuid.uuid4().hex))
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    started = getattr(g, "request_started", None)
    if started is not None:
        elapsed_ms = (time.perf_counter() - started) * 1000
        app.logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                        getattr(g, "request_id", "-"), request.method, request.path, response.status_code, elapsed_ms)
    return response


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = token_user_id()
        if user_id is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/auth")
        g.user_id = user_id
        return fn(*args, **kwargs)
    return wrapper


def serialize_subject(subject: Subject) -> dict:
    return {
        "id": subject.id, "user_id": subject.user_id, "name": subject.name,
        "exam_date": subject.exam_date, "difficulty": subject.difficulty,
        "target_hours": subject.target_hours, "completed_hours": subject.completed_hours,
    }


def project_progress(project: Project) -> int:
    if project.tasks:
        return round(sum(1 for task in project.tasks if task.status == "done") / len(project.tasks) * 100)
    return int(project.progress_percent or 0)


def serialize_project(project: Project, include_tasks: bool = True) -> dict:
    result = {
        "id": project.id, "title": project.title, "description": project.description or "",
        "deadline": project.deadline, "progress_percent": project_progress(project),
        "color": project.color, "task_count": len(project.tasks),
        "completed_tasks": sum(1 for task in project.tasks if task.status == "done"),
        "tags": [{"id": tag.id, "name": tag.name, "color": tag.color} for tag in project.tags],
    }
    if include_tasks:
        result["tasks"] = [{"id": t.id, "title": t.title, "status": t.status, "due_date": t.due_date} for t in project.tasks]
    return result


def serialize_event(event: ScheduleEvent) -> dict:
    return {
        "id": event.id, "title": event.title,
        "start_time": event.start_time.isoformat(timespec="minutes"),
        "end_time": event.end_time.isoformat(timespec="minutes"),
        "color": event.color, "event_type": event.event_type,
        "project_id": event.project_id, "subject_id": event.subject_id,
    }


def parse_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A start and end time are required.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Keep schedule times as local wall-clock values, matching the browser's datetime-local input.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def get_owned_project(db, project_id: int, user_id: int) -> Project | None:
    return db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))


def check_schedule_conflict(db, user_id: int, start: datetime, end: datetime, exclude_id: int | None = None) -> bool:
    query = select(ScheduleEvent.id).where(
        ScheduleEvent.user_id == user_id,
        ScheduleEvent.start_time < end,
        ScheduleEvent.end_time > start,
    )
    if exclude_id is not None:
        query = query.where(ScheduleEvent.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


# ---------------------------------------------------------------------------
# Frontend and authentication
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    if token_user_id() is None:
        return redirect("/auth")
    dist = BASE_DIR.parent / "frontend" / "dist"
    if (dist / "index.html").exists():
        return send_from_directory(dist, "index.html")
    return jsonify({"message": "AURA Study API is running. Start the Vite frontend with: npm run dev"}), 200


@app.get("/auth")
def auth_page():
    if token_user_id() is not None:
        return redirect("/")
    dist = BASE_DIR.parent / "frontend" / "dist"
    if (dist / "index.html").exists():
        return send_from_directory(dist, "index.html")
    return jsonify({"message": "Start the frontend with: npm run dev"}), 200


@app.get("/assets/<path:filename>")
def frontend_assets(filename):
    dist_assets = BASE_DIR.parent / "frontend" / "dist" / "assets"
    if dist_assets.exists():
        return send_from_directory(dist_assets, filename)
    return jsonify({"error": "Frontend assets are not built yet."}), 404


@app.get("/api/health")
def health_check():
    """Minimal health probe for deployment monitors; never exposes configuration."""
    try:
        with engine.connect() as connection:
            connection.execute(select(func.count()).select_from(User).limit(1))
        return jsonify({"status": "ok", "service": "aura-study"}), 200
    except SQLAlchemyError:
        app.logger.exception("Health check database failure request_id=%s", getattr(g, "request_id", "-"))
        return jsonify({"status": "unavailable", "service": "aura-study"}), 503


@app.get("/api/me")
@login_required
def me():
    with SessionLocal() as db:
        user = db.get(User, current_user_id())
        if not user:
            session.clear()
            return jsonify({"error": "User not found."}), 401
        return jsonify({"user": {"id": user.id, "username": user.username, "email": user.email}, "csrf_token": csrf_token()})


@app.patch("/api/profile")
@login_required
def update_profile():
    """Update the signed-in student's public profile details."""
    data = json_body()
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    if not username or len(username) < 3 or len(username) > 80:
        return jsonify({"error": "Username must be between 3 and 80 characters."}), 400
    if not email or len(email) > 255 or "@" not in email:
        return jsonify({"error": "Enter a valid email address."}), 400
    with SessionLocal() as db:
        user = db.get(User, current_user_id())
        if not user:
            return jsonify({"error": "User not found."}), 404
        user.username = username
        user.email = email
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return jsonify({"error": "That username or email is already in use."}), 409
        return jsonify({"user": {"id": user.id, "username": user.username, "email": user.email}})


@app.post("/api/register")
def register():
    data = json_body()
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password are required."}), 400
    if len(username) < 3 or len(username) > 80:
        return jsonify({"error": "Username must be between 3 and 80 characters."}), 400
    if "@" not in email or len(email) > 255:
        return jsonify({"error": "Enter a valid email address."}), 400
    if len(password) < 8:
        return jsonify({"error": "Use a password with at least 8 characters."}), 400
    with SessionLocal() as db:
        user = User(username=username, email=email, password_hash=generate_password_hash(password))
        user.preferences = UserPreferences()
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            return jsonify({"error": "That username or email is already registered."}), 409
        session.clear()
        session.permanent = True
        csrf = csrf_token()
        response = auth_cookie_response({"message": "Account created", "username": user.username, "csrf_token": csrf}, user.id)
        response.status_code = 201
        return response


@app.post("/api/login")
def login():
    data = json_body()
    identifier = str(data.get("identifier", "")).strip()
    password = str(data.get("password", ""))
    if not identifier or not password:
        return jsonify({"error": "Username/email and password are required."}), 400
    with SessionLocal() as db:
        user = db.scalar(select(User).where(or_(User.username == identifier, User.email == identifier.lower())))
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid username/email or password."}), 401
        session.clear()
        session.permanent = True
        response = auth_cookie_response({"message": "Login successful", "username": user.username, "csrf_token": csrf_token()}, user.id)
        return response


@app.post("/api/logout")
@login_required
def logout():
    session.clear()
    response = jsonify({"message": "Logged out successfully"})
    response.delete_cookie("aura_access_token", path="/", samesite="Lax")
    return response


# ---------------------------------------------------------------------------
# Dashboard and retained course/study-log functionality
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
@login_required
def dashboard():
    user_id = current_user_id()
    today = date.today().isoformat()
    try:
        schedule_day = date.fromisoformat(request.args.get("date", today))
    except ValueError:
        return jsonify({"error": "Choose a valid schedule date."}), 400
    day_start = datetime.combine(schedule_day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    with SessionLocal() as db:
        subjects = db.scalars(select(Subject).where(Subject.user_id == user_id).order_by(Subject.exam_date)).all()
        projects = db.scalars(select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())).all()
        events = db.scalars(select(ScheduleEvent).where(
            ScheduleEvent.user_id == user_id, ScheduleEvent.start_time < day_end,
            ScheduleEvent.end_time > day_start
        ).order_by(ScheduleEvent.start_time)).all()
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
        completed_today = db.scalar(select(func.coalesce(func.sum(StudyLog.hours), 0)).where(
            StudyLog.user_id == user_id, StudyLog.log_date == today
        )) or 0
        session_count = db.scalar(select(func.count(StudySession.id)).where(
            StudySession.user_id == user_id, StudySession.completed_at >= today_start,
            StudySession.completed_at < today_end
        )) or 0
        return jsonify({
            "subjects": [serialize_subject(s) for s in subjects],
            "projects": [serialize_project(p) for p in projects],
            "schedule": [serialize_event(e) for e in events],
            "stats": {"course_count": len(subjects), "project_count": len(projects),
                      "hours_today": round(float(completed_today), 2), "sessions_today": session_count},
            "preferences": serialize_preferences(prefs),
        })


def serialize_preferences(prefs: UserPreferences | None) -> dict:
    if not prefs:
        return {"pomodoro_minutes": 25, "short_break_minutes": 5, "long_break_minutes": 15,
                "daily_goal_hours": 3.5, "peak_focus_hours": "09:00-12:00",
                "theme": "cream", "notifications_enabled": True}
    return {"pomodoro_minutes": prefs.pomodoro_minutes, "short_break_minutes": prefs.short_break_minutes,
            "long_break_minutes": prefs.long_break_minutes, "daily_goal_hours": prefs.daily_goal_hours,
            "peak_focus_hours": prefs.peak_focus_hours, "theme": prefs.theme,
            "notifications_enabled": prefs.notifications_enabled}


@app.get("/api/subjects")
@login_required
def get_subjects():
    with SessionLocal() as db:
        subjects = db.scalars(select(Subject).where(Subject.user_id == current_user_id()).order_by(Subject.exam_date)).all()
        return jsonify([serialize_subject(s) for s in subjects])


@app.post("/api/subjects")
@login_required
def add_subject():
    data = json_body()
    name = str(data.get("name", "")).strip()
    exam_date = str(data.get("exam_date", ""))[:10]
    try:
        date.fromisoformat(exam_date)
        difficulty = int(data.get("difficulty", 3))
        target_hours = float(data.get("target_hours", 10))
        if not math.isfinite(target_hours) or target_hours <= 0 or difficulty not in range(1, 6):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid exam date, difficulty (1–5), and positive target hours."}), 400
    if not name or len(name) > 180:
        return jsonify({"error": "Course name is required and must be under 180 characters."}), 400
    with SessionLocal() as db:
        subject = Subject(user_id=current_user_id(), name=name, exam_date=exam_date,
                          difficulty=difficulty, target_hours=target_hours, completed_hours=0)
        db.add(subject)
        db.commit()
        db.refresh(subject)
        return jsonify({"message": "Course created", "subject": serialize_subject(subject)}), 201


@app.patch("/api/subjects/<int:subject_id>")
@login_required
def update_subject(subject_id: int):
    data = json_body()
    with SessionLocal() as db:
        subject = db.scalar(select(Subject).where(
            Subject.id == subject_id, Subject.user_id == current_user_id()
        ))
        if not subject:
            return jsonify({"error": "Course not found."}), 404
        name = str(data.get("name", subject.name)).strip()
        exam_date = str(data.get("exam_date", subject.exam_date))[:10]
        try:
            date.fromisoformat(exam_date)
            difficulty = int(data.get("difficulty", subject.difficulty))
            target_hours = float(data.get("target_hours", subject.target_hours))
            if difficulty not in range(1, 6) or not math.isfinite(target_hours) or target_hours <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Enter a valid exam date, difficulty (1–5), and positive target hours."}), 400
        if not name or len(name) > 180:
            return jsonify({"error": "Course name is required and must be under 180 characters."}), 400
        subject.name = name
        subject.exam_date = exam_date
        subject.difficulty = difficulty
        subject.target_hours = target_hours
        db.commit()
        return jsonify({"message": "Course updated.", "subject": serialize_subject(subject)})


@app.delete("/api/subjects/<int:subject_id>")
@login_required
def delete_subject(subject_id: int):
    with SessionLocal() as db:
        subject = db.scalar(select(Subject).where(Subject.id == subject_id, Subject.user_id == current_user_id()))
        if not subject:
            return jsonify({"error": "Course not found."}), 404
        db.delete(subject)
        db.commit()
        return jsonify({"message": "Course and associated logs deleted."})


@app.post("/api/log-hours")
@login_required
def log_hours():
    data = json_body()
    try:
        subject_id = int(data.get("subject_id"))
        hours = float(data.get("hours", 0))
        log_date = str(data.get("log_date") or date.today().isoformat())[:10]
        date.fromisoformat(log_date)
        if not math.isfinite(hours) or hours <= 0 or hours > 24:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid course, date, and study duration between 0 and 24 hours."}), 400
    with SessionLocal() as db:
        subject = db.scalar(select(Subject).where(Subject.id == subject_id, Subject.user_id == current_user_id()))
        if not subject:
            return jsonify({"error": "Course not found."}), 404
        subject.completed_hours += hours
        db.add(StudyLog(user_id=current_user_id(), subject_id=subject.id, hours=hours, log_date=log_date))
        db.commit()
        return jsonify({"message": "Study time logged", "completed_hours": round(subject.completed_hours, 2)})


# ---------------------------------------------------------------------------
# Projects, tasks, tags
# ---------------------------------------------------------------------------
@app.get("/api/projects")
@login_required
def get_projects():
    with SessionLocal() as db:
        projects = db.scalars(select(Project).where(Project.user_id == current_user_id()).order_by(Project.created_at.desc())).all()
        return jsonify([serialize_project(p) for p in projects])


@app.post("/api/projects")
@login_required
def create_project():
    data = json_body()
    title = str(data.get("title", "")).strip()
    deadline = data.get("deadline") or None
    if not title or len(title) > 180:
        return jsonify({"error": "A project title under 180 characters is required."}), 400
    if deadline:
        try:
            deadline = date.fromisoformat(str(deadline)[:10]).isoformat()
        except ValueError:
            return jsonify({"error": "Enter a valid project deadline."}), 400
    with SessionLocal() as db:
        color = data.get("color", "sage")
        if color not in {"sage", "lavender", "peach"}:
            color = "sage"
        project = Project(user_id=current_user_id(), title=title,
                          description=str(data.get("description", ""))[:4000],
                          deadline=deadline, color=color)
        db.add(project)
        db.commit()
        db.refresh(project)
        return jsonify({"project": serialize_project(project)}), 201


@app.patch("/api/projects/<int:project_id>")
@login_required
def update_project(project_id: int):
    data = json_body()
    with SessionLocal() as db:
        project = get_owned_project(db, project_id, current_user_id())
        if not project:
            return jsonify({"error": "Project not found."}), 404
        if "title" in data:
            title = str(data["title"]).strip()
            if not title or len(title) > 180:
                return jsonify({"error": "Project title is required."}), 400
            project.title = title
        if "description" in data:
            project.description = str(data["description"])[:4000]
        if "deadline" in data:
            value = data["deadline"] or None
            if value:
                try:
                    value = date.fromisoformat(str(value)[:10]).isoformat()
                except ValueError:
                    return jsonify({"error": "Invalid deadline."}), 400
            project.deadline = value
        if "progress_percent" in data:
            try:
                project.progress_percent = max(0, min(100, int(data["progress_percent"])))
            except (TypeError, ValueError):
                return jsonify({"error": "Progress must be between 0 and 100."}), 400
        db.commit()
        return jsonify({"project": serialize_project(project)})


@app.delete("/api/projects/<int:project_id>")
@login_required
def delete_project(project_id: int):
    with SessionLocal() as db:
        project = get_owned_project(db, project_id, current_user_id())
        if not project:
            return jsonify({"error": "Project not found."}), 404
        db.delete(project)
        db.commit()
        return jsonify({"message": "Project deleted."})


@app.post("/api/projects/<int:project_id>/tags")
@login_required
def add_project_tag(project_id: int):
    data = json_body()
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 50:
        return jsonify({"error": "Tag name is required and must be under 50 characters."}), 400
    with SessionLocal() as db:
        project = get_owned_project(db, project_id, current_user_id())
        if not project:
            return jsonify({"error": "Project not found."}), 404
        tag = db.scalar(select(Tag).where(Tag.user_id == current_user_id(), func.lower(Tag.name) == name.lower()))
        if not tag:
            tag = Tag(user_id=current_user_id(), name=name, color="lavender")
            db.add(tag)
            db.flush()
        if tag not in project.tags:
            project.tags.append(tag)
        db.commit()
        return jsonify({"tags": [{"id": t.id, "name": t.name, "color": t.color} for t in project.tags]})


@app.delete("/api/projects/<int:project_id>/tags/<int:tag_id>")
@login_required
def remove_project_tag(project_id: int, tag_id: int):
    with SessionLocal() as db:
        project = get_owned_project(db, project_id, current_user_id())
        tag = db.scalar(select(Tag).where(Tag.id == tag_id, Tag.user_id == current_user_id()))
        if not project or not tag or tag not in project.tags:
            return jsonify({"error": "Project tag not found."}), 404
        project.tags.remove(tag)
        db.commit()
        return jsonify({"message": "Tag removed."})


@app.post("/api/projects/<int:project_id>/tasks")
@login_required
def add_task(project_id: int):
    data = json_body()
    title = str(data.get("title", "")).strip()
    if not title or len(title) > 180:
        return jsonify({"error": "Task title is required."}), 400
    with SessionLocal() as db:
        project = get_owned_project(db, project_id, current_user_id())
        if not project:
            return jsonify({"error": "Project not found."}), 404
        due_date = data.get("due_date") or None
        if due_date:
            try:
                due_date = date.fromisoformat(str(due_date)[:10]).isoformat()
            except ValueError:
                return jsonify({"error": "Invalid task due date."}), 400
        task = Task(project_id=project.id, title=title, due_date=due_date)
        db.add(task)
        db.commit()
        db.refresh(task)
        return jsonify({"task": {"id": task.id, "title": task.title, "status": task.status, "due_date": task.due_date}}), 201


@app.patch("/api/tasks/<int:task_id>")
@login_required
def update_task(task_id: int):
    data = json_body()
    with SessionLocal() as db:
        task = db.scalar(select(Task).join(Project).where(Task.id == task_id, Project.user_id == current_user_id()))
        if not task:
            return jsonify({"error": "Task not found."}), 404
        if "title" in data:
            title = str(data["title"]).strip()
            if not title:
                return jsonify({"error": "Task title cannot be empty."}), 400
            task.title = title[:180]
        if "status" in data:
            if data["status"] not in {"todo", "done"}:
                return jsonify({"error": "Status must be todo or done."}), 400
            task.status = data["status"]
        if "due_date" in data:
            due_date = data["due_date"] or None
            if due_date:
                try:
                    due_date = date.fromisoformat(str(due_date)[:10]).isoformat()
                except ValueError:
                    return jsonify({"error": "Invalid task due date."}), 400
            task.due_date = due_date
        db.commit()
        return jsonify({"task": {"id": task.id, "title": task.title, "status": task.status, "due_date": task.due_date}})


@app.delete("/api/tasks/<int:task_id>")
@login_required
def delete_task(task_id: int):
    with SessionLocal() as db:
        task = db.scalar(select(Task).join(Project).where(Task.id == task_id, Project.user_id == current_user_id()))
        if not task:
            return jsonify({"error": "Task not found."}), 404
        db.delete(task)
        db.commit()
        return jsonify({"message": "Task deleted."})


# ---------------------------------------------------------------------------
# Schedule and timer
# ---------------------------------------------------------------------------
@app.get("/api/schedule")
@login_required
def get_schedule():
    start = request.args.get("start")
    end = request.args.get("end")
    try:
        start_dt = parse_datetime(start) if start else None
        end_dt = parse_datetime(end) if end else None
    except (TypeError, ValueError):
        return jsonify({"error": "Schedule date filters must be valid ISO date/time values."}), 400
    with SessionLocal() as db:
        query = select(ScheduleEvent).where(ScheduleEvent.user_id == current_user_id())
        if start_dt:
            query = query.where(ScheduleEvent.end_time > start_dt)
        if end_dt:
            query = query.where(ScheduleEvent.start_time < end_dt)
        events = db.scalars(query.order_by(ScheduleEvent.start_time)).all()
        return jsonify([serialize_event(event) for event in events])


@app.post("/api/schedule")
@login_required
def create_schedule_event():
    data = json_body()
    title = str(data.get("title", "")).strip()
    try:
        start = parse_datetime(data.get("start_time", ""))
        end = parse_datetime(data.get("end_time", ""))
    except (ValueError, TypeError):
        return jsonify({"error": "Choose a valid start and end time."}), 400
    if not title or len(title) > 180 or end <= start:
        return jsonify({"error": "Enter a title and an end time later than the start time."}), 400
    if (end - start).total_seconds() > 12 * 3600:
        return jsonify({"error": "A schedule block cannot exceed 12 hours."}), 400
    try:
        project_id = int(data["project_id"]) if data.get("project_id") else None
        subject_id = int(data["subject_id"]) if data.get("subject_id") else None
    except (TypeError, ValueError):
        return jsonify({"error": "Project and course references must be valid IDs."}), 400
    with SessionLocal() as db:
        user_id = current_user_id()
        if check_schedule_conflict(db, user_id, start, end):
            return jsonify({"error": "This time overlaps another event. Choose a different time or edit the existing block."}), 409
        if project_id and not get_owned_project(db, project_id, user_id):
            return jsonify({"error": "Project not found."}), 404
        if subject_id and not db.scalar(select(Subject.id).where(Subject.id == subject_id, Subject.user_id == user_id)):
            return jsonify({"error": "Course not found."}), 404
        color = data.get("color", "lavender")
        if color not in {"sage", "lavender", "peach"}:
            color = "lavender"
        event_type = data.get("event_type", "study")
        if event_type not in {"study", "break", "personal"}:
            return jsonify({"error": "Event type must be study, break, or personal."}), 400
        event = ScheduleEvent(user_id=user_id, title=title, start_time=start, end_time=end,
                              color=color, event_type=event_type,
                              project_id=int(project_id) if project_id else None,
                              subject_id=int(subject_id) if subject_id else None)
        db.add(event)
        db.commit()
        db.refresh(event)
        return jsonify({"event": serialize_event(event)}), 201


@app.patch("/api/schedule/<int:event_id>")
@login_required
def update_schedule_event(event_id: int):
    data = json_body()
    with SessionLocal() as db:
        event = db.scalar(select(ScheduleEvent).where(ScheduleEvent.id == event_id, ScheduleEvent.user_id == current_user_id()))
        if not event:
            return jsonify({"error": "Schedule event not found."}), 404
        try:
            start = parse_datetime(data.get("start_time", event.start_time.isoformat()))
            end = parse_datetime(data.get("end_time", event.end_time.isoformat()))
        except (ValueError, TypeError):
            return jsonify({"error": "Choose valid start and end times."}), 400
        if end <= start or (end - start).total_seconds() > 12 * 3600:
            return jsonify({"error": "Choose an end time after the start, with a maximum block length of 12 hours."}), 400
        if check_schedule_conflict(db, current_user_id(), start, end, exclude_id=event.id):
            return jsonify({"error": "This time overlaps another event."}), 409
        new_title = str(data.get("title", event.title)).strip()[:180]
        if not new_title:
            return jsonify({"error": "Event title cannot be empty."}), 400
        if "project_id" in data:
            try:
                project_id = int(data["project_id"]) if data["project_id"] else None
            except (TypeError, ValueError):
                return jsonify({"error": "Project ID must be valid."}), 400
            if project_id and not get_owned_project(db, project_id, current_user_id()):
                return jsonify({"error": "Project not found."}), 404
            event.project_id = project_id
        if "subject_id" in data:
            try:
                subject_id = int(data["subject_id"]) if data["subject_id"] else None
            except (TypeError, ValueError):
                return jsonify({"error": "Course ID must be valid."}), 400
            if subject_id and not db.scalar(select(Subject.id).where(Subject.id == subject_id, Subject.user_id == current_user_id())):
                return jsonify({"error": "Course not found."}), 404
            event.subject_id = subject_id
        if "event_type" in data:
            if data["event_type"] not in {"study", "break", "personal"}:
                return jsonify({"error": "Event type must be study, break, or personal."}), 400
            event.event_type = data["event_type"]
        if "color" in data:
            event.color = data["color"] if data["color"] in {"sage", "lavender", "peach"} else "lavender"
        event.title = new_title
        event.start_time, event.end_time = start, end
        db.commit()
        return jsonify({"event": serialize_event(event)})


@app.delete("/api/schedule/<int:event_id>")
@login_required
def delete_schedule_event(event_id: int):
    with SessionLocal() as db:
        event = db.scalar(select(ScheduleEvent).where(ScheduleEvent.id == event_id, ScheduleEvent.user_id == current_user_id()))
        if not event:
            return jsonify({"error": "Schedule event not found."}), 404
        db.delete(event)
        db.commit()
        return jsonify({"message": "Event deleted."})


@app.post("/api/timer/log")
@login_required
def log_timer_session():
    data = json_body()
    try:
        duration = int(data.get("duration_minutes", 0))
        if not 1 <= duration <= 240:
            raise ValueError
        session_key = str(data.get("session_key", "")).strip()
        if not session_key or len(session_key) > 80:
            raise ValueError
        started = parse_datetime(data.get("started_at", datetime.now().isoformat(timespec="minutes")))
        subject_id = int(data["subject_id"]) if data.get("subject_id") else None
        project_id = int(data["project_id"]) if data.get("project_id") else None
    except (TypeError, ValueError):
        return jsonify({"error": "A valid session key, start time, duration, and optional IDs are required."}), 400
    with SessionLocal() as db:
        existing = db.scalar(select(StudySession).where(StudySession.session_key == session_key, StudySession.user_id == current_user_id()))
        if existing:
            return jsonify({"message": "Session was already recorded.", "duplicate": True}), 200
        user_id = current_user_id()
        subject = None
        if subject_id:
            subject = db.scalar(select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id))
            if not subject:
                return jsonify({"error": "Course not found."}), 404
        if project_id and not get_owned_project(db, project_id, user_id):
            return jsonify({"error": "Project not found."}), 404
        record = StudySession(user_id=user_id, subject_id=subject.id if subject else None,
                              project_id=project_id,
                              duration_minutes=duration, started_at=started,
                              completed_at=datetime.now(), session_key=session_key)
        db.add(record)
        if subject:
            hours = round(duration / 60, 4)
            subject.completed_hours += hours
            db.add(StudyLog(user_id=user_id, subject_id=subject.id, hours=hours, log_date=date.today().isoformat()))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return jsonify({"message": "Session was already recorded.", "duplicate": True}), 200
        return jsonify({"message": "Focus session saved", "session_id": record.id}), 201


# ---------------------------------------------------------------------------
# AI recommendations and preferences
# ---------------------------------------------------------------------------
@app.get("/api/ai/recommendations")
@app.get("/api/recommendations")  # Backwards-compatible route from StudyPulse AI.
@login_required
def recommendations():
    user_id = current_user_id()
    with SessionLocal() as db:
        subjects = [serialize_subject(s) for s in db.scalars(select(Subject).where(Subject.user_id == user_id)).all()]
        logs = [{"subject_id": l.subject_id, "hours": l.hours, "log_date": l.log_date}
                for l in db.scalars(select(StudyLog).where(StudyLog.user_id == user_id).order_by(StudyLog.log_date)).all()]
        sessions = [{"duration_minutes": s.duration_minutes, "started_at": s.started_at.isoformat()}
                    for s in db.scalars(select(StudySession).where(StudySession.user_id == user_id).order_by(StudySession.started_at)).all()]
        try:
            plan_day = date.fromisoformat(request.args.get("date", date.today().isoformat()))
        except ValueError:
            return jsonify({"error": "Choose a valid recommendation date."}), 400
        plan_start = datetime.combine(plan_day, datetime.min.time())
        plan_end = plan_start + timedelta(days=1)
        events = [serialize_event(e) for e in db.scalars(select(ScheduleEvent).where(
            ScheduleEvent.user_id == user_id,
            ScheduleEvent.start_time < plan_end,
            ScheduleEvent.end_time > plan_start,
        ).order_by(ScheduleEvent.start_time)).all()]
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
        result = get_ai_recommendations(
            subjects, logs, sessions, events=events,
            daily_goal_hours=prefs.daily_goal_hours if prefs else 3.5,
            plan_date=plan_day,
            preferred_focus_hours=prefs.peak_focus_hours if prefs else "10:00-17:00",
        )
        return jsonify(result)


@app.get("/api/preferences")
@login_required
def get_preferences():
    with SessionLocal() as db:
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == current_user_id()))
        return jsonify(serialize_preferences(prefs))


@app.put("/api/preferences")
@login_required
def update_preferences():
    data = json_body()
    with SessionLocal() as db:
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == current_user_id()))
        if not prefs:
            prefs = UserPreferences(user_id=current_user_id())
            db.add(prefs)
        try:
            if "pomodoro_minutes" in data:
                prefs.pomodoro_minutes = int(data["pomodoro_minutes"])
                if not 10 <= prefs.pomodoro_minutes <= 90: raise ValueError
            if "short_break_minutes" in data:
                prefs.short_break_minutes = int(data["short_break_minutes"])
                if not 1 <= prefs.short_break_minutes <= 30: raise ValueError
            if "long_break_minutes" in data:
                prefs.long_break_minutes = int(data["long_break_minutes"])
                if not 5 <= prefs.long_break_minutes <= 60: raise ValueError
            if "daily_goal_hours" in data:
                prefs.daily_goal_hours = float(data["daily_goal_hours"])
                if not math.isfinite(prefs.daily_goal_hours) or not 0.5 <= prefs.daily_goal_hours <= 16: raise ValueError
            if "peak_focus_hours" in data:
                value = str(data["peak_focus_hours"]).strip()
                try:
                    start_text, end_text = value.split("-", 1)
                    start_time = datetime.strptime(start_text, "%H:%M").time()
                    end_time = datetime.strptime(end_text, "%H:%M").time()
                    if end_time <= start_time:
                        raise ValueError
                except (ValueError, TypeError):
                    db.rollback()
                    return jsonify({"error": "Preferred focus hours must be a valid same-day range, such as 09:00-12:00."}), 400
                prefs.peak_focus_hours = f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"
            if "theme" in data:
                theme = str(data["theme"])
                if theme not in {"cream", "night"}:
                    raise ValueError
                prefs.theme = theme
            if "notifications_enabled" in data:
                if not isinstance(data["notifications_enabled"], bool):
                    raise ValueError
                prefs.notifications_enabled = data["notifications_enabled"]
        except (TypeError, ValueError):
            db.rollback()
            return jsonify({"error": "Preference values are outside the allowed range."}), 400
        db.commit()
        return jsonify(serialize_preferences(prefs))


# ---------------------------------------------------------------------------
# Phase 2: adaptive learning hub (daily plan, quizzes, flashcards, revisions)
# ---------------------------------------------------------------------------
def _learning_subject(db, subject_id: int | None, user_id: int):
    if not subject_id:
        return None
    return db.scalar(select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id))


def _serialize_flashcard(card: Flashcard) -> dict:
    return {
        "id": card.id, "subject_id": card.subject_id, "front": card.front, "back": card.back,
        "source": card.source, "repetitions": card.repetitions, "interval_days": card.interval_days,
        "due_date": card.due_date, "last_reviewed_at": card.last_reviewed_at.isoformat() if card.last_reviewed_at else None,
        "created_at": card.created_at.isoformat() if card.created_at else None,
    }


def _serialize_revision(item: RevisionItem) -> dict:
    return {"id": item.id, "subject_id": item.subject_id, "title": item.title, "notes": item.notes,
            "due_date": item.due_date, "status": item.status,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None}


def _public_quiz(quiz: LearningQuiz, include_answers: bool = False) -> dict:
    questions = json.loads(quiz.questions_json or "[]")
    if not include_answers:
        questions = [{"question": q["question"], "options": q["options"]} for q in questions]
    return {"id": quiz.id, "subject_id": quiz.subject_id, "title": quiz.title, "topic": quiz.topic,
            "difficulty": quiz.difficulty, "source": quiz.source, "questions": questions,
            "created_at": quiz.created_at.isoformat() if quiz.created_at else None}


@app.get("/api/learning/overview")
@login_required
def learning_overview():
    user_id = current_user_id()
    today = date.today().isoformat()
    with SessionLocal() as db:
        due_cards = db.scalar(select(func.count(Flashcard.id)).where(
            Flashcard.user_id == user_id, Flashcard.due_date <= today)) or 0
        total_cards = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.user_id == user_id)) or 0
        due_revisions = db.scalar(select(func.count(RevisionItem.id)).where(
            RevisionItem.user_id == user_id, RevisionItem.status == "todo", RevisionItem.due_date <= today)) or 0
        open_revisions = db.scalar(select(func.count(RevisionItem.id)).where(
            RevisionItem.user_id == user_id, RevisionItem.status == "todo")) or 0
        quizzes = db.scalars(select(LearningQuiz).where(LearningQuiz.user_id == user_id)
                             .order_by(LearningQuiz.created_at.desc()).limit(8)).all()
        attempts = db.scalars(select(QuizAttempt).where(QuizAttempt.user_id == user_id)
                              .order_by(QuizAttempt.completed_at.desc()).limit(8)).all()
        return jsonify({
            "due_flashcards": int(due_cards), "total_flashcards": int(total_cards),
            "due_revisions": int(due_revisions), "open_revisions": int(open_revisions),
            "recent_quizzes": [{"id": q.id, "title": q.title, "topic": q.topic, "created_at": q.created_at.isoformat()} for q in quizzes],
            "recent_attempts": [{"id": a.id, "quiz_id": a.quiz_id, "score": a.score, "total": a.total,
                                 "percent": round(a.score / max(a.total, 1) * 100), "completed_at": a.completed_at.isoformat()} for a in attempts],
        })


@app.get("/api/learning/daily-plan")
@login_required
def get_learning_daily_plan():
    user_id = current_user_id()
    try:
        plan_day = date.fromisoformat(request.args.get("date", date.today().isoformat()))
    except ValueError:
        return jsonify({"error": "Choose a valid planning date."}), 400
    if (plan_day - date.today()).days > 31 or (date.today() - plan_day).days > 7:
        return jsonify({"error": "Daily plans can be generated up to 31 days ahead or 7 days back."}), 400
    day_start = datetime.combine(plan_day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    recent_from = (plan_day - timedelta(days=60)).isoformat()
    with SessionLocal() as db:
        subjects = db.scalars(select(Subject).where(Subject.user_id == user_id).order_by(Subject.exam_date)).all()
        events = db.scalars(select(ScheduleEvent).where(
            ScheduleEvent.user_id == user_id, ScheduleEvent.start_time < day_end, ScheduleEvent.end_time > day_start
        ).order_by(ScheduleEvent.start_time)).all()
        logs = db.scalars(select(StudyLog).where(
            StudyLog.user_id == user_id, StudyLog.log_date >= recent_from, StudyLog.log_date <= plan_day.isoformat()
        ).order_by(StudyLog.log_date)).all()
        task_rows = db.execute(select(Task, Project).join(Project, Task.project_id == Project.id).where(
            Project.user_id == user_id, Task.status != "done")).all()
        tasks = [{"id": task.id, "project_id": task.project_id, "title": task.title,
                  "due_date": task.due_date, "project_title": project.title,
                  "project_deadline": project.deadline} for task, project in task_rows]
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
        payload = build_daily_plan(
            [serialize_subject(s) for s in subjects],
            [serialize_event(e) for e in events],
            prefs.daily_goal_hours if prefs else 3.5,
            prefs.peak_focus_hours if prefs else "09:00-17:00",
            plan_day,
            [{"subject_id": l.subject_id, "log_date": l.log_date} for l in logs],
            tasks,
        )
        return jsonify(payload)


@app.post("/api/learning/daily-plan/apply")
@login_required
def apply_learning_daily_plan():
    user_id = current_user_id()
    data = json_body()
    try:
        plan_day = date.fromisoformat(str(data.get("date", date.today().isoformat())))
    except ValueError:
        return jsonify({"error": "Choose a valid planning date."}), 400
    if (plan_day - date.today()).days > 31 or (date.today() - plan_day).days > 7:
        return jsonify({"error": "Daily plans can be generated up to 31 days ahead or 7 days back."}), 400
    day_start = datetime.combine(plan_day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    recent_from = (plan_day - timedelta(days=60)).isoformat()
    with SessionLocal() as db:
        subjects = db.scalars(select(Subject).where(Subject.user_id == user_id).order_by(Subject.exam_date)).all()
        events = db.scalars(select(ScheduleEvent).where(
            ScheduleEvent.user_id == user_id, ScheduleEvent.start_time < day_end, ScheduleEvent.end_time > day_start
        ).order_by(ScheduleEvent.start_time)).all()
        logs = db.scalars(select(StudyLog).where(
            StudyLog.user_id == user_id, StudyLog.log_date >= recent_from, StudyLog.log_date <= plan_day.isoformat()
        )).all()
        task_rows = db.execute(select(Task, Project).join(Project, Task.project_id == Project.id).where(
            Project.user_id == user_id, Task.status != "done")).all()
        tasks = [{"id": task.id, "project_id": task.project_id, "title": task.title,
                  "due_date": task.due_date, "project_title": project.title,
                  "project_deadline": project.deadline} for task, project in task_rows]
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
        plan = build_daily_plan([serialize_subject(s) for s in subjects], [serialize_event(e) for e in events],
                                prefs.daily_goal_hours if prefs else 3.5,
                                prefs.peak_focus_hours if prefs else "09:00-17:00", plan_day,
                                [{"subject_id": l.subject_id, "log_date": l.log_date} for l in logs], tasks)
        if not plan["items"]:
            return jsonify({"error": plan["message"], "plan": plan}), 409
        created = []
        for item in plan["items"]:
            start = datetime.fromisoformat(item["start_time"])
            end = datetime.fromisoformat(item["end_time"])
            if check_schedule_conflict(db, user_id, start, end):
                db.rollback()
                return jsonify({"error": "Your schedule changed while this plan was being applied. Refresh the plan and try again."}), 409
            event = ScheduleEvent(user_id=user_id, title=item["title"], start_time=start, end_time=end,
                                  color="sage", event_type="study", subject_id=item.get("subject_id"),
                                  project_id=item.get("project_id"))
            db.add(event)
            created.append(event)
        db.commit()
        return jsonify({"message": f"Added {len(created)} study blocks to your schedule.",
                        "created_count": len(created), "plan": plan}), 201


@app.post("/api/learning/quizzes/generate")
@login_required
def create_learning_quiz():
    data = json_body()
    user_id = current_user_id()
    topic = str(data.get("topic", "")).strip()[:180]
    notes = str(data.get("notes", "")).strip()
    difficulty = str(data.get("difficulty", "standard")).lower()
    try:
        count = int(data.get("count", 5))
    except (TypeError, ValueError):
        return jsonify({"error": "Question count must be a number between 3 and 10."}), 400
    if not topic:
        return jsonify({"error": "Enter a quiz topic."}), 400
    if len(notes) < 20 or len(notes) > 12000:
        return jsonify({"error": "Paste at least 20 characters of study notes (maximum 12,000)."}), 400
    if count < 3 or count > 10:
        return jsonify({"error": "Choose between 3 and 10 questions."}), 400
    if difficulty not in {"easy", "standard", "hard"}:
        return jsonify({"error": "Choose easy, standard, or hard difficulty."}), 400
    with SessionLocal() as db:
        subject_id = data.get("subject_id")
        if subject_id and not _learning_subject(db, subject_id, user_id):
            return jsonify({"error": "The selected course was not found."}), 404
        subject = _learning_subject(db, subject_id, user_id) if subject_id else None
        try:
            questions, source = generate_quiz(topic, notes, count, difficulty)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        title = str(data.get("title") or f"{topic} · {difficulty.title()} quiz").strip()[:180]
        quiz = LearningQuiz(user_id=user_id, subject_id=subject.id if subject else None,
                            title=title, topic=topic, difficulty=difficulty, source=source,
                            questions_json=json.dumps(questions, ensure_ascii=False))
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        return jsonify({"quiz": _public_quiz(quiz)}), 201


@app.get("/api/learning/quizzes")
@login_required
def list_learning_quizzes():
    user_id = current_user_id()
    with SessionLocal() as db:
        quizzes = db.scalars(select(LearningQuiz).where(LearningQuiz.user_id == user_id)
                             .order_by(LearningQuiz.created_at.desc()).limit(30)).all()
        results = []
        for quiz in quizzes:
            latest = db.scalar(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.user_id == user_id)
                               .order_by(QuizAttempt.completed_at.desc()).limit(1))
            results.append({"id": quiz.id, "title": quiz.title, "topic": quiz.topic,
                            "difficulty": quiz.difficulty, "question_count": len(json.loads(quiz.questions_json or "[]")),
                            "created_at": quiz.created_at.isoformat(),
                            "latest_score": latest.score if latest else None,
                            "latest_total": latest.total if latest else None})
        return jsonify(results)


@app.get("/api/learning/quizzes/<int:quiz_id>")
@login_required
def get_learning_quiz(quiz_id: int):
    with SessionLocal() as db:
        quiz = db.scalar(select(LearningQuiz).where(LearningQuiz.id == quiz_id, LearningQuiz.user_id == current_user_id()))
        if not quiz:
            return jsonify({"error": "Quiz not found."}), 404
        return jsonify({"quiz": _public_quiz(quiz)})


@app.post("/api/learning/quizzes/<int:quiz_id>/attempts")
@login_required
def submit_learning_quiz(quiz_id: int):
    user_id = current_user_id()
    data = json_body()
    answers = data.get("answers")
    if not isinstance(answers, list):
        return jsonify({"error": "Submit an answer for each question."}), 400
    with SessionLocal() as db:
        quiz = db.scalar(select(LearningQuiz).where(LearningQuiz.id == quiz_id, LearningQuiz.user_id == user_id))
        if not quiz:
            return jsonify({"error": "Quiz not found."}), 404
        questions = json.loads(quiz.questions_json or "[]")
        if len(answers) != len(questions):
            return jsonify({"error": "Answer count does not match the quiz."}), 400
        results = []
        score = 0
        normalized_answers = []
        for index, question in enumerate(questions):
            try:
                choice = int(answers[index])
            except (TypeError, ValueError):
                choice = -1
            correct = choice == int(question["answer_index"])
            score += int(correct)
            normalized_answers.append(choice)
            results.append({"question": question["question"], "selected_index": choice,
                            "correct_index": int(question["answer_index"]), "is_correct": correct,
                            "explanation": question.get("explanation", "Review your notes for this topic.")})
        attempt = QuizAttempt(quiz_id=quiz.id, user_id=user_id, score=score, total=len(questions),
                              answers_json=json.dumps(normalized_answers))
        db.add(attempt)
        if quiz.subject_id and score / max(len(questions), 1) < 0.7:
            revision = RevisionItem(user_id=user_id, subject_id=quiz.subject_id,
                                    title=f"Review weak areas: {quiz.topic}",
                                    notes=f"Your latest quiz score was {score}/{len(questions)}. Revisit missed questions and explain the concepts without notes.",
                                    due_date=(date.today() + timedelta(days=1)).isoformat(), status="todo")
            db.add(revision)
        db.commit()
        return jsonify({"score": score, "total": len(questions), "percent": round(score / max(len(questions), 1) * 100),
                        "results": results, "revision_created": bool(quiz.subject_id and score / max(len(questions), 1) < 0.7)}), 201


@app.get("/api/learning/flashcards")
@login_required
def list_learning_flashcards():
    user_id = current_user_id()
    due_only = request.args.get("due_only", "false").lower() == "true"
    today = date.today().isoformat()
    with SessionLocal() as db:
        query = select(Flashcard).where(Flashcard.user_id == user_id)
        if due_only:
            query = query.where(Flashcard.due_date <= today)
        cards = db.scalars(query.order_by(Flashcard.due_date, Flashcard.created_at.desc()).limit(200)).all()
        return jsonify([_serialize_flashcard(card) for card in cards])


@app.post("/api/learning/flashcards")
@login_required
def create_learning_flashcard():
    data = json_body()
    front, back = str(data.get("front", "")).strip(), str(data.get("back", "")).strip()
    if not front or not back or len(front) > 700 or len(back) > 4000:
        return jsonify({"error": "Enter a front (max 700 characters) and answer (max 4,000 characters)."}), 400
    user_id = current_user_id()
    with SessionLocal() as db:
        subject = _learning_subject(db, data.get("subject_id"), user_id) if data.get("subject_id") else None
        if data.get("subject_id") and not subject:
            return jsonify({"error": "The selected course was not found."}), 404
        card = Flashcard(user_id=user_id, subject_id=subject.id if subject else None,
                         front=front, back=back, source="manual", due_date=date.today().isoformat())
        db.add(card)
        db.commit()
        db.refresh(card)
        return jsonify({"flashcard": _serialize_flashcard(card)}), 201


@app.post("/api/learning/flashcards/generate")
@login_required
def generate_learning_flashcards():
    data = json_body()
    user_id = current_user_id()
    topic = str(data.get("topic", "General study")).strip()[:180]
    notes = str(data.get("notes", "")).strip()
    try:
        count = int(data.get("count", 12))
    except (TypeError, ValueError):
        return jsonify({"error": "Flashcard count must be a number."}), 400
    if len(notes) < 20 or len(notes) > 12000:
        return jsonify({"error": "Paste at least 20 characters of study notes (maximum 12,000)."}), 400
    if count < 2 or count > 30:
        return jsonify({"error": "Choose between 2 and 30 flashcards."}), 400
    with SessionLocal() as db:
        subject = _learning_subject(db, data.get("subject_id"), user_id) if data.get("subject_id") else None
        if data.get("subject_id") and not subject:
            return jsonify({"error": "The selected course was not found."}), 404
        try:
            generated, source = generate_flashcards(topic, notes, count)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        cards = [Flashcard(user_id=user_id, subject_id=subject.id if subject else None,
                           front=item["front"], back=item["back"], source=source,
                           due_date=date.today().isoformat()) for item in generated]
        db.add_all(cards)
        db.commit()
        for card in cards:
            db.refresh(card)
        return jsonify({"message": f"Created {len(cards)} flashcards.",
                        "flashcards": [_serialize_flashcard(card) for card in cards], "source": source}), 201


@app.patch("/api/learning/flashcards/<int:card_id>/review")
@login_required
def review_learning_flashcard(card_id: int):
    rating = str(json_body().get("rating", "")).lower()
    with SessionLocal() as db:
        card = db.scalar(select(Flashcard).where(Flashcard.id == card_id, Flashcard.user_id == current_user_id()))
        if not card:
            return jsonify({"error": "Flashcard not found."}), 404
        try:
            repetitions, interval, due = next_flashcard_review(card, rating)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        card.repetitions, card.interval_days, card.due_date = repetitions, interval, due.isoformat()
        card.last_reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return jsonify({"flashcard": _serialize_flashcard(card), "message": f"Next review: {due.isoformat()}"})


@app.delete("/api/learning/flashcards/<int:card_id>")
@login_required
def delete_learning_flashcard(card_id: int):
    with SessionLocal() as db:
        card = db.scalar(select(Flashcard).where(Flashcard.id == card_id, Flashcard.user_id == current_user_id()))
        if not card:
            return jsonify({"error": "Flashcard not found."}), 404
        db.delete(card)
        db.commit()
        return jsonify({"message": "Flashcard deleted."})


@app.get("/api/learning/revisions")
@login_required
def list_revision_items():
    user_id = current_user_id()
    status = request.args.get("status", "open")
    with SessionLocal() as db:
        query = select(RevisionItem).where(RevisionItem.user_id == user_id)
        if status == "open":
            query = query.where(RevisionItem.status == "todo")
        elif status in {"todo", "done"}:
            query = query.where(RevisionItem.status == status)
        items = db.scalars(query.order_by(RevisionItem.due_date, RevisionItem.created_at.desc()).limit(200)).all()
        return jsonify([_serialize_revision(item) for item in items])


@app.post("/api/learning/revisions")
@login_required
def create_revision_item():
    data = json_body()
    title = str(data.get("title", "")).strip()
    notes = str(data.get("notes", "")).strip()[:4000]
    try:
        due_date = date.fromisoformat(str(data.get("due_date", date.today().isoformat()))).isoformat()
    except ValueError:
        return jsonify({"error": "Choose a valid revision date."}), 400
    if not title or len(title) > 180:
        return jsonify({"error": "A revision title is required (max 180 characters)."}), 400
    user_id = current_user_id()
    with SessionLocal() as db:
        subject = _learning_subject(db, data.get("subject_id"), user_id) if data.get("subject_id") else None
        if data.get("subject_id") and not subject:
            return jsonify({"error": "The selected course was not found."}), 404
        item = RevisionItem(user_id=user_id, subject_id=subject.id if subject else None,
                            title=title, notes=notes, due_date=due_date, status="todo")
        db.add(item)
        db.commit()
        db.refresh(item)
        return jsonify({"revision": _serialize_revision(item)}), 201


@app.patch("/api/learning/revisions/<int:item_id>")
@login_required
def update_revision_item(item_id: int):
    data = json_body()
    with SessionLocal() as db:
        item = db.scalar(select(RevisionItem).where(RevisionItem.id == item_id, RevisionItem.user_id == current_user_id()))
        if not item:
            return jsonify({"error": "Revision item not found."}), 404
        if "title" in data:
            title = str(data["title"]).strip()
            if not title or len(title) > 180:
                return jsonify({"error": "Revision title must contain 1–180 characters."}), 400
            item.title = title
        if "notes" in data:
            item.notes = str(data["notes"]).strip()[:4000]
        if "due_date" in data:
            try:
                item.due_date = date.fromisoformat(str(data["due_date"])).isoformat()
            except ValueError:
                return jsonify({"error": "Choose a valid revision date."}), 400
        if "status" in data:
            if data["status"] not in {"todo", "done"}:
                return jsonify({"error": "Status must be todo or done."}), 400
            item.status = data["status"]
            item.completed_at = datetime.now(timezone.utc).replace(tzinfo=None) if item.status == "done" else None
        db.commit()
        return jsonify({"revision": _serialize_revision(item)})


@app.delete("/api/learning/revisions/<int:item_id>")
@login_required
def delete_revision_item(item_id: int):
    with SessionLocal() as db:
        item = db.scalar(select(RevisionItem).where(RevisionItem.id == item_id, RevisionItem.user_id == current_user_id()))
        if not item:
            return jsonify({"error": "Revision item not found."}), 404
        db.delete(item)
        db.commit()
        return jsonify({"message": "Revision item deleted."})



# ---------------------------------------------------------------------------
# Phase 3: student productivity (analytics, goals, achievements, notifications)
# ---------------------------------------------------------------------------

ACHIEVEMENT_CATALOG = [
    {"key": "first_focus", "title": "First Focus", "description": "Complete your first focused study session.", "icon": "zap", "target": 1, "metric": "sessions"},
    {"key": "ten_sessions", "title": "Focus Builder", "description": "Complete 10 focused study sessions.", "icon": "target", "target": 10, "metric": "sessions"},
    {"key": "twenty_five_hours", "title": "25-Hour Club", "description": "Record 25 hours of study time.", "icon": "clock", "target": 25, "metric": "hours"},
    {"key": "seven_day_streak", "title": "A Week of Momentum", "description": "Study on seven consecutive days.", "icon": "flame", "target": 7, "metric": "streak"},
    {"key": "thirty_day_streak", "title": "Consistency Champion", "description": "Study on 30 consecutive days.", "icon": "trophy", "target": 30, "metric": "streak"},
    {"key": "first_quiz", "title": "Active Recall Starter", "description": "Complete your first learning quiz.", "icon": "brain", "target": 1, "metric": "quizzes"},
    {"key": "five_quizzes", "title": "Recall in Rhythm", "description": "Complete five learning quizzes.", "icon": "graduation-cap", "target": 5, "metric": "quizzes"},
    {"key": "three_goal_days", "title": "Goal Keeper", "description": "Meet your daily study goal on three days.", "icon": "award", "target": 3, "metric": "goal_days"},
]

def _safe_iso_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None

def _create_productivity_notification(db, user_id: int, kind: str, title: str, message: str, dedupe_key: str, action_url: str | None = None) -> None:
    existing = db.scalar(select(Notification.id).where(
        Notification.user_id == user_id, Notification.dedupe_key == dedupe_key
    ))
    if existing is None:
        db.add(Notification(user_id=user_id, kind=kind, title=title[:180], message=message[:600],
                            dedupe_key=dedupe_key[:180], action_url=action_url))

def _sync_due_item_notifications(db, user_id: int, today: date) -> None:
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
    if prefs and not prefs.notifications_enabled:
        return
    subjects = db.scalars(select(Subject).where(Subject.user_id == user_id)).all()
    for subject in subjects:
        exam_day = _safe_iso_date(subject.exam_date)
        if not exam_day:
            continue
        days_left = (exam_day - today).days
        if 0 <= days_left <= 7:
            when = "today" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days"
            _create_productivity_notification(
                db, user_id, "exam", "Exam coming up",
                f"{subject.name} is scheduled {when} ({exam_day.isoformat()}). Make time for a focused review.",
                f"exam:{subject.id}:{exam_day.isoformat()}", "/schedule",
            )
    tasks = db.scalars(select(Task).join(Project, Task.project_id == Project.id).where(
        Project.user_id == user_id, Task.status != "done", Task.due_date.is_not(None)
    )).all()
    for task in tasks:
        due = _safe_iso_date(task.due_date)
        days_left = (due - today).days if due else 9999
        if not due or not -7 <= days_left <= 3:
            continue
        status = "overdue" if days_left < 0 else "due today" if days_left == 0 else "due tomorrow" if days_left == 1 else f"due in {days_left} days"
        _create_productivity_notification(
            db, user_id, "task", "Project task reminder",
            f"{task.title} is {status} ({due.isoformat()}).",
            f"task:{task.id}:{due.isoformat()}", "/projects",
        )

def _calculate_streaks(active_dates: set[date], today: date) -> tuple[int, int]:
    if not active_dates:
        return 0, 0
    ordered = sorted(active_dates)
    longest = current = 1
    for previous, current_day in zip(ordered, ordered[1:]):
        if (current_day - previous).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    anchor = today if today in active_dates else today - timedelta(days=1)
    current_streak = 0
    while anchor in active_dates:
        current_streak += 1
        anchor -= timedelta(days=1)
    return current_streak, longest

def _sync_achievements(db, user_id: int, metrics: dict) -> list[dict]:
    session_count = int(metrics["lifetime_sessions"])
    total_hours = float(metrics["lifetime_hours"])
    quiz_count = int(metrics["quiz_count"])
    goal_days = int(metrics["goal_days_30"])
    streak = max(int(metrics["current_streak"]), int(metrics["longest_streak"]))
    values = {"sessions": session_count, "hours": total_hours, "quizzes": quiz_count, "goal_days": goal_days, "streak": streak}
    earned_rows = db.scalars(select(Achievement).where(Achievement.user_id == user_id)).all()
    earned_by_key = {row.achievement_key: row for row in earned_rows}
    for item in ACHIEVEMENT_CATALOG:
        if item["key"] in earned_by_key or values[item["metric"]] < item["target"]:
            continue
        row = Achievement(user_id=user_id, achievement_key=item["key"], title=item["title"],
                          description=item["description"], icon=item["icon"])
        db.add(row)
        _create_productivity_notification(db, user_id, "achievement", "Achievement unlocked",
            f"You earned {item['title']}: {item['description']}", f"achievement:{item['key']}", "/productivity")
        earned_by_key[item["key"]] = row
    db.flush()
    result = []
    for item in ACHIEVEMENT_CATALOG:
        row = earned_by_key.get(item["key"])
        progress = min(100, round(values[item["metric"]] / item["target"] * 100)) if item["target"] else 0
        result.append({**item, "unlocked": row is not None,
                       "earned_at": row.earned_at.isoformat() if row and row.earned_at else None,
                       "progress": progress, "current": round(values[item["metric"]], 1)})
    return result

def _productivity_analytics(db, user_id: int, days: int) -> dict:
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    heatmap_start = today - timedelta(days=69)
    all_logs = db.scalars(select(StudyLog).where(StudyLog.user_id == user_id)).all()
    all_sessions = db.scalars(select(StudySession).where(StudySession.user_id == user_id)).all()
    logs_by_day: dict[str, float] = {}
    active_dates: set[date] = set()
    for log in all_logs:
        day_value = _safe_iso_date(log.log_date)
        if day_value:
            key = day_value.isoformat()
            logs_by_day[key] = logs_by_day.get(key, 0.0) + float(log.hours or 0)
            if float(log.hours or 0) > 0 and day_value <= today:
                active_dates.add(day_value)
    sessions_by_day: dict[str, int] = {}
    session_hours_without_course: dict[str, float] = {}
    hour_counts = [0] * 24
    for study_session in all_sessions:
        if study_session.completed_at:
            completed_day = study_session.completed_at.date()
            key = completed_day.isoformat()
            if start_day <= completed_day <= today:
                sessions_by_day[key] = sessions_by_day.get(key, 0) + 1
                if study_session.started_at:
                    hour_counts[study_session.started_at.hour] += 1
            if completed_day <= today:
                active_dates.add(completed_day)
        # Course-linked timer sessions already create a StudyLog row. Count only
        # sessions without a course here to avoid double-counting their hours.
        if study_session.subject_id is None and study_session.completed_at:
            key = study_session.completed_at.date().isoformat()
            session_hours_without_course[key] = session_hours_without_course.get(key, 0.0) + study_session.duration_minutes / 60.0
    daily = []
    for offset in range(days):
        day_value = start_day + timedelta(days=offset)
        key = day_value.isoformat()
        hours = logs_by_day.get(key, 0.0) + session_hours_without_course.get(key, 0.0)
        daily.append({"date": key, "label": day_value.strftime("%b %d"), "hours": round(hours, 2),
                      "sessions": sessions_by_day.get(key, 0)})
    heatmap = []
    for offset in range(70):
        day_value = heatmap_start + timedelta(days=offset)
        key = day_value.isoformat()
        hours = logs_by_day.get(key, 0.0) + session_hours_without_course.get(key, 0.0)
        heatmap.append({"date": key, "hours": round(hours, 2), "sessions": sessions_by_day.get(key, 0),
                        "level": 0 if hours <= 0 else 1 if hours < 1 else 2 if hours < 2 else 3 if hours < 4 else 4})
    period_hours = round(sum(item["hours"] for item in daily), 2)
    period_sessions = sum(item["sessions"] for item in daily)
    today_key = today.isoformat()
    today_hours = round(logs_by_day.get(today_key, 0.0) + session_hours_without_course.get(today_key, 0.0), 2)
    prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
    goal_hours = float(prefs.daily_goal_hours if prefs else 3.5)
    goal_days_30 = 0
    for offset in range(30):
        day_value = today - timedelta(days=offset)
        key = day_value.isoformat()
        hours = logs_by_day.get(key, 0.0) + session_hours_without_course.get(key, 0.0)
        if hours >= goal_hours:
            goal_days_30 += 1
    current_streak, longest_streak = _calculate_streaks(active_dates, today)
    peak_hour = max(range(24), key=lambda hour: hour_counts[hour]) if sum(hour_counts) else None
    peak_focus_label = f"{peak_hour:02d}:00–{(peak_hour + 1) % 24:02d}:00" if peak_hour is not None else None
    subject_rows = db.execute(select(Subject.name, func.coalesce(func.sum(StudyLog.hours), 0))
        .join(StudyLog, StudyLog.subject_id == Subject.id)
        .where(StudyLog.user_id == user_id, StudyLog.log_date >= start_day.isoformat(), StudyLog.log_date <= today.isoformat())
        .group_by(Subject.id, Subject.name).order_by(func.sum(StudyLog.hours).desc()).limit(6)).all()
    subject_breakdown = [{"name": name, "hours": round(float(hours or 0), 2)} for name, hours in subject_rows]
    quiz_count = db.scalar(select(func.count(QuizAttempt.id)).where(QuizAttempt.user_id == user_id)) or 0
    lifetime_log_hours = sum(float(log.hours or 0) for log in all_logs)
    lifetime_unlinked_session_hours = sum(s.duration_minutes / 60.0 for s in all_sessions if s.subject_id is None)
    lifetime_hours = round(lifetime_log_hours + lifetime_unlinked_session_hours, 2)
    lifetime_sessions = len(all_sessions)
    metrics = {"lifetime_sessions": lifetime_sessions, "lifetime_hours": lifetime_hours,
               "quiz_count": int(quiz_count), "goal_days_30": goal_days_30,
               "current_streak": current_streak, "longest_streak": longest_streak}
    achievements = _sync_achievements(db, user_id, metrics)
    insights = []
    if peak_focus_label:
        insights.append(f"Your most recorded focus start time is around {peak_focus_label}.")
    if period_hours > 0:
        insights.append(f"You studied {period_hours:.1f} hours across the selected {days}-day period, averaging {period_hours / days:.1f} hours per day.")
    if subject_breakdown:
        insights.append(f"{subject_breakdown[0]['name']} received the most logged study time in this period.")
    if current_streak:
        insights.append(f"Your current study streak is {current_streak} day{'s' if current_streak != 1 else ''}. Keep the routine realistic and sustainable.")
    else:
        insights.append("A short focused session today is a simple way to restart your study rhythm.")
    if today_hours >= goal_hours:
        insights.append("You have reached today's study-hour goal. Consider stopping on time and protecting your rest.")
    else:
        remaining = max(0, goal_hours - today_hours)
        insights.append(f"You are {remaining:.1f} hours away from today's study goal.")
    return {"period_days": days, "daily": daily, "heatmap": heatmap,
            "stats": {"today_hours": today_hours, "daily_goal_hours": goal_hours,
                      "goal_progress_percent": min(100, round(today_hours / goal_hours * 100)) if goal_hours else 0,
                      "period_hours": period_hours, "period_sessions": period_sessions,
                      "average_daily_hours": round(period_hours / days, 2),
                      "current_streak": current_streak, "longest_streak": longest_streak,
                      "goal_days_30": goal_days_30, "goal_consistency_percent": round(goal_days_30 / 30 * 100),
                      "peak_focus_hour": peak_focus_label, "lifetime_hours": lifetime_hours,
                      "lifetime_sessions": lifetime_sessions, "quiz_count": int(quiz_count)},
            "subjects": subject_breakdown, "hourly_focus": [{"hour": f"{h:02d}:00", "sessions": hour_counts[h]} for h in range(24)],
            "insights": insights, "achievements": achievements}

def _serialize_notification(item: Notification) -> dict:
    return {"id": item.id, "kind": item.kind, "title": item.title, "message": item.message,
            "action_url": item.action_url, "is_read": item.read_at is not None,
            "created_at": item.created_at.isoformat() if item.created_at else None}

def _serialize_reminder(item: Reminder) -> dict:
    return {"id": item.id, "title": item.title, "message": item.message,
            "remind_at": item.remind_at.isoformat(timespec="minutes"), "status": item.status,
            "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None}

@app.get("/api/productivity/overview")
@login_required
def productivity_overview():
    try:
        days = int(request.args.get("days", "7"))
        if days not in {7, 30, 90}:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a 7, 30, or 90 day reporting period."}), 400
    user_id = current_user_id()
    with SessionLocal() as db:
        data = _productivity_analytics(db, user_id, days)
        today_hours = float(data["stats"]["today_hours"])
        daily_goal = float(data["stats"]["daily_goal_hours"])
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
        if today_hours >= daily_goal and (not prefs or prefs.notifications_enabled):
            _create_productivity_notification(db, user_id, "goal", "Daily study goal reached",
                f"You reached your {daily_goal:g}-hour study goal today. Take a well-earned break.",
                f"daily-goal:{date.today().isoformat()}", "/productivity")
        db.flush()
        unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.read_at.is_(None), Notification.dismissed_at.is_(None))) or 0
        db.commit()
        data["unread_notifications"] = int(unread)
        return jsonify(data)

@app.get("/api/productivity/notifications")
@login_required
def list_productivity_notifications():
    user_id = current_user_id()
    with SessionLocal() as db:
        _sync_due_item_notifications(db, user_id, date.today())
        db.flush()
        try:
            limit = max(1, min(100, int(request.args.get("limit", "40"))))
        except ValueError:
            limit = 40
        items = db.scalars(select(Notification).where(Notification.user_id == user_id, Notification.dismissed_at.is_(None))
                           .order_by(Notification.created_at.desc()).limit(limit)).all()
        unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.read_at.is_(None), Notification.dismissed_at.is_(None))) or 0
        db.commit()
        return jsonify({"items": [_serialize_notification(item) for item in items], "unread": int(unread)})

@app.patch("/api/productivity/notifications/<int:notification_id>/read")
@login_required
def mark_productivity_notification_read(notification_id: int):
    with SessionLocal() as db:
        item = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user_id(), Notification.dismissed_at.is_(None)))
        if not item:
            return jsonify({"error": "Notification not found."}), 404
        item.read_at = item.read_at or datetime.now()
        db.commit()
        return jsonify({"message": "Notification marked as read."})

@app.post("/api/productivity/notifications/read-all")
@login_required
def mark_all_productivity_notifications_read():
    with SessionLocal() as db:
        items = db.scalars(select(Notification).where(Notification.user_id == current_user_id(), Notification.read_at.is_(None), Notification.dismissed_at.is_(None))).all()
        now = datetime.now()
        for item in items:
            item.read_at = now
        db.commit()
        return jsonify({"message": "All notifications marked as read.", "updated": len(items)})

@app.delete("/api/productivity/notifications/<int:notification_id>")
@login_required
def delete_productivity_notification(notification_id: int):
    with SessionLocal() as db:
        item = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user_id(), Notification.dismissed_at.is_(None)))
        if not item:
            return jsonify({"error": "Notification not found."}), 404
        item.dismissed_at = datetime.now()
        item.read_at = item.read_at or item.dismissed_at
        db.commit()
        return jsonify({"message": "Notification dismissed."})

@app.get("/api/productivity/reminders")
@login_required
def list_productivity_reminders():
    with SessionLocal() as db:
        items = db.scalars(select(Reminder).where(Reminder.user_id == current_user_id(), Reminder.status != "dismissed")
                           .order_by(Reminder.remind_at.asc()).limit(100)).all()
        return jsonify([_serialize_reminder(item) for item in items])

@app.post("/api/productivity/reminders")
@login_required
def create_productivity_reminder():
    data = json_body()
    title = str(data.get("title", "")).strip()
    message = str(data.get("message", "")).strip()
    try:
        remind_at = parse_datetime(data.get("remind_at", ""))
        if not title or len(title) > 180 or len(message) > 600:
            raise ValueError
        if remind_at < datetime.now() - timedelta(minutes=1) or remind_at > datetime.now() + timedelta(days=365):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a title and a reminder time between now and one year from now. Message must be 600 characters or fewer."}), 400
    with SessionLocal() as db:
        item = Reminder(user_id=current_user_id(), title=title, message=message, remind_at=remind_at)
        db.add(item)
        db.commit()
        return jsonify({"message": "Reminder created.", "reminder": _serialize_reminder(item)}), 201

@app.get("/api/productivity/reminders/due")
@login_required
def deliver_due_productivity_reminders():
    user_id = current_user_id()
    now = datetime.now()
    with SessionLocal() as db:
        due_items = db.scalars(select(Reminder).where(Reminder.user_id == user_id, Reminder.status == "pending", Reminder.remind_at <= now)
                               .order_by(Reminder.remind_at.asc()).limit(20)).all()
        prefs = db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
        notifications_enabled = prefs.notifications_enabled if prefs else True
        delivered = []
        for item in due_items:
            item.status = "delivered"
            item.delivered_at = now
            delivered.append(_serialize_reminder(item))
            if notifications_enabled:
                _create_productivity_notification(db, user_id, "reminder", item.title, item.message or "Your reminder is due.",
                                                   f"reminder:{item.id}", "/productivity")
        db.commit()
        return jsonify({"due": delivered, "notifications_enabled": notifications_enabled})

@app.patch("/api/productivity/reminders/<int:reminder_id>")
@login_required
def update_productivity_reminder(reminder_id: int):
    data = json_body()
    status = str(data.get("status", "")).strip()
    if status not in {"pending", "dismissed"}:
        return jsonify({"error": "Reminder status must be pending or dismissed."}), 400
    with SessionLocal() as db:
        item = db.scalar(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == current_user_id()))
        if not item:
            return jsonify({"error": "Reminder not found."}), 404
        item.status = status
        if status == "pending":
            item.delivered_at = None
        db.commit()
        return jsonify({"message": "Reminder updated.", "reminder": _serialize_reminder(item)})

@app.delete("/api/productivity/reminders/<int:reminder_id>")
@login_required
def delete_productivity_reminder(reminder_id: int):
    with SessionLocal() as db:
        item = db.scalar(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == current_user_id()))
        if not item:
            return jsonify({"error": "Reminder not found."}), 404
        db.delete(item)
        db.commit()
        return jsonify({"message": "Reminder deleted."})

# ---------------------------------------------------------------------------
# Phase 4: Calendar export and study groups
# ---------------------------------------------------------------------------
def _ics_escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\r\n", "\\n").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _group_member(db, group_id: int, user_id: int):
    return db.scalar(select(StudyGroupMember).where(
        StudyGroupMember.group_id == group_id, StudyGroupMember.user_id == user_id
    ))


def _serialize_group(group: StudyGroup, role: str, member_count: int) -> dict:
    return {
        "id": group.id, "name": group.name, "description": group.description or "",
        "invite_code": group.invite_code, "role": role, "member_count": member_count,
        "created_at": group.created_at.isoformat(),
    }


@app.get("/api/calendar/export")
@login_required
def export_calendar_ics():
    """Export the signed-in user's scheduled blocks as a standards-based iCalendar file.

    Times are stored as local wall-clock values. The requested IANA timezone is
    applied before UTC serialization so imported events retain their intended time.
    """
    today = date.today()
    try:
        start_day = date.fromisoformat(request.args.get("start", today.isoformat()))
        end_day = date.fromisoformat(request.args.get("end", (today + timedelta(days=90)).isoformat()))
    except ValueError:
        return jsonify({"error": "Calendar export dates must use YYYY-MM-DD."}), 400
    if end_day < start_day:
        return jsonify({"error": "Calendar export end date must be on or after the start date."}), 400
    if (end_day - start_day).days > 366:
        return jsonify({"error": "Export a maximum of 366 days at a time."}), 400
    tz_name = request.args.get("timezone") or os.getenv("AURA_DEFAULT_TIMEZONE", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return jsonify({"error": "Choose a valid IANA timezone, for example Asia/Kolkata."}), 400

    start_dt = datetime.combine(start_day, datetime.min.time())
    end_dt = datetime.combine(end_day + timedelta(days=1), datetime.min.time())
    with SessionLocal() as db:
        events = db.scalars(select(ScheduleEvent).where(
            ScheduleEvent.user_id == current_user_id(),
            ScheduleEvent.start_time >= start_dt,
            ScheduleEvent.start_time < end_dt,
        ).order_by(ScheduleEvent.start_time)).all()
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AURA Study//Schedule Export//EN",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-TIMEZONE:{_ics_escape(tz_name)}",
        ]
        for event in events:
            local_start = event.start_time.replace(tzinfo=tz)
            local_end = event.end_time.replace(tzinfo=tz)
            utc_start = local_start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            utc_end = local_end.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:aura-{event.id}-{current_user_id()}@aura-study",
                f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{utc_start}", f"DTEND:{utc_end}",
                f"SUMMARY:{_ics_escape(event.title)}",
                f"DESCRIPTION:{_ics_escape('AURA Study · ' + (event.event_type or 'study').title())}",
                "CLASS:PRIVATE", "END:VEVENT",
            ])
        lines.append("END:VCALENDAR")
    payload = "\r\n".join(lines) + "\r\n"
    response = send_file(
        BytesIO(payload.encode("utf-8")), mimetype="text/calendar; charset=utf-8",
        as_attachment=True, download_name=f"aura-study-{start_day.isoformat()}-to-{end_day.isoformat()}.ics",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.get("/api/groups")
@login_required
def list_study_groups():
    user_id = current_user_id()
    with SessionLocal() as db:
        rows = db.execute(select(StudyGroup, StudyGroupMember).join(
            StudyGroupMember, StudyGroupMember.group_id == StudyGroup.id
        ).where(StudyGroupMember.user_id == user_id).order_by(StudyGroup.created_at.desc())).all()
        result = []
        for group, membership in rows:
            count = db.scalar(select(func.count(StudyGroupMember.id)).where(StudyGroupMember.group_id == group.id)) or 0
            result.append(_serialize_group(group, membership.role, count))
        return jsonify(result)


@app.post("/api/groups")
@login_required
def create_study_group():
    data = json_body()
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    if not name or len(name) > 120:
        return jsonify({"error": "Group name must be between 1 and 120 characters."}), 400
    if len(description) > 500:
        return jsonify({"error": "Group description must be 500 characters or fewer."}), 400
    user_id = current_user_id()
    with SessionLocal() as db:
        invite_code = secrets.token_urlsafe(9).replace("-", "A").replace("_", "B")[:12].upper()
        while db.scalar(select(StudyGroup.id).where(StudyGroup.invite_code == invite_code)):
            invite_code = secrets.token_urlsafe(9).replace("-", "A").replace("_", "B")[:12].upper()
        group = StudyGroup(owner_id=user_id, name=name, description=description, invite_code=invite_code)
        db.add(group)
        db.flush()
        db.add(StudyGroupMember(group_id=group.id, user_id=user_id, role="owner"))
        db.commit()
        db.refresh(group)
        return jsonify({"group": _serialize_group(group, "owner", 1)}), 201


@app.post("/api/groups/join")
@login_required
def join_study_group():
    code = str(json_body().get("invite_code", "")).strip().upper()
    if not code or len(code) > 24:
        return jsonify({"error": "Enter a valid group invite code."}), 400
    user_id = current_user_id()
    with SessionLocal() as db:
        group = db.scalar(select(StudyGroup).where(StudyGroup.invite_code == code))
        if not group:
            return jsonify({"error": "No study group matches that invite code."}), 404
        existing = _group_member(db, group.id, user_id)
        if existing:
            count = db.scalar(select(func.count(StudyGroupMember.id)).where(StudyGroupMember.group_id == group.id)) or 0
            return jsonify({"group": _serialize_group(group, existing.role, count), "already_member": True}), 200
        db.add(StudyGroupMember(group_id=group.id, user_id=user_id, role="member"))
        db.commit()
        count = db.scalar(select(func.count(StudyGroupMember.id)).where(StudyGroupMember.group_id == group.id)) or 0
        return jsonify({"group": _serialize_group(group, "member", count)}), 201


@app.get("/api/groups/<int:group_id>")
@login_required
def get_study_group(group_id: int):
    user_id = current_user_id()
    with SessionLocal() as db:
        group = db.get(StudyGroup, group_id)
        membership = _group_member(db, group_id, user_id) if group else None
        if not group or not membership:
            return jsonify({"error": "Study group not found."}), 404
        member_rows = db.execute(select(StudyGroupMember, User.username).join(
            User, User.id == StudyGroupMember.user_id
        ).where(StudyGroupMember.group_id == group_id).order_by(StudyGroupMember.joined_at)).all()
        members = [{"user_id": m.user_id, "username": username, "role": m.role, "joined_at": m.joined_at.isoformat()}
                   for m, username in member_rows]
        post_rows = db.execute(select(StudyGroupPost, User.username).join(
            User, User.id == StudyGroupPost.user_id
        ).where(StudyGroupPost.group_id == group_id).order_by(StudyGroupPost.created_at.desc()).limit(100)).all()
        posts = []
        for post, username in post_rows:
            shared = db.get(Resource, post.resource_id) if post.resource_id else None
            posts.append({
                "id": post.id, "body": post.body, "username": username, "user_id": post.user_id,
                "created_at": post.created_at.isoformat(), "is_author": post.user_id == user_id,
                "is_owner": group.owner_id == user_id,
                "resource": ({
                    "id": shared.id, "title": shared.title, "resource_type": shared.resource_type,
                    "download_url": f"/api/groups/{group_id}/resources/{shared.id}/download" if shared.stored_filename else None,
                    "url": shared.url if not shared.stored_filename else None,
                } if shared else None),
            })
        count = len(members)
        return jsonify({"group": _serialize_group(group, membership.role, count), "members": members, "posts": posts})


@app.post("/api/groups/<int:group_id>/posts")
@login_required
def create_study_group_post(group_id: int):
    data = json_body()
    body = str(data.get("body", "")).strip()
    resource_value = data.get("resource_id")
    if len(body) > 3000:
        return jsonify({"error": "Group messages must be 3,000 characters or fewer."}), 400
    user_id = current_user_id()
    with SessionLocal() as db:
        if not _group_member(db, group_id, user_id):
            return jsonify({"error": "Study group not found."}), 404
        resource_id = None
        if resource_value not in (None, ""):
            try:
                resource_id = int(resource_value)
            except (TypeError, ValueError):
                return jsonify({"error": "Choose a valid resource to share."}), 400
            if not db.scalar(select(Resource.id).where(Resource.id == resource_id, Resource.user_id == user_id)):
                return jsonify({"error": "You can only share resources from your own Resource Bank."}), 404
        if not body and not resource_id:
            return jsonify({"error": "Write a message or choose a resource to share."}), 400
        post = StudyGroupPost(group_id=group_id, user_id=user_id, body=body, resource_id=resource_id)
        db.add(post)
        db.commit()
        return jsonify({"message": "Group update shared.", "post_id": post.id}), 201


@app.delete("/api/groups/<int:group_id>/posts/<int:post_id>")
@login_required
def delete_study_group_post(group_id: int, post_id: int):
    user_id = current_user_id()
    with SessionLocal() as db:
        if not _group_member(db, group_id, user_id):
            return jsonify({"error": "Study group not found."}), 404
        post = db.scalar(select(StudyGroupPost).where(
            StudyGroupPost.id == post_id, StudyGroupPost.group_id == group_id
        ))
        if not post:
            return jsonify({"error": "Group update not found."}), 404
        group = db.get(StudyGroup, group_id)
        if post.user_id != user_id and group.owner_id != user_id:
            return jsonify({"error": "Only the author or group owner can remove this update."}), 403
        db.delete(post)
        db.commit()
        return jsonify({"message": "Group update removed."})


@app.delete("/api/groups/<int:group_id>/members/me")
@login_required
def leave_study_group(group_id: int):
    user_id = current_user_id()
    with SessionLocal() as db:
        group = db.get(StudyGroup, group_id)
        membership = _group_member(db, group_id, user_id) if group else None
        if not group or not membership:
            return jsonify({"error": "Study group not found."}), 404
        if group.owner_id == user_id:
            return jsonify({"error": "The group owner must delete the group or transfer ownership before leaving."}), 409
        db.delete(membership)
        db.commit()
        return jsonify({"message": "You left the study group."})


@app.delete("/api/groups/<int:group_id>")
@login_required
def delete_study_group(group_id: int):
    user_id = current_user_id()
    with SessionLocal() as db:
        group = db.get(StudyGroup, group_id)
        if not group or group.owner_id != user_id:
            return jsonify({"error": "Only the group owner can delete this study group."}), 404
        db.delete(group)
        db.commit()
        return jsonify({"message": "Study group deleted."})


@app.get("/api/groups/<int:group_id>/resources/<int:resource_id>/download")
@login_required
def download_group_resource(group_id: int, resource_id: int):
    user_id = current_user_id()
    with SessionLocal() as db:
        if not _group_member(db, group_id, user_id):
            return jsonify({"error": "Study group not found."}), 404
        shared = db.scalar(select(StudyGroupPost.id).where(
            StudyGroupPost.group_id == group_id, StudyGroupPost.resource_id == resource_id
        ))
        resource = db.get(Resource, resource_id) if shared else None
        if not resource or not resource.stored_filename:
            return jsonify({"error": "Shared file not found."}), 404
        stored, original = resource.stored_filename, resource.original_filename or resource.stored_filename
    response = send_from_directory(UPLOAD_DIR, stored, as_attachment=True, download_name=original)
    response.headers["Cache-Control"] = "private, no-store"
    return response


# ---------------------------------------------------------------------------
# Resource Bank
# ---------------------------------------------------------------------------
RESOURCE_CATEGORIES = {"notes", "lecture", "textbook", "assignment", "research", "reference", "other"}
INLINE_PREVIEW_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}


def serialize_resource(resource: Resource) -> dict:
    extension = resource.resource_type.lower()
    has_file = bool(resource.stored_filename)
    return {
        "id": resource.id, "title": resource.title, "resource_type": resource.resource_type,
        "url": resource.url, "original_filename": resource.original_filename,
        "project_id": resource.project_id, "description": resource.description or "",
        "category": resource.category or "other", "mime_type": resource.mime_type,
        "file_size": resource.file_size or 0, "created_at": resource.created_at.isoformat(),
        "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
        "download_url": f"/api/resources/{resource.id}/download" if has_file else None,
        "preview_url": f"/api/resources/{resource.id}/preview" if has_file and extension in INLINE_PREVIEW_EXTENSIONS else None,
    }


@app.get("/api/resources")
@login_required
def get_resources():
    with SessionLocal() as db:
        resources = db.scalars(select(Resource).where(Resource.user_id == current_user_id()).order_by(Resource.created_at.desc())).all()
        return jsonify([serialize_resource(resource) for resource in resources])


@app.post("/api/resources")
@login_required
def create_resource():
    user_id = current_user_id()
    form_data = request.form if not request.is_json else json_body()
    title = str(form_data.get("title", "") or "").strip()
    description = str(form_data.get("description", "") or "").strip()
    category = str(form_data.get("category", "other") or "other").strip().lower()
    project_id_value = form_data.get("project_id")
    upload = request.files.get("file")
    url = str(form_data.get("url", "") or "").strip()
    if len(description) > 2000:
        return jsonify({"error": "Resource description must be 2,000 characters or fewer."}), 400
    if category not in RESOURCE_CATEGORIES:
        return jsonify({"error": "Choose a valid resource category."}), 400
    stored = None
    original = None
    resource_type = "link"
    mime_type = None
    file_size = 0
    if upload and upload.filename:
        original = secure_filename(upload.filename)
        extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        if not original or extension not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "File type not supported. Upload PDF, Office documents, text, or image files."}), 400
        stored = f"{user_id}_{uuid.uuid4().hex}_{original}"
        upload_path = UPLOAD_DIR / stored
        upload.save(upload_path)
        file_size = upload_path.stat().st_size
        if file_size <= 0:
            upload_path.unlink(missing_ok=True)
            return jsonify({"error": "The selected file is empty."}), 400
        mime_type = upload.mimetype or mimetypes.guess_type(original)[0] or "application/octet-stream"
        resource_type = extension
        url = ""
    elif url:
        if not url.startswith(("https://", "http://")):
            return jsonify({"error": "Resource links must start with http:// or https://."}), 400
    else:
        return jsonify({"error": "Provide a file or a valid web link."}), 400
    if not title:
        title = original or url
    if len(title) > 180:
        if stored: (UPLOAD_DIR / stored).unlink(missing_ok=True)
        return jsonify({"error": "Resource title must be 180 characters or fewer."}), 400
    try:
        project_id = int(project_id_value) if project_id_value else None
    except (TypeError, ValueError):
        if stored: (UPLOAD_DIR / stored).unlink(missing_ok=True)
        return jsonify({"error": "Project ID must be valid."}), 400
    with SessionLocal() as db:
        if project_id and not get_owned_project(db, project_id, user_id):
            if stored: (UPLOAD_DIR / stored).unlink(missing_ok=True)
            return jsonify({"error": "Project not found."}), 404
        resource = Resource(
            user_id=user_id, project_id=project_id, title=title, resource_type=resource_type,
            url=url or None, original_filename=original, stored_filename=stored,
            description=description, category=category, mime_type=mime_type, file_size=file_size,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
        return jsonify({"message": "Resource saved.", "resource": serialize_resource(resource)}), 201


@app.patch("/api/resources/<int:resource_id>")
@login_required
def update_resource(resource_id: int):
    data = json_body()
    user_id = current_user_id()
    with SessionLocal() as db:
        resource = db.scalar(select(Resource).where(Resource.id == resource_id, Resource.user_id == user_id))
        if not resource:
            return jsonify({"error": "Resource not found."}), 404
        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title or len(title) > 180:
                return jsonify({"error": "Resource title must be between 1 and 180 characters."}), 400
            resource.title = title
        if "description" in data:
            description = str(data.get("description") or "").strip()
            if len(description) > 2000:
                return jsonify({"error": "Resource description must be 2,000 characters or fewer."}), 400
            resource.description = description
        if "category" in data:
            category = str(data.get("category") or "other").strip().lower()
            if category not in RESOURCE_CATEGORIES:
                return jsonify({"error": "Choose a valid resource category."}), 400
            resource.category = category
        if "project_id" in data:
            try:
                project_id = int(data["project_id"]) if data.get("project_id") else None
            except (TypeError, ValueError):
                return jsonify({"error": "Project ID must be valid."}), 400
            if project_id and not get_owned_project(db, project_id, user_id):
                return jsonify({"error": "Project not found."}), 404
            resource.project_id = project_id
        resource.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(resource)
        return jsonify({"message": "Resource updated.", "resource": serialize_resource(resource)})


@app.get("/api/resources/<int:resource_id>/preview")
@login_required
def preview_resource(resource_id: int):
    with SessionLocal() as db:
        resource = db.scalar(select(Resource).where(Resource.id == resource_id, Resource.user_id == current_user_id()))
        if not resource or not resource.stored_filename:
            return jsonify({"error": "File not found."}), 404
        extension = resource.resource_type.lower()
        if extension not in INLINE_PREVIEW_EXTENSIONS:
            return jsonify({"error": "This file type must be downloaded to open it."}), 415
        stored = resource.stored_filename
        filename = resource.original_filename or stored
        mime_type = resource.mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = send_from_directory(UPLOAD_DIR, stored, as_attachment=False, download_name=filename, mimetype=mime_type)
    response.headers["Content-Disposition"] = f'inline; filename="{secure_filename(filename)}"'
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # The global app policy denies framing; this route is a same-origin preview
    # inside the authenticated Resource Bank, so allow only that exact use.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    return response


@app.get("/api/resources/<int:resource_id>/download")
@login_required
def download_resource(resource_id: int):
    with SessionLocal() as db:
        resource = db.scalar(select(Resource).where(Resource.id == resource_id, Resource.user_id == current_user_id()))
        if not resource or not resource.stored_filename:
            return jsonify({"error": "File not found."}), 404
        filename = resource.original_filename or resource.stored_filename
        stored = resource.stored_filename
    response = send_from_directory(UPLOAD_DIR, stored, as_attachment=True, download_name=filename)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.delete("/api/resources/<int:resource_id>")
@login_required
def delete_resource(resource_id: int):
    with SessionLocal() as db:
        resource = db.scalar(select(Resource).where(Resource.id == resource_id, Resource.user_id == current_user_id()))
        if not resource:
            return jsonify({"error": "Resource not found."}), 404
        stored = resource.stored_filename
        db.delete(resource)
        db.commit()
        if stored:
            (UPLOAD_DIR / stored).unlink(missing_ok=True)
        return jsonify({"message": "Resource deleted."})


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "The requested API endpoint or resource was not found."}), 404
    return error


@app.errorhandler(429)
def too_many_requests(_error):
    response = jsonify({"error": "Too many requests. Please wait before trying again."})
    response.status_code = 429
    response.headers.setdefault("Retry-After", "60")
    return response


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": "File is too large. The maximum upload size is 10 MB."}), 413


@app.errorhandler(SQLAlchemyError)
def database_error(error):
    app.logger.exception("Database operation failed: %s", error)
    return jsonify({"error": "A database error occurred. Check the server log for details."}), 500


@app.errorhandler(500)
def internal_error(_error):
    return jsonify({"error": "An unexpected server error occurred. Check the backend terminal for details."}), 500


if __name__ == "__main__":
    # Development server only. Use Waitress (Windows) or Gunicorn (Linux) in production.
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")),
            debug=(not is_production and os.getenv("FLASK_DEBUG", "false").lower() == "true"))

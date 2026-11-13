"""Basic API smoke tests. Run with: pytest backend/tests -q
The test database is isolated from the user's local study_planner.db.
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_aura.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-only-secret-key-that-is-definitely-at-least-32-bytes-long")
    # Import after DATABASE_URL is set so SQLAlchemy uses the isolated test file.
    import app as aura_app
    from database import Base, engine, init_db
    Base.metadata.drop_all(bind=engine)
    init_db()
    aura_app.app.config.update(TESTING=True)
    with aura_app.app.test_client() as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def csrf(response):
    return response.get_json()["csrf_token"]


def test_register_and_create_course(client):
    registered = client.post("/api/register", json={
        "username": "student01", "email": "student@example.com", "password": "strong-pass-123",
    })
    assert registered.status_code == 201
    token = csrf(registered)
    created = client.post("/api/subjects", headers={"X-CSRF-Token": token}, json={
        "name": "Operating Systems", "exam_date": "2027-01-15", "difficulty": 4, "target_hours": 20,
    })
    assert created.status_code == 201
    subjects = client.get("/api/subjects").get_json()
    assert len(subjects) == 1
    assert subjects[0]["name"] == "Operating Systems"


def test_schedule_rejects_overlapping_events(client):
    registered = client.post("/api/register", json={
        "username": "student02", "email": "student2@example.com", "password": "strong-pass-123",
    })
    token = csrf(registered)
    headers = {"X-CSRF-Token": token}
    first = client.post("/api/schedule", headers=headers, json={
        "title": "Research", "start_time": "2027-01-15T10:00", "end_time": "2027-01-15T11:00",
    })
    assert first.status_code == 201
    overlap = client.post("/api/schedule", headers=headers, json={
        "title": "Revision", "start_time": "2027-01-15T10:30", "end_time": "2027-01-15T11:30",
    })
    assert overlap.status_code == 409


def test_timer_log_is_idempotent(client):
    registered = client.post("/api/register", json={
        "username": "student03", "email": "student3@example.com", "password": "strong-pass-123",
    })
    token = csrf(registered)
    body = {"session_key": "test-session-1", "duration_minutes": 25, "started_at": "2027-01-15T10:00"}
    first = client.post("/api/timer/log", headers={"X-CSRF-Token": token}, json=body)
    second = client.post("/api/timer/log", headers={"X-CSRF-Token": token}, json=body)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["duplicate"] is True


def test_manual_hours_update_course_progress(client):
    registered = client.post("/api/register", json={
        "username": "student04", "email": "student4@example.com", "password": "strong-pass-123",
    })
    token = csrf(registered)
    headers = {"X-CSRF-Token": token}
    created = client.post("/api/subjects", headers=headers, json={
        "name": "Databases", "exam_date": "2027-02-01", "difficulty": 3, "target_hours": 10,
    })
    subject_id = created.get_json()["subject"]["id"]
    logged = client.post("/api/log-hours", headers=headers, json={
        "subject_id": subject_id, "hours": 1.5, "log_date": "2026-11-12",
    })
    assert logged.status_code == 200
    assert logged.get_json()["completed_hours"] == 1.5


def test_session_key_is_scoped_to_each_user(client):
    first = client.post("/api/register", json={
        "username": "student05", "email": "student5@example.com", "password": "strong-pass-123",
    })
    first_token = csrf(first)
    first_result = client.post("/api/timer/log", headers={"X-CSRF-Token": first_token}, json={
        "session_key": "shared-test-key", "duration_minutes": 25, "started_at": "2026-11-12T10:00",
    })
    assert first_result.status_code == 201

    client.post("/api/logout", headers={"X-CSRF-Token": first_token})
    second = client.post("/api/register", json={
        "username": "student06", "email": "student6@example.com", "password": "strong-pass-123",
    })
    second_token = csrf(second)
    second_result = client.post("/api/timer/log", headers={"X-CSRF-Token": second_token}, json={
        "session_key": "shared-test-key", "duration_minutes": 25, "started_at": "2026-11-12T10:00",
    })
    assert second_result.status_code == 201


def test_invalid_schedule_date_returns_400(client):
    registered = client.post("/api/register", json={
        "username": "student07", "email": "student7@example.com", "password": "strong-pass-123",
    })
    response = client.get("/api/dashboard?date=not-a-date")
    assert response.status_code == 400


def test_course_can_be_updated(client):
    registered = client.post("/api/register", json={
        "username": "courseedit", "email": "courseedit@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    created = client.post("/api/subjects", headers=headers, json={
        "name": "Networks", "exam_date": "2027-02-01", "difficulty": 2, "target_hours": 12,
    })
    subject_id = created.get_json()["subject"]["id"]
    updated = client.patch(f"/api/subjects/{subject_id}", headers=headers, json={
        "name": "Computer Networks", "exam_date": "2027-02-15", "difficulty": 4, "target_hours": 18,
    })
    assert updated.status_code == 200
    assert updated.get_json()["subject"]["name"] == "Computer Networks"
    assert updated.get_json()["subject"]["target_hours"] == 18


def test_task_edit_supports_due_date_and_rejects_invalid_dates(client):
    registered = client.post("/api/register", json={
        "username": "taskedit", "email": "taskedit@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    project = client.post("/api/projects", headers=headers, json={"title": "Thesis"}).get_json()["project"]
    task = client.post(f"/api/projects/{project['id']}/tasks", headers=headers, json={"title": "Read papers"}).get_json()["task"]
    changed = client.patch(f"/api/tasks/{task['id']}", headers=headers, json={
        "title": "Review research papers", "due_date": "2027-01-20",
    })
    assert changed.status_code == 200
    assert changed.get_json()["task"]["due_date"] == "2027-01-20"
    invalid = client.patch(f"/api/tasks/{task['id']}", headers=headers, json={"due_date": "not-a-date"})
    assert invalid.status_code == 400


def test_schedule_event_can_be_edited_without_conflicting_with_itself(client):
    registered = client.post("/api/register", json={
        "username": "scheduleedit", "email": "scheduleedit@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    created = client.post("/api/schedule", headers=headers, json={
        "title": "Study", "start_time": "2027-01-15T10:00", "end_time": "2027-01-15T11:00",
    }).get_json()["event"]
    updated = client.patch(f"/api/schedule/{created['id']}", headers=headers, json={
        "title": "Deep work", "start_time": "2027-01-15T11:00", "end_time": "2027-01-15T12:15",
        "event_type": "study",
    })
    assert updated.status_code == 200
    assert updated.get_json()["event"]["title"] == "Deep work"


def test_settings_update_includes_focus_window_theme_and_reminders(client):
    registered = client.post("/api/register", json={
        "username": "settingsuser", "email": "settings@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    updated = client.put("/api/preferences", headers=headers, json={
        "pomodoro_minutes": 40, "short_break_minutes": 7, "long_break_minutes": 20,
        "daily_goal_hours": 4.5, "peak_focus_hours": "10:00-13:30",
        "theme": "night", "notifications_enabled": False,
    })
    assert updated.status_code == 200
    body = updated.get_json()
    assert body["pomodoro_minutes"] == 40
    assert body["peak_focus_hours"] == "10:00-13:30"
    assert body["theme"] == "night"
    assert body["notifications_enabled"] is False
    invalid = client.put("/api/preferences", headers=headers, json={"peak_focus_hours": "15:00-10:00"})
    assert invalid.status_code == 400


def test_profile_can_be_updated_and_email_is_normalized(client):
    registered = client.post("/api/register", json={
        "username": "profileuser", "email": "profile@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    updated = client.patch("/api/profile", headers=headers, json={
        "username": "profile_student", "email": "PROFILE.STUDENT@example.com",
    })
    assert updated.status_code == 200
    assert updated.get_json()["user"]["username"] == "profile_student"
    assert updated.get_json()["user"]["email"] == "profile.student@example.com"



def test_learning_quiz_can_be_generated_and_submitted_from_term_definition_notes(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    registered = client.post("/api/register", json={
        "username": "quizstudent", "email": "quizstudent@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    created_course = client.post("/api/subjects", headers=headers, json={
        "name": "Biology", "exam_date": "2027-01-15", "difficulty": 3, "target_hours": 12,
    }).get_json()["subject"]
    generated = client.post("/api/learning/quizzes/generate", headers=headers, json={
        "topic": "Cell biology", "subject_id": created_course["id"], "count": 3,
        "notes": "Osmosis: Movement of water across a selectively permeable membrane.\n"
                 "Mitosis: Cell division that produces two genetically identical daughter cells.\n"
                 "Chloroplast: An organelle where photosynthesis takes place.",
    })
    assert generated.status_code == 201
    quiz = generated.get_json()["quiz"]
    assert len(quiz["questions"]) == 3
    assert "answer_index" not in quiz["questions"][0]
    submitted = client.post(f"/api/learning/quizzes/{quiz['id']}/attempts", headers=headers, json={"answers": [0, 0, 0]})
    assert submitted.status_code == 201
    assert submitted.get_json()["total"] == 3


def test_flashcard_spaced_review_and_revision_crud(client):
    registered = client.post("/api/register", json={
        "username": "cardsstudent", "email": "cardsstudent@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    created = client.post("/api/learning/flashcards", headers=headers, json={
        "front": "What is osmosis?", "back": "Movement of water across a selectively permeable membrane.",
    })
    assert created.status_code == 201
    card_id = created.get_json()["flashcard"]["id"]
    reviewed = client.patch(f"/api/learning/flashcards/{card_id}/review", headers=headers, json={"rating": "good"})
    assert reviewed.status_code == 200
    assert reviewed.get_json()["flashcard"]["interval_days"] == 1
    revision = client.post("/api/learning/revisions", headers=headers, json={
        "title": "Review osmosis", "due_date": "2027-01-15", "notes": "Explain it without notes.",
    })
    assert revision.status_code == 201
    revision_id = revision.get_json()["revision"]["id"]
    completed = client.patch(f"/api/learning/revisions/{revision_id}", headers=headers, json={"status": "done"})
    assert completed.status_code == 200
    assert completed.get_json()["revision"]["status"] == "done"


def test_daily_plan_respects_existing_schedule_and_can_be_applied(client):
    from datetime import date, timedelta
    plan_day = date.today() + timedelta(days=2)
    registered = client.post("/api/register", json={
        "username": "planstudent", "email": "planstudent@example.com", "password": "strong-pass-123",
    })
    headers = {"X-CSRF-Token": csrf(registered)}
    course = client.post("/api/subjects", headers=headers, json={
        "name": "Algorithms", "exam_date": (plan_day + timedelta(days=9)).isoformat(),
        "difficulty": 4, "target_hours": 15,
    }).get_json()["subject"]
    block = client.post("/api/schedule", headers=headers, json={
        "title": "Lecture", "start_time": f"{plan_day.isoformat()}T09:00",
        "end_time": f"{plan_day.isoformat()}T10:00",
    })
    assert block.status_code == 201
    plan = client.get(f"/api/learning/daily-plan?date={plan_day.isoformat()}")
    assert plan.status_code == 200
    items = plan.get_json()["items"]
    assert items
    assert all(item["start_time"] >= f"{plan_day.isoformat()}T10:00" for item in items)
    applied = client.post("/api/learning/daily-plan/apply", headers=headers, json={"date": plan_day.isoformat()})
    assert applied.status_code == 201
    assert applied.get_json()["created_count"] == len(items)

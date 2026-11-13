from datetime import date, datetime, timedelta

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_productivity.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "phase3-test-secret-key-that-is-long-enough")
    import app as aura_app
    from database import Base, engine, init_db
    Base.metadata.drop_all(bind=engine)
    init_db()
    aura_app.app.config.update(TESTING=True)
    with aura_app.app.test_client() as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_student(client, username="phase3student"):
    response = client.post("/api/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "strong-pass-123",
    })
    assert response.status_code == 201
    return response.get_json()["csrf_token"]


def test_productivity_analytics_counts_study_without_double_counting(client):
    from database import SessionLocal, StudyLog, StudySession, Subject, User

    token = register_student(client)
    headers = {"X-CSRF-Token": token}
    with SessionLocal() as db:
        user_id = db.scalar(select(User).where(User.username == "phase3student")).id
        subject = Subject(user_id=user_id, name="Biology", exam_date=(date.today() + timedelta(days=20)).isoformat(),
                          difficulty=3, target_hours=10, completed_hours=0)
        db.add(subject)
        db.flush()
        db.add(StudyLog(user_id=user_id, subject_id=subject.id, hours=1.0, log_date=date.today().isoformat()))
        db.add(StudySession(user_id=user_id, subject_id=subject.id, duration_minutes=60,
                            started_at=datetime.now() - timedelta(hours=2), completed_at=datetime.now(), session_key="phase3-course-session"))
        db.add(StudySession(user_id=user_id, subject_id=None, duration_minutes=30,
                            started_at=datetime.now() - timedelta(hours=1), completed_at=datetime.now(), session_key="phase3-unlinked-session"))
        db.commit()
    response = client.get("/api/productivity/overview?days=7")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["stats"]["today_hours"] == 1.5
    assert payload["stats"]["period_sessions"] == 2
    assert payload["stats"]["current_streak"] >= 1
    assert any(item["name"] == "Biology" for item in payload["subjects"])
    assert len(payload["heatmap"]) == 70


def test_productivity_rejects_unsupported_period(client):
    register_student(client)
    response = client.get("/api/productivity/overview?days=14")
    assert response.status_code == 400


def test_exam_and_task_deadline_notifications_are_created_once(client):
    token = register_student(client, "deadline_student")
    headers = {"X-CSRF-Token": token}
    due_exam = (date.today() + timedelta(days=2)).isoformat()
    subject_response = client.post("/api/subjects", headers=headers, json={
        "name": "Operating Systems", "exam_date": due_exam, "difficulty": 4, "target_hours": 12,
    })
    assert subject_response.status_code == 201
    project_response = client.post("/api/projects", headers=headers, json={"title": "Semester project"})
    assert project_response.status_code == 201
    project_id = project_response.get_json()["project"]["id"]
    task_response = client.post(f"/api/projects/{project_id}/tasks", headers=headers, json={
        "title": "Submit research outline", "due_date": (date.today() + timedelta(days=1)).isoformat(),
    })
    assert task_response.status_code == 201
    first = client.get("/api/productivity/notifications").get_json()
    second = client.get("/api/productivity/notifications").get_json()
    kinds = [item["kind"] for item in first["items"]]
    assert "exam" in kinds
    assert "task" in kinds
    assert len(first["items"]) == len(second["items"])


def test_personal_reminder_can_be_created_delivered_and_dismissed(client):
    from database import Reminder, SessionLocal

    token = register_student(client, "reminder_student")
    headers = {"X-CSRF-Token": token}
    remind_at = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="minutes")
    created = client.post("/api/productivity/reminders", headers=headers, json={
        "title": "Review lecture notes", "message": "Revise chapter two", "remind_at": remind_at,
    })
    assert created.status_code == 201
    reminder_id = created.get_json()["reminder"]["id"]
    with SessionLocal() as db:
        reminder = db.scalar(select(Reminder).where(Reminder.id == reminder_id))
        reminder.remind_at = datetime.now() - timedelta(minutes=1)
        db.commit()
    due = client.get("/api/productivity/reminders/due").get_json()
    assert len(due["due"]) == 1
    assert due["due"][0]["id"] == reminder_id
    notifications = client.get("/api/productivity/notifications").get_json()
    assert any(item["kind"] == "reminder" for item in notifications["items"])
    dismissed = client.patch(f"/api/productivity/reminders/{reminder_id}", headers=headers, json={"status": "dismissed"})
    assert dismissed.status_code == 200
    assert all(item["id"] != reminder_id for item in client.get("/api/productivity/reminders").get_json())


def test_notifications_can_be_marked_read_and_are_user_scoped(client):
    from database import Notification, SessionLocal, User

    token = register_student(client, "notify_student_one")
    with SessionLocal() as db:
        user_id = db.scalar(select(User).where(User.username == "notify_student_one")).id
        notification = Notification(user_id=user_id, kind="info", title="Test notification", message="Hello",
                                    dedupe_key="test-notification-one")
        db.add(notification)
        db.commit()
        notification_id = notification.id
    response = client.patch(f"/api/productivity/notifications/{notification_id}/read", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    items = client.get("/api/productivity/notifications").get_json()
    assert items["unread"] == 0
    client.post("/api/logout", headers={"X-CSRF-Token": token})
    second_token = register_student(client, "notify_student_two")
    response = client.patch(f"/api/productivity/notifications/{notification_id}/read", headers={"X-CSRF-Token": second_token})
    assert response.status_code == 404
    response = client.delete(f"/api/productivity/notifications/{notification_id}", headers={"X-CSRF-Token": second_token})
    assert response.status_code == 404


def test_achievements_are_awarded_once_after_first_focus_session(client):
    token = register_student(client, "achievement_student")
    headers = {"X-CSRF-Token": token}
    session_response = client.post("/api/timer/log", headers=headers, json={
        "session_key": "first-phase3-focus", "duration_minutes": 25,
        "started_at": datetime.now().isoformat(timespec="minutes"),
    })
    assert session_response.status_code == 201
    overview = client.get("/api/productivity/overview?days=7").get_json()
    first_focus = next(item for item in overview["achievements"] if item["key"] == "first_focus")
    assert first_focus["unlocked"] is True
    second = client.get("/api/productivity/overview?days=7").get_json()
    assert sum(1 for item in second["achievements"] if item["key"] == "first_focus" and item["unlocked"]) == 1


def test_dismissed_notification_stays_dismissed(client):
    from database import Notification, SessionLocal, User

    token = register_student(client, "dismiss_student")
    with SessionLocal() as db:
        user_id = db.scalar(select(User).where(User.username == "dismiss_student")).id
        notification = Notification(user_id=user_id, kind="exam", title="Exam coming up",
                                    message="Revise Biology", dedupe_key="dismiss-test-key")
        db.add(notification)
        db.commit()
        notification_id = notification.id
    dismissed = client.delete(f"/api/productivity/notifications/{notification_id}", headers={"X-CSRF-Token": token})
    assert dismissed.status_code == 200
    listing = client.get("/api/productivity/notifications").get_json()
    assert all(item["id"] != notification_id for item in listing["items"])
    assert listing["unread"] == 0

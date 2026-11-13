"""Phase 4 tests: study groups, shared resources, resource management, and ICS export."""
from datetime import date, datetime, timedelta
from io import BytesIO
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_aura_phase4.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "phase-four-test-secret-key-at-least-32-bytes")
    import app as aura_app
    from database import Base, engine, init_db
    Base.metadata.drop_all(bind=engine)
    init_db()
    aura_app.app.config.update(TESTING=True)
    with aura_app.app.test_client() as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register(client, username):
    response = client.post("/api/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "strong-pass-123",
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()["csrf_token"]


def test_study_group_create_join_and_member_only_access(client):
    owner_token = register(client, "groupowner")
    owner_headers = {"X-CSRF-Token": owner_token}
    created = client.post("/api/groups", headers=owner_headers, json={
        "name": "Biology Circle", "description": "Weekly revision and note sharing.",
    })
    assert created.status_code == 201
    group = created.get_json()["group"]
    assert group["role"] == "owner"
    assert group["member_count"] == 1
    assert group["invite_code"]

    owner_post = client.post(f"/api/groups/{group['id']}/posts", headers=owner_headers, json={
        "body": "Let's revise cell division this weekend.",
    })
    assert owner_post.status_code == 201
    owner_detail = client.get(f"/api/groups/{group['id']}").get_json()
    assert len(owner_detail["posts"]) == 1
    assert owner_detail["posts"][0]["body"].startswith("Let's revise")

    client.post("/api/logout", headers=owner_headers)
    member_token = register(client, "groupmember")
    member_headers = {"X-CSRF-Token": member_token}
    joined = client.post("/api/groups/join", headers=member_headers, json={"invite_code": group["invite_code"]})
    assert joined.status_code == 201
    assert joined.get_json()["group"]["role"] == "member"
    member_post = client.post(f"/api/groups/{group['id']}/posts", headers=member_headers, json={
        "body": "I will share a summary after revision.",
    })
    assert member_post.status_code == 201
    detail = client.get(f"/api/groups/{group['id']}").get_json()
    assert detail["group"]["member_count"] == 2
    assert {post["username"] for post in detail["posts"]} == {"groupowner", "groupmember"}

    client.post("/api/logout", headers=member_headers)
    register(client, "outsider")
    denied = client.get(f"/api/groups/{group['id']}")
    assert denied.status_code == 404


def test_group_resource_sharing_is_limited_to_member_and_shared_item(client):
    owner_token = register(client, "shareowner")
    owner_headers = {"X-CSRF-Token": owner_token}
    group = client.post("/api/groups", headers=owner_headers, json={"name": "Shared Notes"}).get_json()["group"]
    uploaded = client.post("/api/resources", headers=owner_headers, data={
        "title": "Cell Biology Notes", "category": "notes", "description": "Lecture summary",
        "file": (BytesIO(b"%PDF-1.4\nAURA test document\n%%EOF"), "biology-notes.pdf"),
    }, content_type="multipart/form-data")
    assert uploaded.status_code == 201, uploaded.get_json()
    resource = uploaded.get_json()["resource"]
    assert resource["category"] == "notes"
    assert resource["file_size"] > 0
    assert resource["preview_url"].endswith("/preview")

    shared = client.post(f"/api/groups/{group['id']}/posts", headers=owner_headers, json={
        "body": "Please review this PDF.", "resource_id": resource["id"],
    })
    assert shared.status_code == 201
    link_resource = client.post("/api/resources", headers=owner_headers, json={
        "title": "Open textbook", "url": "https://example.com/textbook", "category": "textbook",
    })
    assert link_resource.status_code == 201
    link_id = link_resource.get_json()["resource"]["id"]
    link_share = client.post(f"/api/groups/{group['id']}/posts", headers=owner_headers, json={
        "body": "Useful online textbook.", "resource_id": link_id,
    })
    assert link_share.status_code == 201
    preview = client.get(resource["preview_url"])
    assert preview.status_code == 200
    assert preview.mimetype == "application/pdf"
    assert preview.headers.get("Content-Disposition", "").startswith("inline;")

    client.post("/api/logout", headers=owner_headers)
    member_token = register(client, "sharemember")
    member_headers = {"X-CSRF-Token": member_token}
    client.post("/api/groups/join", headers=member_headers, json={"invite_code": group["invite_code"]})
    detail = client.get(f"/api/groups/{group['id']}").get_json()
    shared_posts = [post for post in detail["posts"] if post["resource"]]
    shared_post = next(post for post in shared_posts if post["resource"]["download_url"])
    download = client.get(shared_post["resource"]["download_url"])
    assert download.status_code == 200
    assert download.data.startswith(b"%PDF")
    shared_link = next(post for post in shared_posts if post["resource"]["url"])
    assert shared_link["resource"]["url"] == "https://example.com/textbook"


def test_resource_metadata_can_be_updated_and_project_ownership_is_checked(client):
    token = register(client, "resourceeditor")
    headers = {"X-CSRF-Token": token}
    project = client.post("/api/projects", headers=headers, json={"title": "Thesis"}).get_json()["project"]
    created = client.post("/api/resources", headers=headers, json={
        "title": "Reference link", "url": "https://example.com/paper", "category": "research",
        "description": "Initial note", "project_id": project["id"],
    })
    assert created.status_code == 201
    resource_id = created.get_json()["resource"]["id"]
    updated = client.patch(f"/api/resources/{resource_id}", headers=headers, json={
        "title": "Research paper", "description": "Read methods and discussion", "category": "reference",
        "project_id": None,
    })
    assert updated.status_code == 200
    assert updated.get_json()["resource"]["title"] == "Research paper"
    assert updated.get_json()["resource"]["category"] == "reference"
    assert updated.get_json()["resource"]["project_id"] is None


def test_calendar_export_contains_only_users_events_and_validates_range(client):
    token = register(client, "calendaruser")
    headers = {"X-CSRF-Token": token}
    start = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
    event = client.post("/api/schedule", headers=headers, json={
        "title": "Revision, part one", "start_time": start.replace(hour=10).isoformat(timespec="minutes"),
        "end_time": start.replace(hour=11).isoformat(timespec="minutes"),
    })
    assert event.status_code == 201
    export = client.get(f"/api/calendar/export?start={start.date().isoformat()}&end={start.date().isoformat()}&timezone=Asia/Kolkata")
    assert export.status_code == 200
    assert export.mimetype == "text/calendar"
    body = export.data.decode("utf-8")
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:Revision\\, part one" in body
    assert "END:VCALENDAR" in body
    invalid = client.get("/api/calendar/export?start=not-a-date")
    assert invalid.status_code == 400
    invalid_tz = client.get(f"/api/calendar/export?start={start.date().isoformat()}&timezone=Not/A-Timezone")
    assert invalid_tz.status_code == 400


def test_resources_are_not_visible_to_another_user(client):
    owner_token = register(client, "privateowner")
    owner_headers = {"X-CSRF-Token": owner_token}
    created = client.post("/api/resources", headers=owner_headers, json={
        "title": "Private link", "url": "https://example.com/private", "category": "reference",
    })
    resource_id = created.get_json()["resource"]["id"]
    client.post("/api/logout", headers=owner_headers)
    register(client, "privateviewer")
    assert client.get(f"/api/resources/{resource_id}/preview").status_code == 404
    assert client.get(f"/api/resources/{resource_id}/download").status_code == 404

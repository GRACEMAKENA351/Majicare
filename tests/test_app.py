"""
Tests for the MajiCare Flask application.

Covers authentication, report creation, community water-point seeding,
the admin dashboard, and report status updates.
"""
import os
import sys
import tempfile

import pytest

# Ensure the app package is importable when running pytest from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app, create_app, get_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Create a fresh app with an isolated temporary database."""
    db_path = str(tmp_path / "test_majicare.db")

    # Point the module-level app at the isolated database
    flask_app.config["DATABASE"] = db_path

    # Re-run init_db so the isolated DB is created with schema + seed data
    import app as app_module
    app_module.DATABASE = db_path
    with flask_app.app_context():
        flask_app.init_db()

    with flask_app.test_client() as test_client:
        yield test_client


def _register_and_login(client, username="alice", password="strongpass"):
    """Register and log in as a resident, returning the login response."""
    reg = client.post(
        "/register",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert reg.status_code == 302
    login_resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302
    return login_resp


def test_register_and_login_flow(client):
    response = _register_and_login(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_create_app_uses_configured_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "configured-test-secret")

    assert create_app().config["SECRET_KEY"] == "configured-test-secret"


def test_create_app_generates_random_secret_when_unset(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    first_app = create_app()
    second_app = create_app()

    assert len(first_app.config["SECRET_KEY"]) == 64
    assert first_app.config["SECRET_KEY"] != second_app.config["SECRET_KEY"]


def test_admin_route_requires_login_and_admin(client):
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    _register_and_login(client)
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_create_report_flow(client):
    _register_and_login(client)
    response = client.post(
        "/report",
        data={
            "title": "Broken tap",
            "category": "Broken Tap",
            "description": "The tap is dripping.",
            "location": "Main street",
        },
        follow_redirects=True,
    )
    assert b"reported successfully" in response.data
    assert b"Broken tap" in response.data


def test_my_reports_status_filter(client):
    _register_and_login(client)
    client.post(
        "/report",
        data={
            "title": "Pending issue",
            "category": "Water Shortage",
            "description": "No water",
            "location": "Village A",
        },
        follow_redirects=False,
    )
    client.post(
        "/report",
        data={
            "title": "Resolved issue",
            "category": "Water Quality",
            "description": "Water looks dirty",
            "location": "Village B",
        },
        follow_redirects=False,
    )

    with flask_app.app_context():
        get_db().execute(
            "UPDATE reports SET status = 'Resolved' WHERE title = 'Resolved issue'"
        )
        get_db().commit()

    response = client.get("/my-reports?status=Pending", follow_redirects=True)
    assert b"Pending issue" in response.data
    assert b"Resolved issue" not in response.data


def test_create_report_validation_errors(client):
    _register_and_login(client)
    response = client.post(
        "/report",
        data={
            "title": "",
            "category": "",
            "description": "",
            "location": "",
        },
        follow_redirects=True,
    )
    assert b"Complete every field" in response.data


def test_create_report_invalid_category(client):
    _register_and_login(client)
    response = client.post(
        "/report",
        data={
            "title": "Bad category",
            "category": "Not a category",
            "description": "x",
            "location": "y",
        },
        follow_redirects=True,
    )
    assert b"valid category" in response.data


def test_create_report_requires_login(client):
    response = client.post(
        "/report",
        data={
            "title": "Test",
            "category": "Broken Tap",
            "description": "x",
            "location": "y",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def _register_and_login_admin(client, username="admin", password="adminpass123"):
    """Register an admin and log in as them."""
    reg = client.post(
        "/register",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert reg.status_code == 302
    resp = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return resp


def test_admin_dashboard_shows_reports_and_summary(client):
    # Create a resident and a report as a normal user
    _register_and_login(client)
    client.post(
        "/report",
        data={
            "title": "First report",
            "category": "Water Shortage",
            "description": "No water",
            "location": "Village A",
        },
        follow_redirects=False,
    )

    # Log in as admin and view the dashboard
    _register_and_login_admin(client)
    response = client.get("/admin", follow_redirects=True)
    assert response.status_code == 200
    assert b"First report" in response.data
    assert b"Total reports" in response.data
    assert b"Pending" in response.data
    assert b"Resolved" in response.data


def test_admin_can_update_report_status(client):
    _register_and_login_admin(client)
    client.post(
        "/report",
        data={
            "title": "Broken borehole",
            "category": "Broken Borehole",
            "description": "Needs repair",
            "location": "Village B",
        },
        follow_redirects=False,
    )

    with flask_app.app_context():
        report_id = (
            get_db().execute(
                "SELECT id FROM reports WHERE title='Broken borehole'"
            ).fetchone()[0]
        )

    response = client.post(
        f"/admin/report/{report_id}/status",
        data={"status": "Resolved"},
        follow_redirects=True,
    )
    assert b"Report status updated" in response.data

    with flask_app.app_context():
        status = get_db().execute(
            "SELECT status FROM reports WHERE id=?", (report_id,)
        ).fetchone()[0]
        assert status == "Resolved"

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")

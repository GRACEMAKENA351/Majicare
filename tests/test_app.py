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


@pytest.mark.parametrize("path", ["/", "/communities"])
def test_county_filters_list_all_kenyan_counties(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.data.count(b"<option value=") == 48
    assert b'<option value="Baringo County"' in response.data
    assert b'<option value="Nairobi City County"' in response.data
    assert b'<option value="Tharaka-Nithi County"' in response.data


def test_water_point_directory_lists_every_county_and_current_locations(client):
    response = client.get("/water-points")

    assert response.status_code == 200
    assert response.data.count(b'class="county-water-group"') == 47
    assert b"Tharaka-Nithi County" in response.data
    assert b"Demo location (not verified)" in response.data
    assert b"no recorded locations yet" in response.data


def test_admin_can_add_water_point_to_county_directory(client):
    _register_and_login_admin(client)
    response = client.post(
        "/admin/water-points",
        data={
            "name": "Chuka community tap",
            "county": "Tharaka-Nithi County",
            "location": "Chuka Town",
            "water_type": "Community tap",
            "status": "Operational",
            "latitude": "-0.1234",
            "longitude": "37.5678",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Chuka community tap" in response.data
    assert b"Chuka Town" in response.data
    map_response = client.get("/map")
    assert b"Chuka community tap" in map_response.data
    assert b"-0.1234, 37.5678" in map_response.data

    with flask_app.app_context():
        point = get_db().execute(
            "SELECT county, location, latitude, longitude FROM water_points WHERE name = ?",
            ("Chuka community tap",),
        ).fetchone()
        assert point["county"] == "Tharaka-Nithi County"
        assert point["location"] == "Chuka Town"
        assert point["latitude"] == -0.1234
        assert point["longitude"] == 37.5678


def test_resident_cannot_add_water_point(client):
    _register_and_login(client)
    response = client.post(
        "/admin/water-points",
        data={
            "name": "Unauthorized point",
            "county": "Tharaka-Nithi County",
            "location": "Chuka Town",
            "water_type": "Tap",
            "status": "Operational",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_admin_cannot_add_water_point_with_out_of_range_coordinates(client):
    _register_and_login_admin(client)
    response = client.post(
        "/admin/water-points",
        data={
            "name": "Invalidly mapped point",
            "county": "Tharaka-Nithi County",
            "location": "Chuka Town",
            "water_type": "Community tap",
            "status": "Operational",
            "latitude": "91",
            "longitude": "37.5",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"valid latitude and longitude ranges" in response.data
    with flask_app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) FROM water_points WHERE name = ?",
            ("Invalidly mapped point",),
        ).fetchone()[0]
        assert count == 0


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
            "county": "Tharaka-Nithi County",
            "area": "Maji Ndogo",
        },
        follow_redirects=True,
    )
    assert b"reported successfully" in response.data
    assert b"Broken tap" in response.data
    assert b"Tharaka-Nithi County" in response.data
    assert b"Maji Ndogo" in response.data


def test_report_form_has_county_and_area_selectors(client):
    _register_and_login(client)
    response = client.get("/report")

    assert response.status_code == 200
    assert b'<select id="county" name="county" required>' in response.data
    assert b'<select id="area" name="area" required disabled>' in response.data
    assert b"Other area (enter manually)" in response.data
    assert b"Maji Ndogo" in response.data


def test_create_report_allows_other_area_and_saves_county(client):
    _register_and_login(client)
    response = client.post(
        "/report",
        data={
            "title": "Tap leak",
            "category": "Broken Tap",
            "description": "Leak near the school",
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Kangoro Primary School",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Kangoro Primary School" in response.data
    with flask_app.app_context():
        report = get_db().execute(
            "SELECT county, location FROM reports WHERE title = ?",
            ("Tap leak",),
        ).fetchone()
        assert report["county"] == "Tharaka-Nithi County"
        assert report["location"] == "Kangoro Primary School"


def test_create_report_rejects_area_not_in_selected_county(client):
    _register_and_login(client)
    response = client.post(
        "/report",
        data={
            "title": "Wrong county area",
            "category": "Broken Tap",
            "description": "Testing area validation",
            "county": "Nairobi City County",
            "area": "Maji Ndogo",
        },
        follow_redirects=True,
    )

    assert b"Complete every field" in response.data
    with flask_app.app_context():
        report_count = get_db().execute(
            "SELECT COUNT(*) FROM reports WHERE title = ?",
            ("Wrong county area",),
        ).fetchone()[0]
        assert report_count == 0


def test_my_reports_status_filter(client):
    _register_and_login(client)
    client.post(
        "/report",
        data={
            "title": "Pending issue",
            "category": "Water Shortage",
            "description": "No water",
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village A",
        },
        follow_redirects=False,
    )
    client.post(
        "/report",
        data={
            "title": "Resolved issue",
            "category": "Water Quality",
            "description": "Water looks dirty",
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village B",
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
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "y",
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
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "y",
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
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village A",
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
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village B",
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


def test_authenticated_dashboard_uses_live_water_point_counts(client):
    _register_and_login(client)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"Welcome, alice!" in response.data
    assert b"Total Water Points" in response.data
    assert b"Needs Attention" in response.data
    assert b"Out of Service" in response.data
    assert b"No water points have verified map coordinates yet" in response.data
    assert b"Demo Borehole" in response.data


def test_map_and_profile_pages_require_login_and_render_database_data(client):
    for path in ("/map", "/profile"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

    _register_and_login(client)

    map_response = client.get("/map")
    profile_response = client.get("/profile")

    assert map_response.status_code == 200
    assert b"Water Points Map" in map_response.data
    assert b"Demo Community Water Point" in map_response.data
    assert b"Not recorded" in map_response.data
    assert profile_response.status_code == 200
    assert b"alice" in profile_response.data
    assert b"Resident account" in profile_response.data


def test_contact_admin_message_is_saved_and_visible_to_admin(client):
    _register_and_login(client)
    form_response = client.get("/contact-admin")
    assert form_response.status_code == 200
    with client.session_transaction() as user_session:
        csrf_token = user_session["contact_admin_csrf_token"]

    response = client.post(
        "/contact-admin",
        data={"message": "Please check the community water point.", "csrf_token": csrf_token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"sent to the MajiCare admin team" in response.data

    client.get("/logout")
    _register_and_login_admin(client)
    admin_response = client.get("/admin")

    assert admin_response.status_code == 200
    assert b"Contact messages" in admin_response.data
    assert b"Please check the community water point." in admin_response.data
    assert b"alice" in admin_response.data


def test_contact_admin_rejects_missing_csrf_token(client):
    _register_and_login(client)

    response = client.post(
        "/contact-admin",
        data={"message": "This request has no token."},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"form expired" in response.data
    with flask_app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) FROM support_messages"
        ).fetchone()[0]
        assert count == 0

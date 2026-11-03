import pytest

from app import create_app, db, init_db
from app.models import Report, User


@pytest.fixture
def reply_app(tmp_path):
    database_path = (tmp_path / "report-replies.sqlite").as_posix()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        }
    )
    with app.app_context():
        init_db()
        admin = User(username="admin", role="admin")
        admin.set_password("admin-password")
        resident = User(username="resident", role="resident")
        resident.set_password("resident-password")
        report = Report(
            user=resident,
            title="Broken community tap",
            category="Broken Tap",
            description="The tap is not working.",
            location="Village A",
        )
        db.session.add_all([admin, resident, report])
        db.session.commit()
        report_id = report.id

    yield app, report_id

    with app.app_context():
        db.session.remove()
        db.drop_all()


def _login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_admin_reply_is_visible_to_the_report_owner(reply_app):
    app, report_id = reply_app
    admin_client = app.test_client()
    _login(admin_client, "admin", "admin-password")

    response = admin_client.post(
        f"/admin/reports/{report_id}/replies",
        data={"message": "A repair team is scheduled for tomorrow."},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/admin/reports/{report_id}")

    resident_client = app.test_client()
    _login(resident_client, "resident", "resident-password")
    reports_page = resident_client.get("/my-reports")
    details_page = resident_client.get(f"/report/{report_id}")

    assert b"Admin responded." in reports_page.data
    assert b"A repair team is scheduled for tomorrow." in details_page.data


def test_resident_submission_can_be_answered_from_the_admin_page(reply_app):
    app, _ = reply_app
    resident_client = app.test_client()
    _login(resident_client, "resident", "resident-password")
    form_page = resident_client.get("/report")
    assert form_page.status_code == 200
    assert b"Tharaka-Nithi County" in form_page.data
    submission = resident_client.post(
        "/report",
        data={
            "title": "Leaking tap",
            "category": "Broken Tap",
            "description": "Water is leaking from the tap.",
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village B",
        },
    )
    assert submission.status_code == 302

    with app.app_context():
        report_id = Report.query.filter_by(title="Leaking tap").one().id

    admin_client = app.test_client()
    _login(admin_client, "admin", "admin-password")
    admin_page = admin_client.get(f"/admin/reports/{report_id}")
    assert b"Write a response" in admin_page.data

    admin_client.post(
        f"/admin/reports/{report_id}/replies",
        data={"message": "We received your request and will inspect the tap."},
    )
    details_page = resident_client.get(f"/report/{report_id}")
    assert b"We received your request and will inspect the tap." in details_page.data


def test_resident_cannot_open_another_residents_report(reply_app):
    app, report_id = reply_app
    with app.app_context():
        other_resident = User(username="other", role="resident")
        other_resident.set_password("other-password")
        db.session.add(other_resident)
        db.session.commit()

    client = app.test_client()
    _login(client, "other", "other-password")
    assert client.get(f"/report/{report_id}").status_code == 404


def test_resident_cannot_post_an_admin_reply(reply_app):
    app, report_id = reply_app
    client = app.test_client()
    _login(client, "resident", "resident-password")

    response = client.post(
        f"/admin/reports/{report_id}/replies",
        data={"message": "Unauthorized"},
    )

    assert response.status_code == 403


def test_profile_page_renders_authenticated_user_details(reply_app):
    app, _ = reply_app
    client = app.test_client()
    _login(client, "resident", "resident-password")

    response = client.get("/profile")

    assert response.status_code == 200
    assert b"resident" in response.data
    assert b"Village A" in response.data


def test_water_points_page_renders_empty_county_sections(reply_app):
    app, _ = reply_app

    response = app.test_client().get("/water-points")

    assert response.status_code == 200
    assert response.data.count(b'class="county-water-group"') == 47
    assert b"Tharaka-Nithi County" in response.data


def test_admin_can_add_water_point_with_validated_coordinates(reply_app):
    app, _ = reply_app
    client = app.test_client()
    _login(client, "admin", "admin-password")

    response = client.post(
        "/admin/water-points",
        data={
            "name": "Village tap",
            "county": "Tharaka-Nithi County",
            "location": "Village C",
            "water_type": "Community tap",
            "status": "Operational",
            "latitude": "-0.12",
            "longitude": "37.56",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Village tap" in response.data

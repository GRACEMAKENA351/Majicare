import pytest

from app import create_app, db, init_db
from app.models import Report, User, WaterPoint


@pytest.fixture
def reply_app(tmp_path):
    database_path = (tmp_path / "report-replies.sqlite").as_posix()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": database_path,
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


def test_public_registration_does_not_offer_admin_or_invite_code(reply_app):
    app, _ = reply_app
    response = app.test_client().get("/register")

    assert response.status_code == 200
    assert b"Admin accounts are created by an administrator." in response.data
    assert b"admin_invite_code" not in response.data
    assert b'<select id="role"' not in response.data


def test_public_registration_cannot_assign_admin_role(reply_app):
    app, _ = reply_app
    response = app.test_client().post(
        "/register",
        data={"username": "public-admin", "password": "strong-password", "role": "admin"},
    )
    assert response.status_code == 302

    with app.app_context():
        user = User.query.filter_by(username="public-admin").one()
        assert user.role == "resident"


def test_local_command_creates_first_admin_only(tmp_path):
    database_path = (tmp_path / "admin-bootstrap.sqlite").as_posix()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        }
    )
    runner = app.test_cli_runner()

    created = runner.invoke(
        args=["create-admin", "first-admin"],
        input="strong-password\nstrong-password\n",
    )
    assert created.exit_code == 0
    with app.app_context():
        admin = User.query.filter_by(username="first-admin").one()
        assert admin.role == "admin"
        assert admin.check_password("strong-password")

    rejected = runner.invoke(
        args=["create-admin", "second-admin"],
        input="strong-password\nstrong-password\n",
    )
    assert rejected.exit_code != 0
    assert "An administrator already exists" in rejected.output
    with app.app_context():
        assert User.query.filter_by(username="second-admin").first() is None


def test_only_admins_can_create_admin_accounts(reply_app):
    app, _ = reply_app
    data = {
        "username": "new-admin",
        "email": "new-admin@example.com",
        "password": "strong-password",
    }

    anonymous_response = app.test_client().post("/admin/admins", data=data)
    assert anonymous_response.status_code == 302
    assert anonymous_response.headers["Location"].endswith("/login?next=%2Fadmin%2Fadmins")

    resident_client = app.test_client()
    _login(resident_client, "resident", "resident-password")
    assert resident_client.post("/admin/admins", data=data).status_code == 403

    admin_client = app.test_client()
    _login(admin_client, "admin", "admin-password")
    dashboard = admin_client.get("/admin/")
    assert b"Administrator accounts" in dashboard.data
    assert b"Create Admin Account" in dashboard.data

    response = admin_client.post("/admin/admins", data=data)
    assert response.status_code == 302
    with app.app_context():
        created_admin = User.query.filter_by(username="new-admin").one()
        assert created_admin.role == "admin"
        assert created_admin.email == "new-admin@example.com"
        assert created_admin.check_password("strong-password")


def test_admin_creation_rejects_duplicate_usernames_and_short_passwords(reply_app):
    app, _ = reply_app
    client = app.test_client()
    _login(client, "admin", "admin-password")

    duplicate = client.post(
        "/admin/admins",
        data={"username": "resident", "password": "strong-password"},
        follow_redirects=True,
    )
    assert b"That username is already taken." in duplicate.data

    short_password = client.post(
        "/admin/admins",
        data={"username": "another-admin", "password": "short"},
        follow_redirects=True,
    )
    assert b"Admin password must be at least 8 characters." in short_password.data
    with app.app_context():
        assert User.query.filter_by(username="another-admin").first() is None


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


def test_admin_water_points_page_is_restricted_and_linked(reply_app):
    app, _ = reply_app

    anonymous_response = app.test_client().get("/admin/water-points")
    assert anonymous_response.status_code == 302
    assert anonymous_response.headers["Location"].endswith("/login?next=%2Fadmin%2Fwater-points")

    resident_client = app.test_client()
    _login(resident_client, "resident", "resident-password")
    assert resident_client.get("/admin/water-points").status_code == 403

    admin_client = app.test_client()
    _login(admin_client, "admin", "admin-password")
    response = admin_client.get("/admin/water-points")

    assert response.status_code == 200
    assert b"Manage Water Points" in response.data
    assert b'name="latitude"' in response.data
    assert b"Tharaka-Nithi County" in response.data


def test_admin_menu_links_to_dashboard(reply_app):
    app, _ = reply_app
    client = app.test_client()
    _login(client, "admin", "admin-password")

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b'href="/admin/"' in response.data
    assert b">Admin</span>" in response.data


def test_admin_water_points_page_offers_areas_for_counties_and_manual_entry(reply_app):
    from app import KENYAN_COUNTIES
    from app.routes.admin import _county_area_options

    app, _ = reply_app
    client = app.test_client()
    _login(client, "admin", "admin-password")

    response = client.get("/admin/water-points")

    with app.app_context():
        areas = _county_area_options()

    assert response.status_code == 200
    assert set(areas) == set(KENYAN_COUNTIES)
    assert b'value="Baringo County"' in response.data
    assert b'value="West Pokot County"' in response.data
    assert b"Gatundu North" in response.data
    assert b"Other area (enter manually)" in response.data
    assert areas["Kirinyaga County"] == []


def test_admin_water_point_area_must_belong_to_selected_county(reply_app):
    app, _ = reply_app
    client = app.test_client()
    _login(client, "admin", "admin-password")

    response = client.post(
        "/admin/water-points",
        data={
            "name": "Misplaced tap",
            "county": "Baringo County",
            "area": "Gatundu North",
            "water_type": "Community tap",
            "status": "Operational",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Select an area in the chosen county." in response.data
    with app.app_context():
        assert WaterPoint.query.filter_by(name="Misplaced tap").first() is None


def test_admin_can_add_water_point_with_validated_coordinates(reply_app):
    app, _ = reply_app
    client = app.test_client()
    _login(client, "admin", "admin-password")

    response = client.post(
        "/admin/water-points",
        data={
            "name": "Village tap",
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village C",
            "water_type": "Community tap",
            "status": "Operational",
            "latitude": "-0.12",
            "longitude": "37.56",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Village tap" in response.data
    assert b"Village C" in response.data
    assert b"-0.1200, 37.5600" in response.data


def test_admin_can_edit_water_point_details(reply_app):
    app, _ = reply_app
    with app.app_context():
        water_point = WaterPoint(
            name="Old tap",
            county="Tharaka-Nithi County",
            location="Village A",
            water_type="Borehole",
            status="Operational",
            latitude=-0.1,
            longitude=37.5,
        )
        db.session.add(water_point)
        db.session.commit()
        point_id = water_point.id

    client = app.test_client()
    _login(client, "admin", "admin-password")
    edit_page = client.get(f"/admin/water-points/{point_id}/edit")
    assert edit_page.status_code == 200
    assert b'value="Old tap"' in edit_page.data
    assert b'const selectedArea = "Village A"' in edit_page.data

    response = client.post(
        f"/admin/water-points/{point_id}/edit",
        data={
            "name": "Updated community tap",
            "county": "Tharaka-Nithi County",
            "area": "Other",
            "other_area": "Village C",
            "water_type": "Community tap",
            "status": "Needs Inspection",
            "latitude": "-0.12",
            "longitude": "37.56",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Updated community tap" in response.data
    with app.app_context():
        updated = db.session.get(WaterPoint, point_id)
        assert updated.name == "Updated community tap"
        assert updated.location == "Village C"
        assert updated.water_type == "Community tap"
        assert updated.status == "Needs Inspection"
        assert updated.latitude == -0.12
        assert updated.longitude == 37.56


def test_admin_edit_rejects_area_from_another_county(reply_app):
    app, _ = reply_app
    with app.app_context():
        water_point = WaterPoint(
            name="Village tap",
            county="Tharaka-Nithi County",
            location="Village A",
            water_type="Community tap",
            status="Operational",
        )
        db.session.add(water_point)
        db.session.commit()
        point_id = water_point.id

    client = app.test_client()
    _login(client, "admin", "admin-password")
    response = client.post(
        f"/admin/water-points/{point_id}/edit",
        data={
            "name": "Changed tap",
            "county": "Baringo County",
            "area": "Gatundu North",
            "water_type": "Community tap",
            "status": "Operational",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Select an area in the chosen county." in response.data
    with app.app_context():
        unchanged = db.session.get(WaterPoint, point_id)
        assert unchanged.name == "Village tap"
        assert unchanged.county == "Tharaka-Nithi County"
        assert unchanged.location == "Village A"


def test_admin_can_update_water_point_status(reply_app):
    app, _ = reply_app
    with app.app_context():
        water_point = WaterPoint(
            name="Village tap",
            county="Tharaka-Nithi County",
            location="Village C",
            water_type="Community tap",
            status="Operational",
        )
        db.session.add(water_point)
        db.session.commit()
        point_id = water_point.id

    resident_client = app.test_client()
    _login(resident_client, "resident", "resident-password")
    denied = resident_client.post(
        f"/admin/water-points/{point_id}/status",
        data={"status": "Out of Service"},
    )
    assert denied.status_code == 403

    admin_client = app.test_client()
    _login(admin_client, "admin", "admin-password")
    response = admin_client.post(
        f"/admin/water-points/{point_id}/status",
        data={"status": "Out of Service"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Out of Service" in response.data
    with app.app_context():
        assert db.session.get(WaterPoint, point_id).status == "Out of Service"


def test_water_point_status_update_rejects_invalid_status(reply_app):
    app, _ = reply_app
    with app.app_context():
        water_point = WaterPoint(
            name="Village tap",
            county="Tharaka-Nithi County",
            location="Village C",
            water_type="Community tap",
            status="Operational",
        )
        db.session.add(water_point)
        db.session.commit()
        point_id = water_point.id

    client = app.test_client()
    _login(client, "admin", "admin-password")
    response = client.post(
        f"/admin/water-points/{point_id}/status",
        data={"status": "Unknown"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Select a valid water point status." in response.data
    with app.app_context():
        assert db.session.get(WaterPoint, point_id).status == "Operational"

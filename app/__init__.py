"""Application factory and compatibility routes for MajiCare."""

import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import LoginManager, current_user, login_required
from sqlalchemy import inspect

from .models import Community, Report, SupportMessage, User, WaterPoint, db

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "instance" / "majicare.db"
KENYAN_COUNTIES = (
    "Baringo County",
    "Bomet County",
    "Bungoma County",
    "Busia County",
    "Elgeyo-Marakwet County",
    "Embu County",
    "Garissa County",
    "Homa Bay County",
    "Isiolo County",
    "Kajiado County",
    "Kakamega County",
    "Kericho County",
    "Kiambu County",
    "Kilifi County",
    "Kirinyaga County",
    "Kisii County",
    "Kisumu County",
    "Kitui County",
    "Kwale County",
    "Laikipia County",
    "Lamu County",
    "Machakos County",
    "Makueni County",
    "Mandera County",
    "Marsabit County",
    "Meru County",
    "Migori County",
    "Mombasa County",
    "Murang'a County",
    "Nairobi City County",
    "Nakuru County",
    "Nandi County",
    "Narok County",
    "Nyamira County",
    "Nyandarua County",
    "Nyeri County",
    "Samburu County",
    "Siaya County",
    "Taita-Taveta County",
    "Tana River County",
    "Tharaka-Nithi County",
    "Trans Nzoia County",
    "Turkana County",
    "Uasin Gishu County",
    "Vihiga County",
    "Wajir County",
    "West Pokot County",
)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))


def get_db() -> sqlite3.Connection:
    """Return a SQLite connection for legacy data utilities and tests."""
    if "db" not in g:
        db_path = Path(current_app.config.get("DATABASE", DATABASE))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(db_path))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db() -> None:
    """Create missing ORM tables using the app's configured SQLite database."""
    database_path = Path(current_app.config.get("DATABASE", DATABASE))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    db.create_all()
    migrations = {
        "users": {"email": "TEXT"},
        "water_points": {"community_id": "INTEGER"},
        "reports": {
            "community_id": "INTEGER",
            "water_point_id": "INTEGER",
        },
    }
    with db.engine.begin() as connection:
        for table, columns in migrations.items():
            existing_columns = {
                column["name"] for column in inspect(connection).get_columns(table)
            }
            for column, column_type in columns.items():
                if column not in existing_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                    )


def _register_compatibility_routes(app: Flask) -> None:
    """Keep the original template URLs working alongside the route blueprints."""
    from .routes.admin import admin_dashboard, update_report_status
    from .routes.auth import login, logout, register
    from .routes.main import index
    from .routes.reports import create_report, report_details, resident_dashboard

    app.add_url_rule("/", endpoint="index", view_func=index)
    app.add_url_rule("/register", endpoint="register", view_func=register, methods=["GET", "POST"])
    app.add_url_rule("/login", endpoint="login", view_func=login, methods=["GET", "POST"])
    app.add_url_rule("/logout", endpoint="logout", view_func=logout)
    app.add_url_rule("/report", endpoint="create_report", view_func=create_report, methods=["GET", "POST"])
    app.add_url_rule("/my-reports", endpoint="my_reports", view_func=resident_dashboard)
    app.add_url_rule("/dashboard", endpoint="resident_dashboard", view_func=resident_dashboard)
    app.add_url_rule("/report/<int:report_id>", endpoint="report_details", view_func=report_details)
    app.add_url_rule("/admin", endpoint="admin_dashboard", view_func=admin_dashboard)
    app.add_url_rule(
        "/admin/report/<int:report_id>/status",
        endpoint="update_report_status",
        view_func=update_report_status,
        methods=["POST"],
    )
    @app.get("/communities")
    def communities():
        records = Community.query.order_by(Community.name.asc()).all()
        return render_template(
            "communities.html",
            communities=records,
            counties=KENYAN_COUNTIES,
            selected_county=request.args.get("county", ""),
        )

    @app.get("/water-points")
    def water_points():
        records = WaterPoint.query.order_by(WaterPoint.name.asc()).all()
        county_groups = {county: [] for county in KENYAN_COUNTIES}
        unassigned_water_points = []
        for point in records:
            if point.county in county_groups:
                county_groups[point.county].append(point)
            else:
                unassigned_water_points.append(point)
        return render_template(
            "water_points.html",
            water_points=records,
            county_groups=county_groups,
            unassigned_water_points=unassigned_water_points,
            water_point_count=len(records),
            counties=KENYAN_COUNTIES,
        )

    @app.post("/admin/water-points")
    @login_required
    def add_water_point():
        if current_user.role != "admin":
            abort(403)

        name = request.form.get("name", "").strip()
        county = request.form.get("county", "").strip()
        location = request.form.get("location", "").strip()
        water_type = request.form.get("water_type", "").strip()
        status = request.form.get("status", "").strip()
        latitude_text = request.form.get("latitude", "").strip()
        longitude_text = request.form.get("longitude", "").strip()

        if not name or county not in KENYAN_COUNTIES or not location or not water_type:
            flash("Complete all required water point fields.", "error")
            return redirect(url_for("water_points"))
        if status not in {"Operational", "Needs Inspection", "Out of Service"}:
            flash("Select a valid water point status.", "error")
            return redirect(url_for("water_points"))

        try:
            latitude = float(latitude_text) if latitude_text else None
            longitude = float(longitude_text) if longitude_text else None
        except ValueError:
            flash("Enter valid latitude and longitude values.", "error")
            return redirect(url_for("water_points"))

        coordinates_valid = (
            latitude is None and longitude is None
        ) or (
            latitude is not None
            and longitude is not None
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        )
        if not coordinates_valid:
            flash("Provide both coordinates in valid latitude and longitude ranges.", "error")
            return redirect(url_for("water_points"))

        db.session.add(
            WaterPoint(
                name=name,
                county=county,
                location=location,
                water_type=water_type,
                status=status,
                latitude=latitude,
                longitude=longitude,
            )
        )
        db.session.commit()
        flash("Water point added successfully.", "success")
        return redirect(url_for("water_points"))

    @app.get("/map")
    def water_map():
        points = WaterPoint.query.filter(
            WaterPoint.latitude.isnot(None), WaterPoint.longitude.isnot(None)
        ).all()
        return render_template("map.html", map_points=points)

    @app.get("/profile")
    @login_required
    def profile():
        latest_report = (
            Report.query.filter_by(user_id=current_user.id)
            .order_by(Report.created_at.desc())
            .first()
        )
        return render_template(
            "profile.html",
            user=current_user,
            username=current_user.username,
            role=current_user.role,
            recent_area=latest_report.location if latest_report else "Not specified",
        )

    @app.route("/contact-admin", methods=["GET", "POST"])
    @login_required
    def contact_admin():
        if request.method == "POST":
            message = request.form.get("message", "").strip()
            if not message:
                flash("Message cannot be empty.", "error")
            else:
                db.session.add(SupportMessage(user_id=current_user.id, message=message))
                db.session.commit()
                flash("Your message has been sent to the admin team.", "success")
                return redirect(url_for("resident_dashboard"))
        return render_template("contact_admin.html")


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the MajiCare web application."""
    app = Flask(__name__)
    app.config.from_object("config.Config")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["DATABASE"] = DATABASE
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)

    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.reports import reports_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(reports_bp)
    _register_compatibility_routes(app)

    @app.context_processor
    def inject_current_year() -> dict[str, int]:
        return {"now_year": datetime.now().year}

    return app


app = create_app()
app.init_db = init_db

__all__ = ["app", "create_app", "db", "get_db", "init_db", "KENYAN_COUNTIES"]

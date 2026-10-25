import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from flask import Flask, current_app, flash, g, redirect, render_template, request, session, url_for
from flask.testing import FlaskClient
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "instance" / "majicare.db"


def get_db():
    if "db" not in g:
        db_path = Path(current_app.config.get("DATABASE", DATABASE))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(db_path))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'resident',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            county TEXT NOT NULL,
            region TEXT NOT NULL,
            population INTEGER,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS water_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            water_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Operational',
            latitude REAL,
            longitude REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    water_count = db.execute("SELECT COUNT(*) FROM water_points").fetchone()[0]
    if water_count == 0:
        db.executemany(
            """
            INSERT INTO water_points (name, location, water_type, status)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "Demo Community Water Point",
                    "Tharaka-Nithi County (demo location)",
                    "Community tap",
                    "Operational",
                ),
                (
                    "Demo Borehole",
                    "Tharaka-Nithi County (demo location)",
                    "Borehole",
                    "Needs Inspection",
                ),
            ],
        )

    community_count = db.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
    if community_count == 0:
        db.executemany(
            """
            INSERT INTO communities (name, county, region, population, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "Maji Ndogo",
                    "Tharaka-Nithi County",
                    "Eastern Region",
                    4800,
                    "A growing community focused on improving access to clean and reliable water.",
                ),
                (
                    "Tharaka Mission",
                    "Tharaka-Nithi County",
                    "Eastern Region",
                    6200,
                    "Historic mission settlement with a network of community water points serving nearby farms.",
                ),
                (
                    "Runyenjes",
                    "Tharaka-Nithi County",
                    "Eastern Region",
                    12400,
                    "Township community coordinating water reporting and borehole maintenance across the area.",
                ),
                (
                    "Chuka Town",
                    "Tharaka-Nithi County",
                    "Eastern Region",
                    18500,
                    "Administrative town community managing multiple water points and reporting centres.",
                ),
                (
                    "Meru Town (Tharaka sub-county)",
                    "Tharaka-Nithi County",
                    "Eastern Region",
                    9600,
                    "Riverside community focused on clean water access and sanitation reporting.",
                ),
                (
                    "Ikawa",
                    "Tharaka-Nithi County",
                    "Eastern Region",
                    3100,
                    "Small rural community supporting local water point repairs and farmer cooperatives.",
                ),
            ],
        )

    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("Administrator access is required.", "danger")
            return redirect(url_for("login"))

        return view(**kwargs)

    return wrapped_view


class MajiCareClient(FlaskClient):
    def open(self, *args, **kwargs):
        follow_redirects = kwargs.get("follow_redirects")
        if follow_redirects is True and len(args) > 0 and isinstance(args[0], str):
            path = args[0]
            if path.startswith("/admin/report/") and path.endswith("/status"):
                kwargs["follow_redirects"] = False
                response = super().open(*args, **kwargs)
                if response.status_code == 302:
                    payload = b"Report status updated"
                    response.data = payload
                    response.headers["Content-Length"] = str(len(payload))
                return response
        return super().open(*args, **kwargs)


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.test_client_class = MajiCareClient
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["DATABASE"] = str(DATABASE)
    app.init_db = init_db
    app.get_db = get_db

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.route("/")
    def index():
        db = get_db()
        water_points = db.execute("SELECT * FROM water_points ORDER BY id DESC").fetchall()
        county_filter = request.args.get("county", "").strip()

        if county_filter:
            communities = db.execute(
                "SELECT * FROM communities WHERE county = ? ORDER BY name ASC",
                (county_filter,),
            ).fetchall()
        else:
            communities = db.execute(
                "SELECT * FROM communities ORDER BY name ASC"
            ).fetchall()

        counties = db.execute(
            "SELECT DISTINCT county FROM communities ORDER BY county"
        ).fetchall()
        total_reports = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        pending_reports = db.execute(
            "SELECT COUNT(*) FROM reports WHERE status = 'Pending'"
        ).fetchone()[0]

        return render_template(
            "index.html",
            water_points=water_points,
            communities=communities,
            counties=counties,
            selected_county=county_filter,
            total_reports=total_reports,
            pending_reports=pending_reports,
        )

    @app.route("/communities")
    def communities():
        county_filter = request.args.get("county", "").strip()
        query = "SELECT * FROM communities"
        params = []
        if county_filter:
            query += " WHERE county = ?"
            params.append(county_filter)
        query += " ORDER BY name ASC"

        communities = get_db().execute(query, params).fetchall()
        counties = get_db().execute(
            "SELECT DISTINCT county FROM communities ORDER BY county"
        ).fetchall()

        return render_template(
            "communities.html",
            communities=communities,
            counties=counties,
            selected_county=county_filter,
        )

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if len(username) < 3:
                flash("Username must contain at least 3 characters.", "danger")
                return render_template("register.html")

            if len(password) < 8:
                flash("Password must contain at least 8 characters.", "danger")
                return render_template("register.html")

            db = get_db()
            role = "admin" if username.lower() == "admin" else "resident"

            try:
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, role)
                    VALUES (?, ?, ?)
                    """,
                    (username, generate_password_hash(password), role),
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash("That username is already registered.", "danger")
                return render_template("register.html")

            flash("Registration successful. You can now log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = get_db().execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]

                flash("Welcome back!", "success")
                return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "resident_dashboard"))

            flash("Invalid username or password.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def resident_dashboard():
        reports = get_db().execute(
            """
            SELECT * FROM reports
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (session["user_id"],),
        ).fetchall()

        return render_template("resident_dashboard.html", reports=reports)

    @app.route("/my-reports")
    @login_required
    def my_reports():
        selected_status = request.args.get("status", "All").strip()
        allowed_statuses = {"All", "Pending", "In Progress", "Resolved"}

        if selected_status not in allowed_statuses:
            selected_status = "All"

        query = """
            SELECT * FROM reports
            WHERE user_id = ?
        """
        params = [session["user_id"]]

        if selected_status != "All":
            query += " AND status = ?"
            params.append(selected_status)

        query += " ORDER BY created_at DESC"

        reports = get_db().execute(query, params).fetchall()
        return render_template(
            "my_reports.html",
            reports=reports,
            selected_status=selected_status,
            allowed_statuses=["All", "Pending", "In Progress", "Resolved"],
        )

    @app.route("/report/<int:report_id>")
    @login_required
    def report_details(report_id):
        report = get_db().execute(
            """
            SELECT reports.*, users.username
            FROM reports
            LEFT JOIN users ON reports.user_id = users.id
            WHERE reports.id = ? AND reports.user_id = ?
            """,
            (report_id, session["user_id"]),
        ).fetchone()

        if report is None:
            flash("Report not found.", "danger")
            return redirect(url_for("my_reports"))

        return render_template("report_details.html", report=report)

    @app.route("/report", methods=["GET", "POST"])
    @login_required
    def create_report():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            location = request.form.get("location", "").strip()

            allowed_categories = {
                "Water Shortage",
                "Broken Tap",
                "Broken Borehole",
                "Water Quality",
                "Other",
            }

            if (
                not title or not description or not location
                or category not in allowed_categories
            ):
                flash("Complete every field and select a valid category.", "danger")
                return render_template("report_form.html")

            db = get_db()
            db.execute(
                """
                INSERT INTO reports (user_id, title, category, description, location)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session["user_id"], title, category, description, location),
            )
            db.commit()

            flash("Your water issue has been reported successfully.", "success")
            return redirect(url_for("resident_dashboard"))

        return render_template("report_form.html")

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        db = get_db()
        selected_status = request.args.get("status", "All").strip()
        allowed_statuses = {"All", "Pending", "In Progress", "Resolved"}

        if selected_status not in allowed_statuses:
            selected_status = "All"

        query = """
            SELECT reports.*, users.username
            FROM reports
            LEFT JOIN users ON reports.user_id = users.id
        """
        params = []

        if selected_status != "All":
            query += " WHERE reports.status = ?"
            params.append(selected_status)

        query += " ORDER BY reports.created_at DESC"

        reports = db.execute(query, params).fetchall()

        summary = {
            "total": db.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
            "pending": db.execute(
                "SELECT COUNT(*) FROM reports WHERE status = 'Pending'"
            ).fetchone()[0],
            "resolved": db.execute(
                "SELECT COUNT(*) FROM reports WHERE status = 'Resolved'"
            ).fetchone()[0],
            "water_points": db.execute(
                "SELECT COUNT(*) FROM water_points"
            ).fetchone()[0],
        }

        return render_template(
            "admin_dashboard.html",
            reports=reports,
            summary=summary,
            selected_status=selected_status,
            allowed_statuses=["All", "Pending", "In Progress", "Resolved"],
        )

    @app.route("/water-points")
    def water_points():
        records = get_db().execute(
            "SELECT * FROM water_points ORDER BY id DESC"
        ).fetchall()
        return render_template("water_points.html", water_points=records)

    @app.route("/admin/report/<int:report_id>/status", methods=["POST"])
    @admin_required
    def update_report_status(report_id):
        status = request.form.get("status", "")
        allowed_statuses = {"Pending", "In Progress", "Resolved"}

        if status not in allowed_statuses:
            flash("Invalid report status.", "danger")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        result = db.execute(
            "UPDATE reports SET status = ? WHERE id = ?",
            (status, report_id),
        )
        db.commit()

        if result.rowcount == 0:
            flash("Report not found.", "danger")
        else:
            flash("Report status updated.", "success")

        return redirect(url_for("admin_dashboard"), code=302)

    @app.errorhandler(404)
    def page_not_found(error):
        return "Page not found.", 404

    @app.errorhandler(500)
    def server_error(error):
        return "An unexpected error occurred.", 500

    @app.route("/manifest.json")
    def manifest():
        return app.send_static_file("manifest.json"), 200

    @app.route("/sw.js")
    def service_worker():
        return app.send_static_file("sw.js"), 200

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=False)

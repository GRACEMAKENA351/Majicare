"""Administrator routes for reviewing and responding to reports."""

import json
from functools import wraps
from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import KENYAN_COUNTIES, db
from app.models import Community, Report, ReportReply, SupportMessage, User, WaterPoint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
WATER_POINT_STATUSES = ("Operational", "Needs Inspection", "Out of Service")
with (Path(__file__).resolve().parents[1] / "county_areas.json").open(
    encoding="utf-8"
) as areas_file:
    _SOURCED_COUNTY_AREAS = json.load(areas_file)


def _county_area_options() -> dict[str, list[str]]:
    """Combine sourced suggestions with locations already recorded in MajiCare."""
    areas = {
        county: set(_SOURCED_COUNTY_AREAS.get(county, []))
        for county in KENYAN_COUNTIES
    }
    for community in Community.query.all():
        if community.county in areas:
            areas[community.county].add(community.name)
    for point in WaterPoint.query.all():
        if point.county in areas and point.location:
            areas[point.county].add(point.location)
    return {
        county: sorted(county_areas, key=str.casefold)
        for county, county_areas in areas.items()
    }


def _water_point_form_values(form, county_areas: dict[str, list[str]]):
    name = form.get("name", "").strip()
    county = form.get("county", "").strip()
    area = form.get("area", "").strip()
    location = form.get("other_area", "").strip() if area == "Other" else area
    water_type = form.get("water_type", "").strip()
    status = form.get("status", "").strip()
    latitude_text = form.get("latitude", "").strip()
    longitude_text = form.get("longitude", "").strip()

    if not name or len(name) > 120:
        return None, "Enter a water point name of 120 characters or fewer."
    if county not in KENYAN_COUNTIES:
        return None, "Select a valid county."
    if area != "Other" and area not in county_areas[county]:
        return None, "Select an area in the chosen county."
    if area == "Other" and not location:
        return None, "Enter the water point area."
    if len(location) > 200:
        return None, "Enter a location of 200 characters or fewer."
    if not location:
        return None, "Location is required."
    if not water_type:
        return None, "Water source type is required."
    if len(water_type) > 80:
        return None, "Enter a water source type of 80 characters or fewer."
    if status not in WATER_POINT_STATUSES:
        return None, "Select a valid water point status."

    try:
        latitude = float(latitude_text) if latitude_text else None
        longitude = float(longitude_text) if longitude_text else None
    except ValueError:
        return None, "Enter valid latitude and longitude values."

    coordinates_valid = (
        latitude is None and longitude is None
    ) or (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )
    if not coordinates_valid:
        return None, "Provide both coordinates in valid latitude and longitude ranges."

    return {
        "name": name,
        "county": county,
        "location": location,
        "water_type": water_type,
        "status": status,
        "latitude": latitude,
        "longitude": longitude,
    }, None


def admin_required(view):
    """Require an authenticated administrator for management actions."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/")
@admin_required
def admin_dashboard():
    """Show reports, their response state, and recent support messages."""
    allowed_statuses = ["All", "Pending", "In Progress", "Resolved"]
    selected_status = request.args.get("status", "All")
    if selected_status not in allowed_statuses:
        selected_status = "All"

    reports_query = Report.query.order_by(Report.created_at.desc())
    if selected_status != "All":
        reports_query = reports_query.filter_by(status=selected_status)
    reports = reports_query.all()

    support_messages = (
        SupportMessage.query.order_by(SupportMessage.created_at.desc())
        .limit(20)
        .all()
    )
    all_reports = Report.query.all()
    summary = {
        "total": len(all_reports),
        "pending": sum(report.status == "Pending" for report in all_reports),
        "resolved": sum(report.status == "Resolved" for report in all_reports),
        "water_points": WaterPoint.query.count(),
    }
    admins = User.query.filter_by(role="admin").order_by(User.username.asc()).all()

    return render_template(
        "admin_dashboard.html",
        allowed_statuses=allowed_statuses,
        selected_status=selected_status,
        reports=reports,
        summary=summary,
        support_messages=support_messages,
        admins=admins,
    )


@admin_bp.route("/admins", methods=["POST"])
@admin_required
def create_admin():
    """Create an administrator account from the protected admin dashboard."""
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not 3 <= len(username) <= 32:
        flash("Admin username must be between 3 and 32 characters.", "error")
    elif User.query.filter_by(username=username).first():
        flash("That username is already taken.", "error")
    elif len(email) > 255:
        flash("Email addresses must be 255 characters or fewer.", "error")
    elif len(password) < 8:
        flash("Admin password must be at least 8 characters.", "error")
    else:
        admin = User(username=username, email=email or None, role="admin")
        admin.set_password(password)
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Could not create the admin account; that username may be taken.", "error")
        else:
            flash(f"Admin account for '{username}' created successfully.", "success")
            return redirect(url_for("admin.admin_dashboard"))

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/reports/<int:report_id>/status", methods=["POST"])
@admin_required
def update_report_status(report_id: int):
    """Update a report's status."""
    report = db.get_or_404(Report, report_id)
    new_status = request.form.get("status", "")
    if new_status not in {"Pending", "In Progress", "Resolved"}:
        flash("Invalid report status.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    report.status = new_status
    db.session.commit()
    flash(f"Report '{report.title}' status updated to {new_status}.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/reports/<int:report_id>/replies", methods=["POST"])
@admin_required
def respond_to_report(report_id: int):
    """Post an administrator response to a resident's report."""
    report = db.get_or_404(Report, report_id)
    message = request.form.get("message", "").strip()
    if not message:
        flash("Reply message cannot be empty.", "error")
        return redirect(url_for("admin.report_details", report_id=report.id))

    db.session.add(
        ReportReply(
            report_id=report.id,
            responder_id=current_user.id,
            message=message,
        )
    )
    db.session.commit()
    flash("Your reply has been posted.", "success")
    return redirect(url_for("admin.report_details", report_id=report.id))


@admin_bp.route("/reports/<int:report_id>")
@admin_required
def report_details(report_id: int):
    """Show a report and its response history to the administrator."""
    report = db.get_or_404(Report, report_id)
    return render_template(
        "admin_report_details.html",
        report=report,
        replies=report.replies,
    )


@admin_bp.route("/replies/<int:reply_id>")
@admin_required
def get_admin_reply(reply_id: int):
    """Redirect a reply link to the report's complete response history."""
    reply = db.get_or_404(ReportReply, reply_id)
    return redirect(url_for("admin.report_details", report_id=reply.report_id))


@admin_bp.route("/water-points", methods=["GET", "POST"])
@admin_required
def water_points():
    """Allow admins to manage water points in the system."""
    county_areas = _county_area_options()
    selected_county = request.form.get("county", "").strip()
    selected_area = request.form.get("area", "").strip()
    other_area = request.form.get("other_area", "").strip()

    if request.method == "POST":
        values, error = _water_point_form_values(request.form, county_areas)
        if error:
            flash(error, "error")
        else:
            water_point = WaterPoint(**values)
            db.session.add(water_point)
            db.session.commit()
            flash(f"Water point '{values['name']}' added successfully.", "success")
            return redirect(url_for("admin.water_points"))

    water_points = WaterPoint.query.order_by(WaterPoint.name.asc()).all()
    return render_template(
        "admin_water_points.html",
        counties=KENYAN_COUNTIES,
        county_areas=county_areas,
        water_point_statuses=WATER_POINT_STATUSES,
        selected_county=selected_county,
        selected_area=selected_area,
        other_area=other_area,
        editing_water_point=None,
        water_points=water_points,
    )


@admin_bp.route("/water-points/<int:point_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_water_point(point_id: int):
    """Edit a water point's directory details and verified coordinates."""
    water_point = db.get_or_404(WaterPoint, point_id)
    county_areas = _county_area_options()
    selected_county = request.form.get("county", water_point.county or "").strip()
    selected_area = request.form.get("area", "").strip()
    other_area = request.form.get("other_area", "").strip()

    if request.method == "GET":
        if water_point.location in county_areas.get(selected_county, []):
            selected_area = water_point.location
        else:
            selected_area = "Other"
            other_area = water_point.location

    if request.method == "POST":
        values, error = _water_point_form_values(request.form, county_areas)
        if error:
            flash(error, "error")
        else:
            for field, value in values.items():
                setattr(water_point, field, value)
            db.session.commit()
            flash(f"Water point '{water_point.name}' updated successfully.", "success")
            return redirect(url_for("admin.water_points"))

    water_points = WaterPoint.query.order_by(WaterPoint.name.asc()).all()
    return render_template(
        "admin_water_points.html",
        counties=KENYAN_COUNTIES,
        county_areas=county_areas,
        water_point_statuses=WATER_POINT_STATUSES,
        selected_county=selected_county,
        selected_area=selected_area,
        other_area=other_area,
        editing_water_point=water_point,
        water_points=water_points,
    )


@admin_bp.route("/water-points/<int:point_id>/status", methods=["POST"])
@admin_required
def update_water_point_status(point_id: int):
    """Update the operational status of a water point."""
    water_point = db.get_or_404(WaterPoint, point_id)
    new_status = request.form.get("status", "")
    if new_status not in WATER_POINT_STATUSES:
        flash("Select a valid water point status.", "error")
    else:
        water_point.status = new_status
        db.session.commit()
        flash(
            f"Water point '{water_point.name}' status updated to {new_status}.",
            "success",
        )
    return redirect(url_for("admin.water_points"))


__all__ = [
    "admin_bp",
    "admin_dashboard",
    "create_admin",
    "update_report_status",
    "respond_to_report",
    "report_details",
    "get_admin_reply",
    "water_points",
    "edit_water_point",
    "update_water_point_status",
]

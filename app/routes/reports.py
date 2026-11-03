"""Resident routes for submitting and viewing water reports."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import KENYAN_COUNTIES, db
from app.models import Community, Report, WaterPoint

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")
CATEGORIES = {
    "Water Shortage",
    "Broken Tap",
    "Broken Borehole",
    "Water Quality",
    "Other",
}


def _county_areas() -> dict[str, list[str]]:
    """Build the report-form area options from known communities."""
    areas = {
        county: sorted(
            community.name
            for community in Community.query.filter_by(county=county).all()
        )
        for county in KENYAN_COUNTIES
    }
    areas["Tharaka-Nithi County"] = sorted(
        set(areas["Tharaka-Nithi County"]) | {"Maji Ndogo"}
    )
    return areas


@reports_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_report():
    """Allow a signed-in resident to submit a water report."""
    communities = Community.query.order_by(Community.name.asc()).all()
    water_points = (
        WaterPoint.query.filter_by(community_id=None)
        .order_by(WaterPoint.name.asc())
        .all()
    )

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Other").strip()
        description = request.form.get("description", "").strip()
        county = request.form.get("county", "").strip()
        area = request.form.get("area", "").strip()
        location = request.form.get("location", "").strip()
        if area == "Other":
            location = request.form.get("other_area", "").strip()
        elif area:
            location = area
        water_point_id = request.form.get("water_point_id", "").strip()

        county_areas = _county_areas()
        if not title or not description or not location or not county:
            flash("Complete every field before submitting your report.", "error")
        elif county not in KENYAN_COUNTIES:
            flash("Select a valid county.", "error")
        elif area and area != "Other" and area not in county_areas[county]:
            flash("Select an area in the chosen county.", "error")
        elif area == "Other" and not request.form.get("other_area", "").strip():
            flash("Enter the area where the issue occurred.", "error")
        elif category not in CATEGORIES:
            flash("Select a valid category.", "error")
        else:
            report = Report(
                user_id=current_user.id,
                community_id=None,
                water_point_id=int(water_point_id) if water_point_id else None,
                title=title,
                category=category,
                description=description,
                county=county or None,
                location=location,
                status="Pending",
            )
            db.session.add(report)
            db.session.commit()
            flash("Your report has been submitted.", "success")
            return redirect(url_for("resident_dashboard"))

    return render_template(
        "report_form.html",
        communities=communities,
        water_points=water_points,
        categories=sorted(CATEGORIES),
        counties=KENYAN_COUNTIES,
        county_areas=_county_areas(),
    )


@reports_bp.route("/my-reports")
@login_required
def resident_dashboard():
    """Show the signed-in user's reports and administrator response state."""
    allowed_statuses = ["All", "Pending", "In Progress", "Resolved"]
    selected_status = request.args.get("status", "All")
    if selected_status not in allowed_statuses:
        selected_status = "All"

    reports_query = (
        Report.query.filter_by(user_id=current_user.id)
        .order_by(Report.created_at.desc())
    )
    if selected_status != "All":
        reports_query = reports_query.filter_by(status=selected_status)

    return render_template(
        "my_reports.html",
        reports=reports_query.all(),
        allowed_statuses=allowed_statuses,
        selected_status=selected_status,
    )


@reports_bp.route("/<int:report_id>")
@login_required
def report_details(report_id: int):
    """Let residents view only their own report and admin replies."""
    report = Report.query.filter_by(
        id=report_id,
        user_id=current_user.id,
    ).first_or_404()
    return render_template("report_details.html", report=report)


__all__ = ["reports_bp", "create_report", "resident_dashboard", "report_details"]

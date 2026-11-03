"""Administrator routes for reviewing and responding to reports."""

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Report, ReportReply, SupportMessage, WaterPoint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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

    return render_template(
        "admin_dashboard.html",
        allowed_statuses=allowed_statuses,
        selected_status=selected_status,
        reports=reports,
        summary=summary,
        support_messages=support_messages,
    )


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
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        county = request.form.get("county", "").strip()
        location = request.form.get("location", "").strip()
        water_type = request.form.get("water_type", "").strip()
        status = request.form.get("status", "").strip()

        if not name:
            flash("Water point name is required.", "error")
        elif not location:
            flash("Location is required.", "error")
        elif not county:
            flash("County is required.", "error")
        elif not water_type:
            flash("Water source type is required.", "error")
        elif status not in {"Operational", "Needs Inspection", "Out of Service"}:
            flash("Select a valid status.", "error")
        else:
            water_point = WaterPoint(
                name=name,
                county=county,
                location=location,
                water_type=water_type,
                status=status,
            )
            db.session.add(water_point)
            db.session.commit()
            flash(f"Water point '{name}' added successfully.", "success")
            return redirect(url_for("admin.water_points"))

    counties = KENYAN_COUNTIES
    water_points = WaterPoint.query.order_by(WaterPoint.name.asc()).all()
    return render_template(
        "admin_water_points.html",
        counties=counties,
        water_points=water_points,
    )


__all__ = [
    "admin_bp",
    "admin_dashboard",
    "update_report_status",
    "respond_to_report",
    "report_details",
    "get_admin_reply",
    "water_points",
]

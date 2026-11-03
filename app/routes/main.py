"""Public homepage route."""

from flask import Blueprint, render_template, request

from app import KENYAN_COUNTIES
from app.models import Community, Report, WaterPoint

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Render the public homepage with featured communities and stats."""
    communities = Community.query.order_by(Community.name.asc()).limit(6).all()
    water_points = WaterPoint.query.limit(9).all()
    total_reports = Report.query.count()
    pending_reports = Report.query.filter_by(status="Pending").count()
    return render_template(
        "index.html",
        water_points=water_points,
        total_reports=total_reports,
        pending_reports=pending_reports,
        communities=communities,
        counties=KENYAN_COUNTIES,
        selected_county=request.args.get("county", ""),
    )


__all__ = ["main_bp", "index"]

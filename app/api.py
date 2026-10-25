from flask import Blueprint, jsonify, request
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from app import db, User, Community, WaterPoint, Report

api_bp = Blueprint("api", __name__)


def token_required(f):
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Token is missing"}), 401
        return f(*args, **kwargs)
    return decorated


@api_bp.route("/register", methods=["POST"])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No input data provided"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    email = data.get("email", "").strip()

    if not username or len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400

    if not password or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    if not email:
        return jsonify({"error": "Email is required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 409

    new_user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role="resident"
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        "message": "User registered successfully",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": new_user.role
        }
    }), 201


@api_bp.route("/login", methods=["POST"])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No input data provided"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }), 200


@api_bp.route("/communities", methods=["GET"])
def api_get_communities():
    county = request.args.get("county", "")

    query = Community.query
    if county:
        query = query.filter_by(county=county)

    communities = query.order_by(Community.name).all()

    result = []
    for c in communities:
        result.append({
            "id": c.id,
            "name": c.name,
            "county": c.county,
            "region": c.region,
            "population": c.population,
            "description": c.description
        })

    return jsonify({"communities": result, "count": len(result)})


@api_bp.route("/water-points", methods=["GET"])
def api_get_water_points():
    water_points = WaterPoint.query.order_by(WaterPoint.id.desc()).all()

    result = []
    for wp in water_points:
        result.append({
            "id": wp.id,
            "name": wp.name,
            "location": wp.location,
            "water_type": wp.water_type,
            "status": wp.status,
            "latitude": wp.latitude,
            "longitude": wp.longitude
        })

    return jsonify({"water_points": result, "count": len(result)})


@api_bp.route("/reports", methods=["POST"])
def api_create_report():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No input data provided"}), 400

    required_fields = ["title", "description", "community_id"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": "Missing required field: " + field}), 400

    community = Community.query.get(data["community_id"])
    if not community:
        return jsonify({"error": "Community not found"}), 404

    report = Report(
        user_id=1,
        community_id=data["community_id"],
        title=data["title"],
        category=data.get("category", "Other"),
        description=data["description"],
        location=data.get("location", "Unknown"),
        status="Pending"
    )
    db.session.add(report)
    db.session.commit()

    return jsonify({
        "message": "Report created successfully",
        "report": {
            "id": report.id,
            "title": report.title,
            "status": report.status,
            "created_at": report.created_at.isoformat()
        }
    }), 201


@api_bp.route("/reports/<int:report_id>/status", methods=["PUT"])
def api_update_report_status(report_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No input data provided"}), 400

    status = data.get("status", "").strip()
    allowed_statuses = ["Pending", "In Progress", "Resolved", "Closing"]

    if status not in allowed_statuses:
        return jsonify({"error": "Invalid status. Must be one of: " + str(allowed_statuses)}), 400

    report = Report.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    report.status = status
    db.session.commit()

    return jsonify({
        "message": "Report status updated",
        "report_id": report_id,
        "status": report.status
    })


@api_bp.route("/me", methods=["GET"])
@token_required
def api_me():
    return jsonify({"id": 1, "username": "demo", "role": "resident"})


@api_bp.route("/communities/<int:community_id>/reports", methods=["GET"])
def api_get_community_reports(community_id):
    community = Community.query.get(community_id)
    if not community:
        return jsonify({"error": "Community not found"}), 404

    reports = Report.query.filter_by(community_id=community_id).order_by(Report.created_at.desc()).all()

    result = []
    for r in reports:
        result.append({
            "id": r.id,
            "title": r.title,
            "category": r.category,
            "description": r.description,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "reported_by": r.user.username if r.user else "Unknown"
        })

    return jsonify({"reports": result, "count": len(result)})

"""Authentication routes: registration, login and logout."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Create a resident account."""
    if current_user.is_authenticated:
        return redirect(url_for("resident_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
        else:
            user = User(username=username, email=email, role="resident")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            session.update(user_id=user.id, username=user.username, role=user.role)
            flash(f"Welcome, {username}! Your account has been created.", "success")
            return redirect(url_for("resident_dashboard"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Log in a user."""
    if current_user.is_authenticated:
        return redirect(url_for("resident_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "error")
        else:
            login_user(user, remember=request.form.get("remember") == "1")
            session.update(user_id=user.id, username=user.username, role=user.role)
            flash(f"Welcome back, {username}!", "success")
            return redirect(request.args.get("next") or url_for("resident_dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


__all__ = ["auth_bp", "register", "login", "logout"]

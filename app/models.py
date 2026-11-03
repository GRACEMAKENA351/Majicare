"""SQLAlchemy models for the MajiCare application."""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Text, unique=True, nullable=False)
    email = db.Column(db.Text, nullable=True)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="resident")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))

    reports = db.relationship("Report", back_populates="user", foreign_keys="Report.user_id")
    support_messages = db.relationship(
        "SupportMessage", back_populates="user", foreign_keys="SupportMessage.user_id"
    )
    report_replies = db.relationship(
        "ReportReply", back_populates="responder", foreign_keys="ReportReply.responder_id"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username!r}>"


class Community(db.Model):
    __tablename__ = "communities"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, unique=True, nullable=False)
    county = db.Column(db.Text, nullable=False)
    region = db.Column(db.Text, nullable=False)
    population = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))

    water_points = db.relationship(
        "WaterPoint", back_populates="community", foreign_keys="WaterPoint.community_id"
    )
    reports = db.relationship("Report", back_populates="community", foreign_keys="Report.community_id")

    def __repr__(self) -> str:
        return f"<Community {self.name!r}>"


class WaterPoint(db.Model):
    __tablename__ = "water_points"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=True)
    county = db.Column(db.Text, nullable=True)
    location = db.Column(db.Text, nullable=False)
    water_type = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default="Operational")
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))

    community = db.relationship("Community", back_populates="water_points")
    reports = db.relationship(
        "Report", back_populates="water_point", foreign_keys="Report.water_point_id"
    )

    def __repr__(self) -> str:
        return f"<WaterPoint {self.name!r}>"


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=True)
    water_point_id = db.Column(db.Integer, db.ForeignKey("water_points.id"), nullable=True)
    title = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, nullable=False, default="Other")
    description = db.Column(db.Text, nullable=False)
    county = db.Column(db.Text, nullable=True)
    location = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="reports", foreign_keys="Report.user_id")
    community = db.relationship("Community", back_populates="reports", foreign_keys="Report.community_id")
    water_point = db.relationship(
        "WaterPoint", back_populates="reports", foreign_keys="Report.water_point_id"
    )
    replies = db.relationship(
        "ReportReply",
        back_populates="report",
        order_by="ReportReply.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Report {self.id!r}: {self.title!r}>"


class SupportMessage(db.Model):
    """In-app messages residents send to the admin team."""

    __tablename__ = "support_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="support_messages", foreign_keys="SupportMessage.user_id")

    def __repr__(self) -> str:
        return f"<SupportMessage {self.id!r} by {self.user_id!r}>"
class ReportReply(db.Model):
    """Admin responses to resident water reports."""

    __tablename__ = "report_replies"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False)
    responder_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    report = db.relationship("Report", back_populates="replies")
    responder = db.relationship("User", back_populates="report_replies")
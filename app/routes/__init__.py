from .admin import admin_bp, admin_dashboard, update_report_status, respond_to_report, get_admin_reply  # noqa: F401
from .auth import auth_bp, login, logout, register  # noqa: F401
from .main import main_bp, index  # noqa: F401
from .reports import reports_bp, create_report, resident_dashboard  # noqa: F401

__all__: list[str] = [
    "index",
    "register",
    "login",
    "logout",
    "resident_dashboard",
    "create_report",
    "admin_dashboard",
    "update_report_status",
    "respond_to_report",
    "get_admin_reply",
]

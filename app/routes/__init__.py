from .admin import admin_dashboard, update_report_status
from .auth import login, logout, register
from .main import index
from .reports import create_report, resident_dashboard

__all__ = [
    "index",
    "register",
    "login",
    "logout",
    "resident_dashboard",
    "create_report",
    "admin_dashboard",
    "update_report_status",
]

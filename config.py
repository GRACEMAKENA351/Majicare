import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SQLITE_URI = "sqlite:///" + str(BASE_DIR / "instance" / "majicare.db")

# Stable SECRET_KEY for local development. The README instructs developers to
# export SECRET_KEY as an environment variable in production; that value takes
# precedence. For local sessions, this default keeps the app deterministic
# without a real (committed) secret.
SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-do-not-use-in-prod"


class Config:
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", SQLITE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Flask-WTF CSRF: disabled for the JSON API responses in this project, but
    # the template forms still use it through Flask-WTF when enabled.
    WTF_CSRF_ENABLED = os.environ.get("WTF_CSRF_ENABLED", "false").lower() == "true"
    WTF_CSRF_TIME_LIMIT = None


class DevelopmentConfig(Config):
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    SQLALCHEMY_ECHO = False
    WTF_CSRF_ENABLED = True

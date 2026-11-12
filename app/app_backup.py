# Application factory and shared utilities for the MajiCare Flask app.

import os
import secrets
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, current_app, flash, g, redirect, render_template, request, session, url_for,
)
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "instance" / "majicare.db"

KENYAN_COUNTIES = (
    "Baringo County",
    "Bomet County",
    "Bungoma County",
    "Busia County",
    "Elgeyo-Marakwet County",
    "Embu County",
    "Garissa County",
    "Homa Bay County",
    "Isiolo County",
    "Kajiado County",
    "Kakamega County",
    "Kericho County",
    "Kiambu County",
    "Kilifi County",
    "Kirinyaga County",
    "Kisii County",
    "Kisumu County",
    "Kitui County",
    "Kwale County",
    "Laikipia County",
    "Lamu County",
    "Machakos County",
    "Makueni County",
    "Mandera County",
    "Marsabit County",
    "Meru County",
    "Migori County",
    "Mombasa County",
    "Murang'a County",
    "Nairobi City County",
    "Nakuru County",
    "Nandi County",
    "Narok County",
    "Nyamira County",
    "Nyandarua County",
    "Nyeri County",
    "Samburu County",
    "Siaya County",
    "Taita-Taveta County",
    "Tana River County",
    "Tharaka-Nithi County",
    "Trans Nzoia County",
    "Turkana County",
    "Uasin Gishu County",
    "Vihiga County",
    "Wajir County",
    "West Pokot County",
)

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

def get_db():
    """Return the current application context's SQLite connection (for schemas)."""
    import sqlite3

    if "db" not in g:
        db_path = Path(current_app.config.get("DATABASE", DATABASE))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(db_path))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    """Create the schema and seed data using a raw sqlite3 connection."""
    db = get_db()
    db.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'resident',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            county TEXT NOT NULL,
            region TEXT NOT NULL,
            population INTEGER,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS water_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            community_id INTEGER,
            county TEXT,
            location TEXT NOT NULL,
            water_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Operational',
            latitude REAL,
            longitude REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(community_id) REFERENCES communities(id)
        );

        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            responder_id INTEGER NOT NULL,
            responder_role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
            FOREIGN KEY(responder_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            community_id INTEGER NOT NULL,
            water_point_id INTEGER,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            county TEXT,
            location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            last_admin_reply_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(community_id) REFERENCES communities(id),
            FOREIGN KEY(water_point_id) REFERENCES water_points(id)
        );

        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )

    water_point_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(water_points)").fetchall()
    }
    if "community_id" not in water_point_columns:
        db.execute("ALTER TABLE water_points ADD COLUMN community_id INTEGER")

    locations_to_communities = {
        row["id"]: row["name"]
        for row in db.execute(
            "SELECT id, name FROM communities WHERE name IS NOT NULL AND name != ''"
        ).fetchall()
    }
    for point in db.execute(
        "SELECT id, location, community_id FROM water_points WHERE community_id IS NULL"
    ).fetchall():
        community_id = locations_to_communities.get(point["location"])
        if community_id is not None:
            db.execute(
                "UPDATE water_points SET community_id = ? WHERE id = ?",
                (community_id, point["id"]),
            )




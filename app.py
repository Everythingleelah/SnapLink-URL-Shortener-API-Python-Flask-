"""
SnapLink — URL Shortener REST API
A clean, production-ready URL shortener built with Flask + SQLite.
Author: Deborah Lambert | License: MIT
"""

import hashlib
import os
import re
import sqlite3
import string
import random
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify, redirect, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ──────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────

DATABASE = os.environ.get("SNAPLINK_DB", "snaplink.db")
BASE_URL = os.environ.get("SNAPLINK_BASE_URL", "http://localhost:5000")
SECRET_KEY = os.environ.get("SNAPLINK_SECRET", "dev-secret-change-in-production")
ALIAS_MAX_LENGTH = 20
ALIAS_MIN_LENGTH = 3

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# ──────────────────────────────────────────
# Database
# ──────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    UNIQUE NOT NULL,
            original    TEXT    NOT NULL,
            title       TEXT,
            clicks      INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now')),
            expires_at  TEXT,
            is_active   INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS clicks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    NOT NULL,
            ip_hash     TEXT,
            referrer    TEXT,
            user_agent  TEXT,
            clicked_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_links_code ON links(code);
        CREATE INDEX IF NOT EXISTS idx_clicks_code ON clicks(code);
    """)
    db.commit()
    db.close()


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def generate_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def is_valid_url(url: str) -> bool:
    pattern = re.compile(
        r"^https?://"
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
        r"localhost|"
        r"\d{1,3}(?:\.\d{1,3}){3})"
        r"(?::\d+)?"
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(pattern.match(url))


def is_valid_alias(alias: str) -> bool:
    if not (ALIAS_MIN_LENGTH <= len(alias) <= ALIAS_MAX_LENGTH):
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", alias))


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def error(message: str, code: int = 400) -> tuple:
    return jsonify({"success": False, "error": message}), code


def success(data: dict, code: int = 200) -> tuple:
    return jsonify({"success": True, **data}), code


# ──────────────────────────────────────────
# Routes — Link Management
# ──────────────────────────────────────────

@app.post("/api/shorten")
@limiter.limit("20 per minute")
def shorten():
    """Create a shortened URL."""
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    alias = (body.get("alias") or "").strip()
    title = (body.get("title") or "").strip()
    expires_at = body.get("expires_at")

    if not url:
        return error("Field 'url' is required.")
    if not is_valid_url(url):
        return error("Invalid URL. Must start with http:// or https://")

    db = get_db()

    if alias:
        if not is_valid_alias(alias):
            return error(
                f"Alias must be {ALIAS_MIN_LENGTH}–{ALIAS_MAX_LENGTH} characters "
                "and contain only letters, numbers, hyphens, or underscores."
            )
        existing = db.execute("SELECT 1 FROM links WHERE code = ?", (alias,)).fetchone()
        if existing:
            return error(f"Alias '{alias}' is already taken.", 409)
        code = alias
    else:
        for _ in range(10):
            code = generate_code()
            if not db.execute("SELECT 1 FROM links WHERE code = ?", (code,)).fetchone():
                break
        else:
            return error("Could not generate a unique code. Please try again.", 500)

    db.execute(
        "INSERT INTO links (code, original, title, expires_at) VALUES (?, ?, ?, ?)",
        (code, url, title or None, expires_at),
    )
    db.commit()

    return success(
        {
            "short_url": f"{BASE_URL}/{code}",
            "code": code,
            "original": url,
            "title": title or None,
            "expires_at": expires_at,
            "created_at": datetime.utcnow().isoformat(),
        },
        201,
    )


@app.get("/api/links")
def list_links():
    """List all active shortened links with basic stats."""
    db = get_db()
    rows = db.execute(
        "SELECT code, original, title, clicks, created_at, expires_at "
        "FROM links WHERE is_active = 1 ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    links = [
        {
            "short_url": f"{BASE_URL}/{r['code']}",
            "code": r["code"],
            "original": r["original"],
            "title": r["title"],
            "clicks": r["clicks"],
            "created_at": r["created_at"],
            "expires_at": r["expires_at"],
        }
        for r in rows
    ]
    return success({"links": links, "count": len(links)})


@app.get("/api/links/<code>")
def get_link(code: str):
    """Get details for a single link."""
    db = get_db()
    row = db.execute(
        "SELECT code, original, title, clicks, created_at, expires_at, is_active "
        "FROM links WHERE code = ?",
        (code,),
    ).fetchone()
    if not row:
        return error("Link not found.", 404)

    recent_clicks = db.execute(
        "SELECT clicked_at, referrer FROM clicks WHERE code = ? ORDER BY clicked_at DESC LIMIT 10",
        (code,),
    ).fetchall()

    return success(
        {
            "short_url": f"{BASE_URL}/{code}",
            "code": row["code"],
            "original": row["original"],
            "title": row["title"],
            "clicks": row["clicks"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "is_active": bool(row["is_active"]),
            "recent_clicks": [dict(r) for r in recent_clicks],
        }
    )


@app.delete("/api/links/<code>")
def delete_link(code: str):
    """Soft-delete (deactivate) a link."""
    db = get_db()
    row = db.execute("SELECT id FROM links WHERE code = ?", (code,)).fetchone()
    if not row:
        return error("Link not found.", 404)
    db.execute("UPDATE links SET is_active = 0 WHERE code = ?", (code,))
    db.commit()
    return success({"message": f"Link '{code}' deactivated."})


@app.get("/api/stats")
def global_stats():
    """Return global statistics."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM links WHERE is_active = 1").fetchone()[0]
    total_clicks = db.execute("SELECT SUM(clicks) FROM links").fetchone()[0] or 0
    top = db.execute(
        "SELECT code, original, clicks FROM links ORDER BY clicks DESC LIMIT 5"
    ).fetchall()
    return success(
        {
            "total_links": total,
            "total_clicks": total_clicks,
            "top_links": [
                {"code": r["code"], "original": r["original"], "clicks": r["clicks"]}
                for r in top
            ],
        }
    )


# ──────────────────────────────────────────
# Routes — Redirect
# ──────────────────────────────────────────

@app.get("/<code>")
def redirect_link(code: str):
    """Redirect short code to original URL and record the click."""
    db = get_db()
    row = db.execute(
        "SELECT original, expires_at, is_active FROM links WHERE code = ?", (code,)
    ).fetchone()

    if not row or not row["is_active"]:
        return jsonify({"error": "Link not found or has been deactivated."}), 404

    if row["expires_at"] and row["expires_at"] < datetime.utcnow().isoformat():
        return jsonify({"error": "This link has expired."}), 410

    db.execute("UPDATE links SET clicks = clicks + 1 WHERE code = ?", (code,))
    db.execute(
        "INSERT INTO clicks (code, ip_hash, referrer, user_agent) VALUES (?, ?, ?, ?)",
        (
            code,
            hash_ip(request.remote_addr or ""),
            request.referrer or None,
            request.user_agent.string[:200] if request.user_agent else None,
        ),
    )
    db.commit()
    return redirect(row["original"], 302)


# ──────────────────────────────────────────
# Health check
# ──────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "SnapLink", "version": "1.0.0"})


# ──────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("✓ SnapLink API running at http://localhost:5000")
    print("  POST /api/shorten   — Create a short link")
    print("  GET  /api/links     — List all links")
    print("  GET  /api/stats     — Global stats")
    print("  GET  /<code>        — Redirect")
    app.run(debug=True, port=5000)

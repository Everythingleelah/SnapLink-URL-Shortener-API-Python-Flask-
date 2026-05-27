# SnapLink URL Shortener REST API 🔗

A production-ready URL shortener REST API built with **Flask + SQLite**. Clean architecture, rate limiting, click analytics, and full CRUD support.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask) ![SQLite](https://img.shields.io/badge/SQLite-lightblue?logo=sqlite) ![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- ✂️ **URL shortening** with random or custom aliases
- 📊 **Click analytics** — total clicks, recent click history, referrer tracking
- ⏳ **Link expiration** — set TTL on any link
- 🚦 **Rate limiting** — 20 shorten requests per minute per IP
- 🗑️ **Soft delete** — deactivate links without losing analytics
- 🔒 **Privacy-first** — IP addresses stored as hashed values only
- ❤️ **Health endpoint** — `/health` for uptime monitoring

---

## Quick Start

```bash
git clone https://github.com/yourusername/snaplink-api.git
cd snaplink-api
pip install -r requirements.txt
python app.py
```

The API runs at `http://localhost:5000`.

---

## API Reference

### `POST /api/shorten`

Create a shortened URL.

**Request Body:**
```json
{
  "url": "https://example.com/very/long/path?query=value",
  "alias": "my-link",          // optional custom alias
  "title": "My Homepage",      // optional
  "expires_at": "2025-12-31"   // optional ISO date
}
```

**Response:**
```json
{
  "success": true,
  "short_url": "http://localhost:5000/my-link",
  "code": "my-link",
  "original": "https://example.com/very/long/path?query=value",
  "created_at": "2024-12-15T10:30:00"
}
```

---

### `GET /api/links`

List all active links (up to 50, most recent first).

---

### `GET /api/links/<code>`

Get full details for a link including recent click history.

---

### `DELETE /api/links/<code>`

Soft-delete (deactivate) a link.

---

### `GET /api/stats`

Return global stats: total links, total clicks, and top 5 most-clicked links.

---

### `GET /<code>`

Redirect to the original URL. Records click with timestamp, referrer, and hashed IP.

---

## cURL Examples

```bash
# Shorten a URL
curl -X POST http://localhost:5000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com", "alias": "gh"}'

# Get link stats
curl http://localhost:5000/api/links/gh

# Global stats
curl http://localhost:5000/api/stats

# Delete a link
curl -X DELETE http://localhost:5000/api/links/gh
```

---

## Project Structure

```
snaplink-api/
├── app.py              # Main Flask application
├── requirements.txt    # Dependencies
├── tests/
│   └── test_api.py     # Pytest test suite
└── README.md
```

---

## Database Schema

**links** table: `id, code, original, title, clicks, created_at, expires_at, is_active`

**clicks** table: `id, code, ip_hash, referrer, user_agent, clicked_at`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SNAPLINK_DB` | `snaplink.db` | Path to SQLite database |
| `SNAPLINK_BASE_URL` | `http://localhost:5000` | Base URL for short links |
| `SNAPLINK_SECRET` | `dev-secret` | Flask secret key |

---

## Deployment

```bash
# Production with gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

For production, swap SQLite for PostgreSQL using SQLAlchemy.

---

## License

MIT.

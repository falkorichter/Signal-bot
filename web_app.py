#!/usr/bin/env python3
"""web_app.py — Flask web dashboard for the Signal FAQ Bot.

Shows every processed message with its full pipeline in near-real time.
The dashboard auto-refreshes every 5 seconds; no WebSocket required.

Usage::

    python web_app.py [--host HOST] [--port PORT] [--debug]

The bot (bot.py) and the dashboard read/write the same ``data/sessions.json``
file and can run in separate terminals simultaneously.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, abort, jsonify, render_template

from storage import SessionStore

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Each web_app process gets its own read-view of the store.
# The bot writes; this process reads.  The store reloads from disk on
# every request so the dashboard always shows the latest data.
_store = SessionStore()


# ---------------------------------------------------------------------------
# Helper: reload from disk before each read so we always see bot writes
# ---------------------------------------------------------------------------

def _fresh_store() -> SessionStore:
    """Return a store whose in-memory cache is refreshed from disk."""
    # Re-load unconditionally — cheap because sessions.json is small.
    store = SessionStore()
    return store


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def dashboard():
    """Serve the single-page dashboard shell."""
    return render_template("index.html")


@app.route("/api/sessions")
def api_sessions():
    """Return all sessions as a JSON array, newest first."""
    store = _fresh_store()
    sessions = store.get_all_sessions()
    return jsonify([s.to_dict() for s in sessions])


@app.route("/api/sessions/<session_id>")
def api_session(session_id: str):
    """Return a single session by ID."""
    store = _fresh_store()
    session = store.get_session(session_id)
    if session is None:
        abort(404, description=f"Session '{session_id}' not found")
    return jsonify(session.to_dict())


@app.route("/api/stats")
def api_stats():
    """Return aggregate statistics as JSON."""
    store = _fresh_store()
    sessions = store.get_all_sessions()
    return jsonify(
        {
            "total": len(sessions),
            "questions": sum(1 for s in sessions if s.is_question is True),
            "non_questions": sum(1 for s in sessions if s.is_question is False),
            "pending": sum(1 for s in sessions if s.is_question is None),
            "replied": sum(1 for s in sessions if s.replied),
            "errors": sum(1 for s in sessions if s.error),
        }
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": str(err)}), 404


@app.errorhandler(500)
def internal_error(err):
    logger.error("Internal server error: %s", err)
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description="Signal FAQ Bot — Web Dashboard")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Listen port (default: 5000)"
    )
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = parser.parse_args()

    logger.info("Dashboard → http://%s:%d/", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

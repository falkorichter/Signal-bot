#!/usr/bin/env python3
"""web_app.py -- Flask web dashboard for the Signal FAQ Bot.

Provides a live session list, a benchmark/test panel, token visualisation,
and a config inspector.  The bot (bot.py) and the dashboard share
data/sessions.json and can run in separate terminals simultaneously.

Usage::

    python web_app.py [--host HOST] [--port PORT] [--debug]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, abort, jsonify, render_template, request

from storage import SessionStore

logger = logging.getLogger(__name__)

app = Flask(__name__)


def _fresh_store() -> SessionStore:
    """Return a SessionStore freshly loaded from disk."""
    return SessionStore()


@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/api/sessions")
def api_sessions():
    store = _fresh_store()
    return jsonify([s.to_dict() for s in store.get_all_sessions()])


@app.route("/api/sessions/<session_id>")
def api_session(session_id: str):
    store = _fresh_store()
    session = store.get_session(session_id)
    if session is None:
        abort(404, description=f"Session '{session_id}' not found")
    return jsonify(session.to_dict())


@app.route("/api/stats")
def api_stats():
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
            "test_runs": sum(1 for s in sessions if s.is_test),
        }
    )


@app.route("/api/config")
def api_config():
    from config import (
        BOT_LANGUAGE,
        CALENDAR_COMMAND,
        LLM_COMMAND,
        MONITOR_GROUP,
        POLL_INTERVAL,
        QUESTION_CHECK_COMMAND,
        SIGNAL_NUMBER,
        TOKEN_WINDOW,
    )
    return jsonify(
        {
            "signal_number": SIGNAL_NUMBER or "(not set)",
            "monitor_group": MONITOR_GROUP or "(all)",
            "bot_language": BOT_LANGUAGE,
            "poll_interval": POLL_INTERVAL,
            "token_window": TOKEN_WINDOW,
            "question_check_command": QUESTION_CHECK_COMMAND,
            "calendar_command": CALENDAR_COMMAND,
            "llm_command": LLM_COMMAND,
        }
    )


@app.route("/api/benchmark", methods=["POST"])
def api_benchmark():
    """Run the full bot pipeline for a manually entered message.

    Request body (JSON): {"message": "What are the opening hours?"}

    Returns the Session dict after all pipeline steps complete.
    The session is flagged is_test=true and no real Signal DM is sent.
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        abort(400, description="'message' field is required and must not be empty")

    from bot import run_pipeline

    store = _fresh_store()
    try:
        session = run_pipeline(
            message_text=message,
            sender="benchmark-ui",
            group_id="",
            store=store,
            is_test=True,
            send_dm=False,
        )
        return jsonify(session.to_dict()), 200
    except Exception as exc:
        logger.error("Benchmark pipeline error: %s", exc, exc_info=True)
        # Do not expose internal exception details (stack traces) to clients.
        return jsonify({"error": "Pipeline execution failed. Check server logs for details."}), 500


@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": str(err)}), 400


@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": str(err)}), 404


@app.errorhandler(500)
def internal_error(err):
    logger.error("Internal server error: %s", err)
    return jsonify({"error": "Internal server error"}), 500


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description="Signal FAQ Bot -- Web Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=5000, help="Listen port")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = parser.parse_args()
    logger.info("Dashboard at http://%s:%d/", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

"""
Voice-Based Email - Web Interface
Flask + Web Speech API (mic/voice runs in the browser; this server only
talks to your inbox). Shares its email-parsing logic with main.py (CLI)
via email_logic.py, so voice commands behave identically in both.

Run:  python app.py
Open: http://127.0.0.1:5000   (use Chrome or Edge - Web Speech API only)
"""
import os
from flask import Flask, render_template, request, jsonify

from email_client_smtp import SMTPEmailClient
from email_logic import CONTACTS, is_yes, clean_email_spoken, resolve_contact, spell_out

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "voice-email-dev")

EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")

_client = None  # lazily-built SMTPEmailClient, cached for the process


def is_configured():
    return bool(EMAIL_USER and EMAIL_PASS)


def get_client():
    global _client
    if _client is None and is_configured():
        _client = SMTPEmailClient(EMAIL_USER, EMAIL_PASS, SMTP_SERVER, SMTP_PORT, IMAP_SERVER)
    return _client


@app.route("/")
def index():
    return render_template(
        "index.html",
        email_user=EMAIL_USER if is_configured() else None,
        contacts=CONTACTS,
    )


@app.route("/api/status")
def status():
    return jsonify({
        "configured": is_configured(),
        "email": EMAIL_USER if is_configured() else None,
    })


@app.route("/api/contacts")
def contacts():
    return jsonify({k: v for k, v in CONTACTS.items() if v})


@app.route("/api/inbox", methods=["GET", "POST"])
def api_inbox():
    if not is_configured():
        return jsonify({"ok": False, "error": "Email not configured. Set EMAIL_USER / EMAIL_PASS in .env"}), 400
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 8))
    unread_only = bool(data.get("unread_only", False))
    try:
        emails = get_client().read_inbox(limit=limit, unread_only=unread_only)
    except Exception as e:
        # real errors are reported as errors, never disguised as a fake email
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "count": len(emails), "emails": emails})


@app.route("/api/send", methods=["POST"])
def api_send():
    if not is_configured():
        return jsonify({"ok": False, "error": "Email not configured. Set EMAIL_USER / EMAIL_PASS in .env"}), 400
    d = request.get_json(force=True) or {}
    to_raw = (d.get("to") or "").strip()
    subject = (d.get("subject") or "").strip() or "Voice email"
    body = (d.get("body") or "").strip() or "(sent by voice)"

    # same recipient resolution as the CLI: contact name -> address,
    # or accurate spoken-email parsing ("ram at gmail dot com")
    to, confident = resolve_contact(to_raw)
    if not to or "@" not in to:
        return jsonify({"ok": False, "error": f"Could not resolve a valid email from: {to_raw!r}"}), 400

    ok, msg = get_client().send_email(to, subject, body)
    return jsonify({"ok": ok, "message": msg, "to": to}), (200 if ok else 500)


@app.route("/api/parse_email", methods=["POST"])
def parse_email():
    """Spoken/typed recipient -> resolved address. Mirrors the CLI's
    resolve_contact()/clean_email_spoken() exactly, so 'mom' or
    'ram at gmail dot com' resolve the same way in both interfaces."""
    spoken = (request.get_json(force=True) or {}).get("text", "")
    if not spoken:
        return jsonify({"ok": False, "valid": False})
    email, confident = resolve_contact(spoken)
    return jsonify({
        "ok": True,
        "email": email,
        "valid": bool(email and confident),
        "spelled": spell_out(email) if email else None,
        "raw": spoken,
    })


@app.route("/api/parse_yes_no", methods=["POST"])
def parse_yes_no():
    text = (request.get_json(force=True) or {}).get("text", "")
    return jsonify({"result": is_yes(text)})


if __name__ == "__main__":
    print("=" * 58)
    print("  Voice Email - Web Interface")
    print("=" * 58)
    print(f"  Email : {EMAIL_USER if is_configured() else 'NOT CONFIGURED - edit .env'}")
    print("  Open  : http://127.0.0.1:5000")
    print("=" * 58)
    app.run(host="0.0.0.0", port=5000, debug=True)

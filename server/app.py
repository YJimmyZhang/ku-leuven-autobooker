"""
KU Leuven Autobooker – Webhook Receiver + Scheduled Booker

Run locally:
    pip install -r requirements.txt
    python app.py

For production, deploy behind HTTPS (e.g. Railway, Fly.io, a VPS) and point
the extension's WEBHOOK_URL to your public /update-cookie endpoint.
"""

import json
import logging
import os
import random
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import schedule
from flask import Flask, jsonify, request, send_file

# =============================================================================
# Configuration – fill in the TODO placeholders below
# =============================================================================

# Shared secret – must match SECRET_KEY in extension/background.js
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-before-deploy")

# Shibboleth session cookie (name suffix is stable for kurt3.ghum.kuleuven.be)
SESSION_COOKIE_NAME = "_shibsession"

BOOKING_URL = "https://kurt3.ghum.kuleuven.be/api/reservations/"

# --- Seat & time slot ---------------------------------------------------------
# Slots open at 18:00 for the day exactly 8 days ahead (e.g. Mon 18:00 → next Tue).
RESOURCE_ID = 300908
RESOURCE_NAME = "Agora - Silent Study Seat 155"
BUILDING_NAME = "Agora Learning Centre"

PARTICIPANT_UID = os.environ.get("PARTICIPANT_UID", "YOUR_STUDENT_ID")
PARTICIPANT_EMAIL = os.environ.get("PARTICIPANT_EMAIL", "you@student.kuleuven.be")

START_TIME = "10:00"
END_TIME = "18:00"
# Days after the 18:00 trigger (KU Leuven opens Agora slots 8 days in advance)
BOOKING_DATE_OFFSET_DAYS = 8

# Path to persist the captured cookie across server restarts
COOKIE_STORE_PATH = Path(
    os.environ.get("COOKIE_STORE_PATH", str(Path(__file__).parent / "cookie_store.json"))
)

# Random delay before firing the booking request (milliseconds → seconds)
BOOKING_DELAY_MIN_MS = 100
BOOKING_DELAY_MAX_MS = 400

# Daily trigger time (24-hour clock, server local timezone).
# On cloud hosts, set TZ=Europe/Brussels so 18:00 is Belgian time.
BOOKING_TIME = "18:00:00"

# --- When to book (exam period / manual off switch) -----------------------------
# Set BOOKING_ENABLED=false to keep the server running but skip 18:00 bookings.
BOOKING_ENABLED = os.environ.get("BOOKING_ENABLED", "true").lower() in ("1", "true", "yes")
# Only book while today AND the target slot date fall within this window (optional).
BOOKING_PERIOD_START = os.environ.get("BOOKING_PERIOD_START", "")  # e.g. 2026-06-01
BOOKING_PERIOD_END = os.environ.get("BOOKING_PERIOD_END", "")    # e.g. 2026-07-15

# --- KU Leuven quota (Study Seat: max 16h/booking; 48h future pre-bookable/week) -
WEEKLY_FUTURE_HOUR_LIMIT = int(os.environ.get("WEEKLY_FUTURE_HOUR_LIMIT", "48"))
MAX_HOURS_PER_BOOKING = int(os.environ.get("MAX_HOURS_PER_BOOKING", "16"))

# --- Check-in (required within 30 min of START_TIME on the booking day) ---------
CHECKIN_BASE_URL = "https://kurt3.ghum.kuleuven.be/check-in/"
CHECKIN_WINDOW_MINUTES = 30

STATE_STORE_PATH = Path(
    os.environ.get("STATE_STORE_PATH", str(Path(__file__).parent / "scheduler_state.json"))
)

RUNTIME_CONFIG_PATH = Path(
    os.environ.get("RUNTIME_CONFIG_PATH", str(Path(__file__).parent / "runtime_config.json"))
)

ADMIN_HTML_PATH = Path(__file__).parent / "admin.html"


def default_settings() -> dict:
    """Defaults from env / hardcoded seat config (first boot)."""
    return {
        "booking_enabled": os.environ.get("BOOKING_ENABLED", "true").lower() in ("1", "true", "yes"),
        "booking_period_start": os.environ.get("BOOKING_PERIOD_START", ""),
        "booking_period_end": os.environ.get("BOOKING_PERIOD_END", ""),
        "resource_id": RESOURCE_ID,
        "resource_name": RESOURCE_NAME,
        "building_name": BUILDING_NAME,
        "participant_uid": PARTICIPANT_UID,
        "participant_email": PARTICIPANT_EMAIL,
        "start_time": START_TIME,
        "end_time": END_TIME,
        "booking_date_offset_days": BOOKING_DATE_OFFSET_DAYS,
        "booking_time": BOOKING_TIME,
    }


def get_settings() -> dict:
    """Live settings (runtime_config.json overrides env defaults)."""
    settings = default_settings()
    if RUNTIME_CONFIG_PATH.exists():
        try:
            with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            for key, value in stored.items():
                if key in settings and value is not None:
                    settings[key] = value
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load runtime config: %s", exc)
    return settings


def save_settings(settings: dict) -> None:
    try:
        with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        os.chmod(RUNTIME_CONFIG_PATH, 0o600)
    except OSError as exc:
        log.error("Failed to save runtime config: %s", exc)


def init_runtime_config() -> None:
    if not RUNTIME_CONFIG_PATH.exists():
        save_settings(default_settings())
        log.info("Created runtime config at %s", RUNTIME_CONFIG_PATH)

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# =============================================================================
# Cookie storage (in-memory + JSON file persistence)
# =============================================================================

_cookie_store: dict = {
    "cookie_name": SESSION_COOKIE_NAME,
    "cookie_value": None,
    "cookies": {},
    "domain": None,
    "captured_at": None,
}


def normalize_cookie_store() -> None:
    """Ensure cookie jar exists (handles legacy single-cookie stores)."""
    cookies = _cookie_store.get("cookies") or {}
    if not cookies and _cookie_store.get("cookie_value"):
        name = _cookie_store.get("cookie_name", SESSION_COOKIE_NAME)
        cookies = {name: _cookie_store["cookie_value"]}
    _cookie_store["cookies"] = cookies


def booking_cookies() -> dict[str, str]:
    """Return all stored cookies for the booking request."""
    normalize_cookie_store()
    return dict(_cookie_store.get("cookies") or {})


def is_authenticated_response(response: requests.Response) -> bool:
    """True only when the API returned JSON, not a Shibboleth login page."""
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return response.ok

    body = response.text[:2000]
    login_markers = (
        "Central Login",
        "Loading Session Information",
        "<html",
        "idp.kuleuven.be",
    )
    if any(marker in body for marker in login_markers):
        return False

    return response.ok


def load_cookie_store() -> None:
    """Load persisted cookie from disk on startup."""
    global _cookie_store
    if COOKIE_STORE_PATH.exists():
        try:
            with open(COOKIE_STORE_PATH, "r", encoding="utf-8") as f:
                _cookie_store = json.load(f)
            normalize_cookie_store()
            log.info("Loaded cookie from %s (captured: %s)", COOKIE_STORE_PATH, _cookie_store.get("captured_at"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load cookie store: %s", exc)


def save_cookie_store() -> None:
    """Persist cookie to disk."""
    try:
        with open(COOKIE_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cookie_store, f, indent=2)
        # Restrict file permissions (owner read/write only)
        os.chmod(COOKIE_STORE_PATH, 0o600)
    except OSError as exc:
        log.error("Failed to save cookie store: %s", exc)


def build_booking_payload(booking_date: date) -> dict:
    """Build the JSON body matching the kurt3 /api/reservations/ contract."""
    s = get_settings()
    date_label = booking_date.strftime("%a %b %d")
    email_display = s["participant_email"].replace("@", "&commat;")

    return {
        "id": s["resource_id"],
        "resourceName": s["resource_name"],
        "subject": s["resource_name"],
        "purpose": "",
        "resourceId": s["resource_id"],
        "startDate": booking_date.isoformat(),
        "startTime": s["start_time"],
        "endDate": booking_date.isoformat(),
        "endTime": s["end_time"],
        "participants": [
            {"uid": s["participant_uid"], "email": s["participant_email"]},
        ],
        "summary": [
            f"Resource **{s['resource_name']}**",
            f"at **{s['building_name']}**",
            f"for **{email_display}**",
            f"from **{date_label} {s['start_time']}** until **{date_label} {s['end_time']}**",
        ],
        "withCheckIn": False,
    }


def booking_target_date() -> date:
    """Resolve which calendar date to book for when the trigger fires."""
    return (datetime.now() + timedelta(days=get_settings()["booking_date_offset_days"])).date()


def booking_duration_hours() -> int:
    s = get_settings()
    start_h, start_m = map(int, s["start_time"].split(":")[:2])
    end_h, end_m = map(int, s["end_time"].split(":")[:2])
    minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
    return minutes // 60


def parse_config_date(value: str) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def reservation_period() -> tuple[date | None, date | None]:
    """First/last calendar days to hold a seat (what you pick in admin)."""
    s = get_settings()
    return (
        parse_config_date(s["booking_period_start"]),
        parse_config_date(s["booking_period_end"]),
    )


def booking_run_window() -> tuple[date | None, date | None]:
    """Days when the 18:00 job may run (= seat period minus days-ahead offset)."""
    seat_start, seat_end = reservation_period()
    offset = timedelta(days=get_settings()["booking_date_offset_days"])
    run_start = (seat_start - offset) if seat_start else None
    run_end = (seat_end - offset) if seat_end else None
    return run_start, run_end


def is_target_date_in_period(target: date) -> bool:
    seat_start, seat_end = reservation_period()
    if seat_start and target < seat_start:
        return False
    if seat_end and target > seat_end:
        return False
    return True


def is_booking_active_today() -> bool:
    s = get_settings()
    if not s["booking_enabled"]:
        return False
    today = date.today()
    run_start, run_end = booking_run_window()
    if run_start and today < run_start:
        return False
    if run_end and today > run_end:
        return False
    return True


def booking_status_message() -> str:
    s = get_settings()
    if not s["booking_enabled"]:
        return "Auto-booking is turned off."
    seat_start, seat_end = reservation_period()
    run_start, run_end = booking_run_window()
    today = date.today()
    offset = s["booking_date_offset_days"]
    if run_start and today < run_start:
        return f"Starts {run_start.isoformat()} at 18:00 (books first seat on {seat_start})."
    if run_end and today > run_end:
        return f"Finished — last run was {run_end.isoformat()} (last seat {seat_end})."
    target = booking_target_date()
    if not is_target_date_in_period(target):
        return f"Tonight skipped: {target} is outside seat period."
    return f"Tonight at 18:00 → book {target} ({s['start_time']}–{s['end_time']})."


def should_attempt_booking() -> tuple[bool, str]:
    if not is_booking_active_today():
        return False, "Booking disabled or today is outside the run window (seat period minus days ahead)"

    hours = booking_duration_hours()
    if hours > MAX_HOURS_PER_BOOKING:
        return False, f"Slot is {hours}h but Study Seat max per booking is {MAX_HOURS_PER_BOOKING}h"

    target = booking_target_date()
    if not is_target_date_in_period(target):
        return False, f"Target date {target} is outside BOOKING_PERIOD"

    used = future_quota_hours_used()
    if used + hours > WEEKLY_FUTURE_HOUR_LIMIT:
        return False, (
            f"Would exceed {WEEKLY_FUTURE_HOUR_LIMIT}h future quota "
            f"({used}h booked + {hours}h new > {WEEKLY_FUTURE_HOUR_LIMIT}h). "
            "Cancel a future reservation or wait for the rolling quota."
        )

    return True, ""


# =============================================================================
# Scheduler state (quota tracker + pending check-ins)
# =============================================================================

_scheduler_state: dict = {
    "future_bookings": [],
    "pending_checkins": [],
}


def load_scheduler_state() -> None:
    global _scheduler_state
    if STATE_STORE_PATH.exists():
        try:
            with open(STATE_STORE_PATH, "r", encoding="utf-8") as f:
                _scheduler_state = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load scheduler state: %s", exc)


def save_scheduler_state() -> None:
    try:
        with open(STATE_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(_scheduler_state, f, indent=2)
        os.chmod(STATE_STORE_PATH, 0o600)
    except OSError as exc:
        log.error("Failed to save scheduler state: %s", exc)


def future_quota_hours_used() -> int:
    """Hours already reserved by this bot for days after today (KU Leuven rolling quota)."""
    today = date.today()
    total = 0
    for entry in _scheduler_state.get("future_bookings", []):
        entry_date = date.fromisoformat(entry["date"])
        if entry_date > today:
            total += int(entry["hours"])
    return total


def register_successful_booking(target: date, reservation_id: int | None) -> None:
    hours = booking_duration_hours()
    _scheduler_state.setdefault("future_bookings", []).append(
        {
            "date": target.isoformat(),
            "hours": hours,
            "reservation_id": reservation_id,
            "booked_on": datetime.now().isoformat(),
        }
    )
    if reservation_id:
        schedule_checkin(reservation_id, target)
    prune_scheduler_state()
    save_scheduler_state()


def schedule_checkin(reservation_id: int, checkin_date: date) -> None:
    s = get_settings()
    start_h, start_m = map(int, s["start_time"].split(":")[:2])
    checkin_at = datetime.combine(checkin_date, datetime.min.time()).replace(
        hour=start_h, minute=start_m
    ) + timedelta(seconds=random.randint(5, 90))

    _scheduler_state.setdefault("pending_checkins", []).append(
        {
            "reservation_id": reservation_id,
            "checkin_at": checkin_at.isoformat(),
            "deadline": (checkin_at + timedelta(minutes=CHECKIN_WINDOW_MINUTES)).isoformat(),
            "done": False,
            "url": f"{CHECKIN_BASE_URL}{reservation_id}",
        }
    )
    log.info(
        "Scheduled check-in for reservation %s at %s (deadline +%s min)",
        reservation_id,
        checkin_at.isoformat(),
        CHECKIN_WINDOW_MINUTES,
    )


def prune_scheduler_state() -> None:
    today = date.today()
    _scheduler_state["future_bookings"] = [
        e
        for e in _scheduler_state.get("future_bookings", [])
        if date.fromisoformat(e["date"]) >= today
    ]
    cutoff = datetime.now() - timedelta(days=2)
    kept = []
    for item in _scheduler_state.get("pending_checkins", []):
        if item.get("done"):
            deadline = datetime.fromisoformat(item["deadline"])
            if deadline >= cutoff:
                kept.append(item)
        else:
            kept.append(item)
    _scheduler_state["pending_checkins"] = kept


def extract_reservation_id(response: requests.Response) -> int | None:
    try:
        data = response.json()
    except ValueError:
        return None
    for key in ("id", "reservationId", "reservation_id"):
        if key in data and data[key] is not None:
            return int(data[key])
    return None


def kurt3_request_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://kurt3.ghum.kuleuven.be/reservation",
        "Origin": "https://kurt3.ghum.kuleuven.be",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) "
            "Gecko/20100101 Firefox/152.0"
        ),
    }


def attempt_checkin(reservation_id: int) -> dict:
    cookies = booking_cookies()
    url = f"{CHECKIN_BASE_URL}{reservation_id}"
    log.info("Check-in GET %s", url)

    try:
        response = requests.get(
            url,
            headers=kurt3_request_headers(),
            cookies=cookies,
            timeout=30,
            allow_redirects=True,
        )
        ok = is_authenticated_response(response) and response.ok
        log.info("Check-in response: HTTP %s — %s", response.status_code, response.text[:200])
        return {
            "success": ok,
            "reservation_id": reservation_id,
            "status_code": response.status_code,
            "body": response.text[:300],
        }
    except requests.RequestException as exc:
        log.error("Check-in error: %s", exc)
        return {"success": False, "reservation_id": reservation_id, "error": str(exc)}


def process_pending_checkins() -> None:
    now = datetime.now()
    for item in _scheduler_state.get("pending_checkins", []):
        if item.get("done"):
            continue
        checkin_at = datetime.fromisoformat(item["checkin_at"])
        deadline = datetime.fromisoformat(item["deadline"])
        if now < checkin_at:
            continue
        if now > deadline:
            log.error(
                "Missed check-in window for reservation %s (deadline %s)",
                item["reservation_id"],
                item["deadline"],
            )
            item["done"] = True
            save_scheduler_state()
            continue
        result = attempt_checkin(int(item["reservation_id"]))
        item["done"] = True
        item["result"] = result
        save_scheduler_state()


def scheduled_booking_job() -> None:
    ok, reason = should_attempt_booking()
    if not ok:
        log.info("Skipping 18:00 booking: %s", reason)
        return
    attempt_booking()


# =============================================================================
# Flask webhook
# =============================================================================

app = Flask(__name__)


@app.after_request
def cors_headers(response):
    """Allow fetch() from the Firefox extension (moz-extension:// origin)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/update-cookie", methods=["OPTIONS"])
@app.route("/book-now", methods=["OPTIONS"])
@app.route("/health", methods=["OPTIONS"])
@app.route("/config", methods=["OPTIONS"])
def cors_preflight():
    return "", 204


def public_config() -> dict:
    s = get_settings()
    run_start, run_end = booking_run_window()
    active = is_booking_active_today()
    target = booking_target_date()
    next_target = target.isoformat() if active and is_target_date_in_period(target) else None
    return {
        "booking_enabled": s["booking_enabled"],
        "booking_active_today": active,
        "booking_period_start": s["booking_period_start"] or None,
        "booking_period_end": s["booking_period_end"] or None,
        "run_period_start": run_start.isoformat() if run_start else None,
        "run_period_end": run_end.isoformat() if run_end else None,
        "resource_id": s["resource_id"],
        "resource_name": s["resource_name"],
        "building_name": s["building_name"],
        "start_time": s["start_time"],
        "end_time": s["end_time"],
        "booking_date_offset_days": s["booking_date_offset_days"],
        "booking_time": s["booking_time"],
        "next_target_date": next_target,
        "booking_status_message": booking_status_message(),
    }


@app.route("/config", methods=["GET"])
def get_config():
    """Public read — used by admin UI and Mac tunnel agent."""
    return jsonify(public_config())


@app.route("/config", methods=["POST"])
def update_config():
    """Update settings (requires secret). No server restart needed."""
    data = request.get_json(silent=True) or {}
    if data.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    settings = get_settings()
    field_map = {
        "booking_enabled": bool,
        "booking_period_start": str,
        "booking_period_end": str,
        "resource_id": int,
        "resource_name": str,
        "building_name": str,
        "start_time": str,
        "end_time": str,
        "booking_date_offset_days": int,
    }
    for key, typ in field_map.items():
        if key in data:
            settings[key] = typ(data[key])

    save_settings(settings)
    log.info("Runtime config updated via /config")
    return jsonify(public_config())


@app.route("/admin")
def admin_page():
    """Simple settings UI — open at http://127.0.0.1:8080/admin (via SSH tunnel)."""
    return send_file(ADMIN_HTML_PATH)


@app.route("/health", methods=["GET"])
def health():
    """Simple health-check endpoint."""
    normalize_cookie_store()
    cookies = booking_cookies()
    shib_names = [n for n in cookies if n.startswith("_shibsession")]
    return jsonify(
        {
            "status": "ok",
            "has_cookie": bool(shib_names),
            "cookie_count": len(cookies),
            "shibsession_cookie": shib_names[0] if shib_names else None,
            "captured_at": _cookie_store.get("captured_at"),
            **public_config(),
            "future_quota_hours_used": future_quota_hours_used(),
            "future_quota_hours_limit": WEEKLY_FUTURE_HOUR_LIMIT,
            "bookings_by_bot": _scheduler_state.get("future_bookings", []),
            "pending_checkins": [
                c for c in _scheduler_state.get("pending_checkins", []) if not c.get("done")
            ],
        }
    )


@app.route("/update-cookie", methods=["POST"])
def update_cookie():
    """
    Receive a fresh session cookie from the Firefox extension.
    Validates the shared secret before storing.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Expected JSON body"}), 400

    if data.get("secret") != SECRET_KEY:
        log.warning("Rejected cookie update: invalid secret")
        return jsonify({"error": "Unauthorized"}), 401

    cookie_value = data.get("cookie_value")
    if not cookie_value and not data.get("cookies"):
        return jsonify({"error": "Missing cookie_value or cookies"}), 400

    cookie_jar: dict[str, str] = {}
    for entry in data.get("cookies") or []:
        name = entry.get("name")
        value = entry.get("value")
        if name and value:
            cookie_jar[name] = value

    if cookie_value:
        cookie_name = data.get("cookie_name", SESSION_COOKIE_NAME)
        cookie_jar[cookie_name] = cookie_value

    _cookie_store["cookies"] = cookie_jar
    shib_name = next((n for n in cookie_jar if n.startswith("_shibsession")), None)
    _cookie_store["cookie_name"] = shib_name or data.get("cookie_name", SESSION_COOKIE_NAME)
    _cookie_store["cookie_value"] = cookie_jar.get(_cookie_store["cookie_name"])
    _cookie_store["domain"] = data.get("domain")
    _cookie_store["captured_at"] = data.get("captured_at", datetime.now().isoformat())

    save_cookie_store()
    log.info(
        "Cookie updated: %d cookies, shib=%s domain=%s captured_at=%s",
        len(cookie_jar),
        _cookie_store["cookie_name"],
        _cookie_store["domain"],
        _cookie_store["captured_at"],
    )

    return jsonify(
        {
            "status": "stored",
            "cookie_name": _cookie_store["cookie_name"],
            "cookie_count": len(cookie_jar),
        }
    )


@app.route("/book-now", methods=["POST"])
def book_now():
    """
    Manually trigger a booking attempt (for testing before going live).

    POST JSON: {"secret": "<SECRET_KEY>", "skip_delay": false}
    Set skip_delay=true to fire immediately without the 100–400 ms jitter.
    """
    data = request.get_json(silent=True) or {}

    if data.get("secret") != SECRET_KEY:
        log.warning("Rejected book-now: invalid secret")
        return jsonify({"error": "Unauthorized"}), 401

    skip_delay = bool(data.get("skip_delay", False))
    force = bool(data.get("force", False))
    if not force:
        ok, reason = should_attempt_booking()
        if not ok:
            return jsonify({"success": False, "error": reason}), 400
    result = attempt_booking(skip_delay=skip_delay)

    status_code = 200 if result.get("success") else 502
    return jsonify(result), status_code


# =============================================================================
# Scheduled booking
# =============================================================================


def attempt_booking(*, skip_delay: bool = False) -> dict:
    """Fire the university booking POST with the stored session cookie."""
    cookies = booking_cookies()

    if not any(name.startswith("_shibsession") for name in cookies):
        log.error("No session cookie stored – cannot book. Log in via Firefox first.")
        return {"success": False, "error": "No session cookie stored"}

    if cookies.get("_shibsession_test") == "test123":
        return {
            "success": False,
            "error": "Stored cookie is the manual test placeholder – re-login via Firefox",
        }

    if not get_settings()["resource_id"]:
        log.error("resource_id is not set.")
        return {"success": False, "error": "resource_id not configured"}

    s = get_settings()
    target_date = booking_target_date()
    payload = build_booking_payload(target_date)

    if not skip_delay:
        delay_ms = random.randint(BOOKING_DELAY_MIN_MS, BOOKING_DELAY_MAX_MS)
        log.info("Waiting %d ms before booking request…", delay_ms)
        time.sleep(delay_ms / 1000.0)

    headers = {
        "Content-Type": "application/json",
        **kurt3_request_headers(),
    }

    cookies = dict(cookies)
    booked_at = datetime.now().isoformat()

    log.info(
        "Sending booking POST to %s at %s (seat %s, %s %s–%s, %d cookies)",
        BOOKING_URL,
        booked_at,
        s["resource_id"],
        target_date.isoformat(),
        s["start_time"],
        s["end_time"],
        len(cookies),
    )

    try:
        response = requests.post(
            BOOKING_URL,
            json=payload,
            headers=headers,
            cookies=cookies,
            timeout=30,
        )
        log.info("Booking response: HTTP %s", response.status_code)
        log.info("Response body: %s", response.text[:500])

        authenticated = is_authenticated_response(response)
        reservation_id = extract_reservation_id(response) if authenticated else None
        result = {
            "success": authenticated and response.ok,
            "status_code": response.status_code,
            "body": response.text[:500],
            "booked_at": booked_at,
            "resource_id": s["resource_id"],
            "reservation_id": reservation_id,
            "booking_date": target_date.isoformat(),
            "cookie_count": len(cookies),
        }

        if result["success"]:
            register_successful_booking(target_date, reservation_id)
            log.info("Booking succeeded (reservation_id=%s).", reservation_id)
        elif authenticated:
            log.error("Booking API returned JSON but status %s", response.status_code)
        elif response.ok:
            log.error("Got HTTP 200 but response looks like a login page – session invalid")
            result["error"] = "Session expired or invalid – log in again via Firefox"
        else:
            log.error("Booking request failed with status %s", response.status_code)

        return result

    except requests.RequestException as exc:
        log.error("Booking request error: %s", exc)
        return {"success": False, "error": str(exc), "booked_at": booked_at}


def run_scheduler() -> None:
    """Background thread that runs the schedule loop."""
    s = get_settings()
    schedule.every().day.at(s["booking_time"]).do(scheduled_booking_job)
    schedule.every(30).seconds.do(process_pending_checkins)
    log.info("Scheduler started – booking daily at %s (enabled=%s)", s["booking_time"], s["booking_enabled"])
    run_start, run_end = booking_run_window()
    if s["booking_period_start"] or s["booking_period_end"]:
        log.info(
            "Seat period: %s → %s (18:00 runs %s → %s)",
            s["booking_period_start"] or "…",
            s["booking_period_end"] or "…",
            run_start.isoformat() if run_start else "…",
            run_end.isoformat() if run_end else "…",
        )

    while True:
        schedule.run_pending()
        time.sleep(0.5)


# =============================================================================
# Bootstrap (shared by `python app.py` and gunicorn)
# =============================================================================

_scheduler_started = False


def bootstrap() -> None:
    """Load persisted cookie and start the daily scheduler (once per process)."""
    global _scheduler_started
    if _scheduler_started:
        return

    load_cookie_store()
    load_scheduler_state()
    prune_scheduler_state()
    init_runtime_config()

    if os.environ.get("DISABLE_SCHEDULER") == "1":
        log.info("Scheduler disabled (DISABLE_SCHEDULER=1)")
    else:
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

    _scheduler_started = True


bootstrap()


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("Starting Flask server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)

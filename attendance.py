from datetime import date, datetime, time, timedelta, timezone
from hashlib import pbkdf2_hmac
from hmac import compare_digest
import binascii
import io
import logging
import os
import threading
import uuid

import asyncio
import anyio
import cv2
import mediapipe as mp
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel
from pymongo import ASCENDING, MongoClient
from sklearn.metrics.pairwise import cosine_similarity
from starlette.middleware.sessions import SessionMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_env_file()


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "attendance-secret-change-me"),
    same_site="lax",
)


FRONTEND_DIST_DIR = os.path.join("frontend", "dist")
if os.path.isdir(FRONTEND_DIST_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")

ONNX_PATH = os.getenv("ONNX_PATH", "w600k_r50.onnx")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "attendance_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "employees")
COLLECTION_ATT = os.getenv("ATTENDANCE_COLLECTION", "attendance")
COLLECTION_LOCATION = os.getenv("LOCATION_COLLECTION", "location_tracking")
COLLECTION_SESSIONS = os.getenv("ATTENDANCE_SESSION_COLLECTION", "attendance_sessions")
ORG_COLLECTION_NAME = os.getenv("ORG_COLLECTION_NAME", "organizations")
ADMIN_COLLECTION_NAME = os.getenv("ADMIN_COLLECTION_NAME", "admin_users")
USER_COLLECTION_NAME = os.getenv("USER_COLLECTION_NAME", "users")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(10 * 1024 * 1024)))
SUPERADMIN_EMAIL = os.getenv("SUPERADMIN_EMAIL", "superadmin@example.com")
SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "superadmin123")
DEFAULT_TRACKING_TIMEOUT_HOURS = float(os.getenv("DEFAULT_TRACKING_TIMEOUT_HOURS", "4"))
DEFAULT_TRACKING_INTERVAL_MINUTES = int(os.getenv("DEFAULT_TRACKING_INTERVAL_MINUTES", "30"))
AUTO_CHECKOUT_POLL_SECONDS = int(os.getenv("AUTO_CHECKOUT_POLL_SECONDS", "60"))

MIN_FACE_SIZE_PX = 80
MIN_BLUR_SCORE = 80.0
MIN_BRIGHTNESS = 40
MAX_BRIGHTNESS = 220
MAX_TILT_ANGLE_DEG = 25

MP_FACE_MESH = mp.solutions.face_mesh
LEFT_IRIS = 468
RIGHT_IRIS = 473
NOSE_TIP = 1
LEFT_MOUTH = 61
RIGHT_MOUTH = 291

ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

_model_lock = threading.Lock()
_model_session = None
_model_input_name = None

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]
attendance_collection = db[COLLECTION_ATT]
location_collection = db[COLLECTION_LOCATION]
attendance_sessions_collection = db[COLLECTION_SESSIONS]
organizations_collection = db[ORG_COLLECTION_NAME]
admin_users_collection = db[ADMIN_COLLECTION_NAME]
users_collection = db[USER_COLLECTION_NAME]


class AttendanceModel(BaseModel):
    employee_id: str
    employee_name: str
    latitude: float
    longitude: float
    timestamp: datetime


class LoginModel(BaseModel):
    username: str
    password: str


class WebLoginModel(BaseModel):
    username: str
    password: str
    role: str = "auto"


class OrgCreateModel(BaseModel):
    org_name: str
    org_code: str
    max_users: int
    admin_name: str
    admin_email: str
    admin_password: str


class OrgUpdateModel(BaseModel):
    org_name: str
    org_code: str
    max_users: int
    admin_name: str
    admin_email: str
    admin_password: str = ""
    auto_checkout_enabled: bool = True
    tracking_timeout_hours: float = DEFAULT_TRACKING_TIMEOUT_HOURS
    tracking_interval_minutes: int = DEFAULT_TRACKING_INTERVAL_MINUTES


class UserCreateModel(BaseModel):
    employee_id: str
    employee_name: str
    email: str
    password: str


class TrackingSettingsModel(BaseModel):
    auto_checkout_enabled: bool = True
    tracking_timeout_hours: float = DEFAULT_TRACKING_TIMEOUT_HOURS
    tracking_interval_minutes: int = DEFAULT_TRACKING_INTERVAL_MINUTES


def utc_now():
    return datetime.now(timezone.utc)


def get_model_session():
    global _model_session, _model_input_name
    if _model_session is None:
        with _model_lock:
            if _model_session is None:
                logger.info("Loading face model from %s", ONNX_PATH)
                loaded_session = ort.InferenceSession(ONNX_PATH)
                _model_session = loaded_session
                _model_input_name = loaded_session.get_inputs()[0].name
    return _model_session, _model_input_name


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{binascii.hexlify(salt).decode()}${binascii.hexlify(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = binascii.unhexlify(salt_hex.encode())
        expected = binascii.unhexlify(digest_hex.encode())
        actual = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return compare_digest(actual, expected)
    except Exception:
        return False


def get_flash(request: Request):
    return request.session.pop("flash", None)


def set_flash(request: Request, message: str, level: str = "info"):
    request.session["flash"] = {"message": message, "level": level}


def require_superadmin(request: Request):
    if request.session.get("role") != "superadmin":
        return redirect("/superadmin/login")
    return None


def require_org_admin(request: Request):
    if request.session.get("role") != "org_admin":
        return redirect("/org-admin/login")
    return None


def get_org_by_id(org_id: str):
    return organizations_collection.find_one({"org_id": org_id}, {"_id": 0})


def get_admin_by_email(email: str):
    return admin_users_collection.find_one({"email": email.lower().strip()}, {"_id": 0})


def get_user_count(org_id: str) -> int:
    return users_collection.count_documents({"org_id": org_id})


def count_face_profiles(org_id: str) -> int:
    return collection.count_documents({"org_id": org_id})


def default_tracking_settings():
    return {
        "auto_checkout_enabled": True,
        "tracking_timeout_hours": DEFAULT_TRACKING_TIMEOUT_HOURS,
        "tracking_interval_minutes": DEFAULT_TRACKING_INTERVAL_MINUTES,
    }


def normalize_tracking_settings(settings):
    merged = default_tracking_settings()
    if isinstance(settings, dict):
        merged.update({key: settings[key] for key in merged if key in settings})
    merged["tracking_timeout_hours"] = max(0.25, float(merged["tracking_timeout_hours"]))
    merged["tracking_interval_minutes"] = max(1, int(merged["tracking_interval_minutes"]))
    merged["auto_checkout_enabled"] = bool(merged["auto_checkout_enabled"])
    return merged


def get_org_tracking_settings(org_id: str):
    org = get_org_by_id(org_id)
    if not org:
        return default_tracking_settings()
    return normalize_tracking_settings(org.get("tracking_settings"))


def find_active_session(org_id: str, employee_id: str):
    return attendance_sessions_collection.find_one(
        {"org_id": org_id, "employee_id": employee_id, "status": "active"},
        {"_id": 0},
        sort=[("check_in_time", -1)],
    )


def get_attendance_state(org_id: str, employee_id: str):
    active_session = find_active_session(org_id, employee_id)
    if active_session:
        return {
            "is_checked_in": True,
            "attendance_state": "checked_in",
            "next_attendance_type": "check_out",
            "active_session_id": active_session.get("session_id"),
            "check_in_time": format_api_timestamp(active_session.get("check_in_time")),
            "expected_checkout_at": format_api_timestamp(active_session.get("expected_checkout_at")),
        }

    latest = attendance_collection.find_one(
        {"org_id": org_id, "employee_id": employee_id},
        {"_id": 0, "attendance_type": 1, "timestamp": 1, "checkout_source": 1},
        sort=[("timestamp", -1)],
    )
    latest_type = (latest or {}).get("attendance_type")
    return {
        "is_checked_in": False,
        "attendance_state": "checked_out",
        "next_attendance_type": "check_in",
        "last_attendance_type": latest_type or "",
        "last_attendance_time": format_api_timestamp((latest or {}).get("timestamp")),
        "last_checkout_source": (latest or {}).get("checkout_source", ""),
    }


def open_attendance_session(body: dict):
    org_id = body.get("org_id")
    employee_id = body.get("employee_id")
    if not org_id or not employee_id:
        return None

    existing = find_active_session(org_id, employee_id)
    if existing:
        return existing

    settings = get_org_tracking_settings(org_id)
    check_in_dt = parse_record_timestamp(body.get("timestamp")) or utc_now()
    expected_checkout_at = check_in_dt + timedelta(hours=settings["tracking_timeout_hours"])
    session_doc = {
        "session_id": uuid.uuid4().hex,
        "org_id": org_id,
        "employee_id": employee_id,
        "employee_name": body.get("employee_name", ""),
        "check_in_time": check_in_dt,
        "expected_checkout_at": expected_checkout_at,
        "status": "active",
        "auto_checkout_enabled": settings["auto_checkout_enabled"],
        "tracking_timeout_hours": settings["tracking_timeout_hours"],
        "tracking_interval_minutes": settings["tracking_interval_minutes"],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    attendance_sessions_collection.insert_one(session_doc)
    session_doc.pop("_id", None)
    return session_doc


def close_attendance_session(body: dict, checkout_source="manual", remark=""):
    org_id = body.get("org_id")
    employee_id = body.get("employee_id")
    if not org_id or not employee_id:
        return
    active = find_active_session(org_id, employee_id)
    if not active:
        return
    attendance_sessions_collection.update_one(
        {"session_id": active["session_id"]},
        {"$set": {
            "status": "closed",
            "check_out_time": parse_record_timestamp(body.get("timestamp")) or utc_now(),
            "checkout_source": checkout_source,
            "checkout_remark": remark,
            "updated_at": utc_now(),
        }},
    )


def auto_checkout_due_sessions():
    now = utc_now()
    due_sessions = list(attendance_sessions_collection.find(
        {
            "status": "active",
            "auto_checkout_enabled": True,
            "expected_checkout_at": {"$lte": now},
        },
        {"_id": 0},
    ))
    for session_doc in due_sessions:
        checkout_record = {
            "employee_id": session_doc.get("employee_id", ""),
            "employee_name": session_doc.get("employee_name", ""),
            "org_id": session_doc.get("org_id", ""),
            "attendance_type": "check_out",
            "timestamp": now.isoformat(),
            "checkout_source": "auto",
            "remark": (
                f"Auto checkout after {session_doc.get('tracking_timeout_hours', DEFAULT_TRACKING_TIMEOUT_HOURS)} "
                "hours without manual checkout"
            ),
            "session_id": session_doc.get("session_id"),
        }
        attendance_collection.insert_one(checkout_record)
        attendance_sessions_collection.update_one(
            {"session_id": session_doc["session_id"]},
            {"$set": {
                "status": "closed",
                "check_out_time": now,
                "checkout_source": "auto",
                "checkout_remark": checkout_record["remark"],
                "updated_at": now,
            }},
        )
    return len(due_sessions)


async def auto_checkout_loop():
    while True:
        try:
            count = await anyio.to_thread.run_sync(auto_checkout_due_sessions)
            if count:
                logger.info("Auto checked out %s attendance sessions", count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("auto_checkout_loop failed: %s", exc)
        await asyncio.sleep(AUTO_CHECKOUT_POLL_SECONDS)


def parse_record_timestamp(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def format_display_timestamp(value):
    dt = parse_record_timestamp(value)
    return dt.strftime("%d-%m-%Y %I:%M:%S %p") if dt else (value or "")


def format_api_timestamp(value):
    dt = parse_record_timestamp(value)
    return dt.isoformat() if dt else (value or "")


def to_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def is_timestamp_in_range(value, start_date=None, end_date=None, month=None, exact_date=None):
    dt = parse_record_timestamp(value)
    if not dt:
        return False
    item_date = dt.date()
    if exact_date and item_date != exact_date:
        return False
    if month:
        try:
            month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
        except ValueError:
            return True
        if item_date.year != month_start.year or item_date.month != month_start.month:
            return False
    if start_date and item_date < start_date:
        return False
    if end_date and item_date > end_date:
        return False
    return True


def serialize_datetime_fields(record):
    clean = dict(record)
    clean.pop("_id", None)
    clean.pop("password_hash", None)
    for key in ("created_at", "updated_at", "timestamp"):
        if key in clean:
            clean[key] = format_api_timestamp(clean.get(key))
    return clean


def normalize_page(page: int = 1, page_size: int = 20):
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    return page, page_size


def paginate_items(items, page: int = 1, page_size: int = 20):
    page, page_size = normalize_page(page, page_size)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
            "has_next": end < total,
            "has_prev": page > 1,
        },
    }


def require_api_role(request: Request, *roles: str):
    role = request.session.get("role")
    if role not in roles:
        raise HTTPException(status_code=401, detail="Login required")
    return role


def set_login_session(request: Request, role: str, profile: dict):
    request.session.clear()
    request.session["role"] = role
    if role == "superadmin":
        request.session["email"] = profile.get("email", SUPERADMIN_EMAIL)
    elif role == "org_admin":
        request.session["org_id"] = profile["org_id"]
        request.session["admin_email"] = profile["email"]
        request.session["admin_name"] = profile["name"]
    elif role == "user":
        request.session["org_id"] = profile["org_id"]
        request.session["employee_id"] = profile["employee_id"]
        request.session["employee_name"] = profile["employee_name"]
        request.session["user_email"] = profile["email"]


def session_payload(request: Request):
    role = request.session.get("role")
    if not role:
        return {"authenticated": False, "role": None}
    payload = {"authenticated": True, "role": role}
    for key in ("email", "org_id", "admin_email", "admin_name", "employee_id", "employee_name", "user_email"):
        if key in request.session:
            payload[key] = request.session[key]
    return payload


def get_orgs_with_insights(page: int = 1, page_size: int = 20):
    orgs = list(organizations_collection.find({}, {"_id": 0}).sort("created_at", -1))
    total_users = 0
    total_faces = 0
    active_orgs = 0
    total_attendance_today = 0

    for org in orgs:
        org_id = org["org_id"]
        users_count = get_user_count(org_id)
        face_profiles = count_face_profiles(org_id)
        attendance_today = get_today_attendance_count(org_id)
        admin = admin_users_collection.find_one({"org_id": org_id}, {"_id": 0, "name": 1, "email": 1})
        org["users_count"] = users_count
        org["face_profiles"] = face_profiles
        org["attendance_today"] = attendance_today
        org["capacity_used_percent"] = round((users_count / max(int(org.get("max_users", 1)), 1)) * 100, 1)
        org["admin_name"] = admin.get("name") if admin else ""
        org["admin_email"] = admin.get("email") if admin else ""
        total_users += users_count
        total_faces += face_profiles
        total_attendance_today += attendance_today
        if org.get("is_active", False):
            active_orgs += 1

    paged = paginate_items(orgs, page, page_size)
    return {
        "summary": {
            "organizations": len(orgs),
            "active_organizations": active_orgs,
            "inactive_organizations": len(orgs) - active_orgs,
            "users": total_users,
            "face_profiles": total_faces,
            "attendance_today": total_attendance_today,
        },
        "orgs": paged["items"],
        "all_orgs": orgs,
        "pagination": paged["pagination"],
    }


def get_today_attendance_count(org_id: str) -> int:
    today = datetime.now().date()
    count = 0
    cursor = attendance_collection.find({"org_id": org_id}, {"timestamp": 1})
    for record in cursor:
        dt = parse_record_timestamp(record.get("timestamp"))
        if dt and dt.date() == today:
            count += 1
    return count


def get_org_attendance_rows(org_id: str):
    rows = []
    cursor = attendance_collection.find({"org_id": org_id}, {"_id": 0}).sort("timestamp", -1)
    for record in cursor:
        rows.append({
            "employee_id": record.get("employee_id", ""),
            "employee_name": record.get("employee_name", ""),
            "attendance_type": record.get("attendance_type", "attendance"),
            "latitude": record.get("latitude", ""),
            "longitude": record.get("longitude", ""),
            "timestamp": format_display_timestamp(record.get("timestamp")),
        })
    return rows


def get_org_map_points(org_id: str):
    points = []
    attendance_cursor = attendance_collection.find(
        {"org_id": org_id, "latitude": {"$exists": True}, "longitude": {"$exists": True}},
        {"_id": 0},
    )
    location_cursor = location_collection.find(
        {"org_id": org_id, "latitude": {"$exists": True}, "longitude": {"$exists": True}},
        {"_id": 0},
    )

    for record in attendance_cursor:
        points.append({
            "employee_id": record.get("employee_id", ""),
            "employee_name": record.get("employee_name", ""),
            "type": record.get("attendance_type", "attendance"),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "timestamp": format_display_timestamp(record.get("timestamp")),
        })

    for record in location_cursor:
        points.append({
            "employee_id": record.get("employee_id", ""),
            "employee_name": record.get("employee_name", ""),
            "type": "location_track",
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "timestamp": format_display_timestamp(record.get("timestamp")),
        })

    return sorted(points, key=lambda item: item.get("timestamp", ""), reverse=True)


def get_filtered_attendance_rows(org_id: str, employee_id=None, start=None, end=None, month=None, date_value=None):
    start_date = to_date(start)
    end_date = to_date(end)
    exact_date = to_date(date_value)
    query = {"org_id": org_id}
    if employee_id:
        query["employee_id"] = employee_id
    rows = []
    cursor = attendance_collection.find(query, {"_id": 0}).sort("timestamp", -1)
    for record in cursor:
        if not is_timestamp_in_range(record.get("timestamp"), start_date, end_date, month, exact_date):
            continue
        rows.append({
            "employee_id": record.get("employee_id", ""),
            "employee_name": record.get("employee_name", ""),
            "attendance_type": record.get("attendance_type", "attendance"),
            "latitude": record.get("latitude", ""),
            "longitude": record.get("longitude", ""),
            "checkout_source": record.get("checkout_source", "manual"),
            "remark": record.get("remark", ""),
            "session_id": record.get("session_id", ""),
            "timestamp": format_api_timestamp(record.get("timestamp")),
            "display_timestamp": format_display_timestamp(record.get("timestamp")),
        })
    return rows


def get_filtered_map_points(org_id: str, employee_id=None, start=None, end=None, month=None, date_value=None):
    start_date = to_date(start)
    end_date = to_date(end)
    exact_date = to_date(date_value)
    base_query = {"org_id": org_id, "latitude": {"$exists": True}, "longitude": {"$exists": True}}
    if employee_id:
        base_query["employee_id"] = employee_id

    points = []
    attendance_cursor = attendance_collection.find(base_query, {"_id": 0})
    location_query = {"org_id": org_id}
    if employee_id:
        location_query["employee_id"] = employee_id
    location_cursor = location_collection.find(location_query, {"_id": 0})

    for record in attendance_cursor:
        if not is_timestamp_in_range(record.get("timestamp"), start_date, end_date, month, exact_date):
            continue
        points.append({
            "employee_id": record.get("employee_id", ""),
            "employee_name": record.get("employee_name", ""),
            "type": record.get("attendance_type", "attendance"),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "tracking_status": record.get("tracking_status", "ok"),
            "remark": record.get("remark", ""),
            "timestamp": format_api_timestamp(record.get("timestamp")),
            "display_timestamp": format_display_timestamp(record.get("timestamp")),
        })

    for record in location_cursor:
        if not is_timestamp_in_range(record.get("timestamp"), start_date, end_date, month, exact_date):
            continue
        points.append({
            "employee_id": record.get("employee_id", ""),
            "employee_name": record.get("employee_name", ""),
            "type": "location_track",
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "tracking_status": record.get("tracking_status", "ok"),
            "remark": record.get("remark", ""),
            "timestamp": format_api_timestamp(record.get("timestamp")),
            "display_timestamp": format_display_timestamp(record.get("timestamp")),
        })

    return sorted(points, key=lambda item: item.get("timestamp", ""), reverse=True)


def get_attendance_date_groups(rows, map_points):
    grouped = {}
    for row in rows:
        dt = parse_record_timestamp(row.get("timestamp"))
        if not dt:
            continue
        key = (row.get("employee_id", ""), dt.date().isoformat())
        item = grouped.setdefault(key, {
            "employee_id": row.get("employee_id", ""),
            "employee_name": row.get("employee_name", ""),
            "date": dt.date().isoformat(),
            "check_in_count": 0,
            "check_out_count": 0,
            "attendance_count": 0,
            "gps_count": 0,
            "failed_gps_count": 0,
            "first_time": "",
            "last_time": "",
        })
        item["attendance_count"] += 1
        if row.get("attendance_type") == "check_in":
            item["check_in_count"] += 1
        if row.get("attendance_type") == "check_out":
            item["check_out_count"] += 1
        timestamp = row.get("timestamp") or ""
        item["first_time"] = min([value for value in [item["first_time"], timestamp] if value], default=timestamp)
        item["last_time"] = max(item["last_time"], timestamp)

    for point in map_points:
        dt = parse_record_timestamp(point.get("timestamp"))
        if not dt:
            continue
        key = (point.get("employee_id", ""), dt.date().isoformat())
        item = grouped.setdefault(key, {
            "employee_id": point.get("employee_id", ""),
            "employee_name": point.get("employee_name", ""),
            "date": dt.date().isoformat(),
            "check_in_count": 0,
            "check_out_count": 0,
            "attendance_count": 0,
            "gps_count": 0,
            "failed_gps_count": 0,
            "first_time": "",
            "last_time": "",
        })
        if point.get("type") == "location_track":
            item["gps_count"] += 1
            if point.get("tracking_status") != "ok":
                item["failed_gps_count"] += 1

    groups = list(grouped.values())
    for item in groups:
        item["first_time_display"] = format_display_timestamp(item["first_time"])
        item["last_time_display"] = format_display_timestamp(item["last_time"])
    return sorted(groups, key=lambda item: (item["date"], item["employee_name"], item["employee_id"]), reverse=True)


def build_org_dashboard(org_id: str, users_page: int = 1, users_page_size: int = 20):
    org = get_org_by_id(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    users = list(users_collection.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1))
    safe_users = []
    for user in users:
        user["face_enrolled"] = is_face_enrolled(org_id, user["employee_id"])
        safe_users.append(serialize_datetime_fields(user))

    attendance_today = get_today_attendance_count(org_id)
    user_count = len(users)
    face_profiles = count_face_profiles(org_id)
    recent_attendance = get_filtered_attendance_rows(org_id)[:12]
    active_users = sum(1 for user in users if user.get("is_active", True))
    active_sessions = attendance_sessions_collection.count_documents({"org_id": org_id, "status": "active"})
    tracking_settings = get_org_tracking_settings(org_id)

    paged_users = paginate_items(safe_users, users_page, users_page_size)
    return {
        "org": serialize_datetime_fields(org),
        "tracking_settings": tracking_settings,
        "summary": {
            "org_name": org["org_name"],
            "org_code": org["org_code"],
            "status": "Active" if org.get("is_active") else "Inactive",
            "user_limit": org.get("max_users", 0),
            "users_count": user_count,
            "active_users": active_users,
            "inactive_users": user_count - active_users,
            "face_profiles": face_profiles,
            "face_coverage_percent": round((face_profiles / max(user_count, 1)) * 100, 1),
            "attendance_today": attendance_today,
            "active_tracking_sessions": active_sessions,
            "capacity_used_percent": round((user_count / max(int(org.get("max_users", 1)), 1)) * 100, 1),
        },
        "users": paged_users["items"],
        "all_users": safe_users,
        "users_pagination": paged_users["pagination"],
        "recent_attendance": recent_attendance,
    }


def build_superadmin_org_detail(org_id: str, users_page: int = 1, users_page_size: int = 20):
    org = get_org_by_id(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    admin = admin_users_collection.find_one({"org_id": org_id}, {"_id": 0})
    users = list(users_collection.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1))
    safe_users = []
    for user in users:
        user["face_enrolled"] = is_face_enrolled(org_id, user["employee_id"])
        safe_users.append(serialize_datetime_fields(user))

    paged_users = paginate_items(safe_users, users_page, users_page_size)
    return {
        "org": serialize_datetime_fields(org),
        "admin": serialize_datetime_fields(admin or {}),
        "tracking_settings": get_org_tracking_settings(org_id),
        "summary": build_org_dashboard(org_id)["summary"],
        "users": paged_users["items"],
        "all_users": safe_users,
        "users_pagination": paged_users["pagination"],
        "recent_attendance": get_filtered_attendance_rows(org_id)[:20],
    }


def is_face_enrolled(org_id: str, employee_id: str) -> bool:
    return collection.find_one(
        {"org_id": org_id, "employee_id": employee_id},
        {"_id": 1},
    ) is not None


def read_image_from_bytes(data: bytes):
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image_np = np.array(image.convert("RGB"))
        return cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.warning("read_image_from_bytes failed: %s", exc)
        return None


def preprocess_face(face_bgr):
    face = cv2.resize(face_bgr, (112, 112))
    face = face.astype(np.float32) / 255.0
    face = (face - 0.5) / 0.5
    face = np.transpose(face, (2, 0, 1))
    return np.expand_dims(face, axis=0)


def l2_normalize(vector):
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 1e-10 else vector


def check_face_quality(face_bgr):
    h, w = face_bgr.shape[:2]
    if h < MIN_FACE_SIZE_PX or w < MIN_FACE_SIZE_PX:
        return False, f"Face too small ({w}x{h}px, need {MIN_FACE_SIZE_PX}px minimum)"

    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_score < MIN_BLUR_SCORE:
        return False, f"Face too blurry (score={blur_score:.1f}, need >={MIN_BLUR_SCORE})"

    brightness = float(gray.mean())
    if brightness < MIN_BRIGHTNESS:
        return False, f"Face too dark (brightness={brightness:.1f})"
    if brightness > MAX_BRIGHTNESS:
        return False, f"Face overexposed (brightness={brightness:.1f})"

    return True, ""


def _get_aligned_face(image_bgr, landmarks, img_h, img_w):
    lm = landmarks.landmark

    lx = lm[LEFT_IRIS].x * img_w
    ly = lm[LEFT_IRIS].y * img_h
    rx = lm[RIGHT_IRIS].x * img_w
    ry = lm[RIGHT_IRIS].y * img_h
    angle = np.degrees(np.arctan2(ry - ly, rx - lx))
    if abs(angle) > MAX_TILT_ANGLE_DEG:
        return None, (
            f"Face too tilted ({angle:.1f} degrees, max +/-{MAX_TILT_ANGLE_DEG}) - "
            "please hold the camera straight"
        )

    src = np.array([
        [lx, ly],
        [rx, ry],
        [lm[NOSE_TIP].x * img_w, lm[NOSE_TIP].y * img_h],
        [lm[LEFT_MOUTH].x * img_w, lm[LEFT_MOUTH].y * img_h],
        [lm[RIGHT_MOUTH].x * img_w, lm[RIGHT_MOUTH].y * img_h],
    ], dtype=np.float32)

    transform, _ = cv2.estimateAffinePartial2D(src, ARCFACE_DST, method=cv2.LMEDS)
    if transform is None:
        return None, "Face alignment transform failed"

    aligned = cv2.warpAffine(
        image_bgr,
        transform,
        (112, 112),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT,
    )
    return aligned, ""


def extract_mesh_faces(image_bgr, max_faces=10):
    img_h, img_w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    crops = []
    rejections = []

    with MP_FACE_MESH.FaceMesh(
        static_image_mode=True,
        max_num_faces=max_faces,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        results = face_mesh.process(rgb)
        if not results.multi_face_landmarks:
            return [], []

        for landmarks in results.multi_face_landmarks:
            aligned, reason = _get_aligned_face(image_bgr, landmarks, img_h, img_w)
            if aligned is not None:
                crops.append(aligned)
            else:
                rejections.append(reason)

    return crops, rejections


def embedding_from_mesh_crop(face_bgr):
    ok, reason = check_face_quality(face_bgr)
    if not ok:
        return None, reason

    try:
        face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        processed = preprocess_face(face_rgb)
        model_session, model_input_name = get_model_session()
        raw = model_session.run(None, {model_input_name: processed})[0].flatten()
        return l2_normalize(raw), ""
    except Exception as exc:
        logger.error("embedding_from_mesh_crop failed: %s", exc)
        return None, "Embedding extraction failed"


def get_embedding_single(image_np):
    crops, tilt_rejections = extract_mesh_faces(image_np, max_faces=5)
    if not crops:
        reason = tilt_rejections[0] if tilt_rejections else "No face detected"
        return None, reason
    if len(crops) > 1:
        return None, "Multiple faces detected - use a single-face photo"

    emb, reason = embedding_from_mesh_crop(crops[0])
    if emb is None:
        return None, reason
    return emb, None


def get_all_embeddings(image_np):
    crops, rejections = extract_mesh_faces(image_np, max_faces=10)
    embeddings = []

    for crop in crops:
        emb, reason = embedding_from_mesh_crop(crop)
        if emb is not None:
            embeddings.append(emb)
        else:
            rejections.append(reason)

    return embeddings, rejections


async def extract_enrollment_embedding(upload: UploadFile):
    image_bytes = await upload.read(MAX_FILE_BYTES + 1)
    if len(image_bytes) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file")

    image_np = await anyio.to_thread.run_sync(read_image_from_bytes, image_bytes)
    if image_np is None:
        raise HTTPException(status_code=400, detail="Failed to decode image")

    embedding, err = await anyio.to_thread.run_sync(lambda: get_embedding_single(image_np))
    if err:
        raise HTTPException(status_code=400, detail=err)
    return embedding


def redirect(url: str):
    return RedirectResponse(url=url, status_code=303)


@app.on_event("startup")
async def startup():
    organizations_collection.create_index([("org_id", ASCENDING)], unique=True)
    organizations_collection.create_index([("org_code", ASCENDING)], unique=True)
    admin_users_collection.create_index([("email", ASCENDING)], unique=True)
    users_collection.create_index([("email", ASCENDING)], unique=True)
    users_collection.create_index([("employee_id", ASCENDING), ("org_id", ASCENDING)], unique=True)
    collection.create_index([("employee_id", ASCENDING), ("org_id", ASCENDING)], unique=True)
    attendance_collection.create_index([("org_id", ASCENDING), ("employee_id", ASCENDING)])
    location_collection.create_index([("org_id", ASCENDING), ("employee_id", ASCENDING)])
    attendance_sessions_collection.create_index([("org_id", ASCENDING), ("employee_id", ASCENDING), ("status", ASCENDING)])
    attendance_sessions_collection.create_index([("status", ASCENDING), ("expected_checkout_at", ASCENDING)])
    app.state.auto_checkout_task = asyncio.create_task(auto_checkout_loop())
    logger.info("Registered routes:")
    for route in app.routes:
        logger.info(route.path)


@app.on_event("shutdown")
async def shutdown():
    task = getattr(app.state, "auto_checkout_task", None)
    if task:
        task.cancel()


@app.get("/")
async def index(request: Request):
    return redirect("/app/")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/auth/login")
async def api_login(request: Request, payload: WebLoginModel):
    role = payload.role.strip().lower()
    username = payload.username.strip()
    password = payload.password
    lookup = username.lower()

    if role in {"auto", "superadmin"}:
        if lookup != SUPERADMIN_EMAIL.lower().strip() or password != SUPERADMIN_PASSWORD:
            if role == "superadmin":
                raise HTTPException(status_code=401, detail="Invalid super admin credentials")
        else:
            set_login_session(request, "superadmin", {"email": SUPERADMIN_EMAIL})
            return session_payload(request)

    if role in {"auto", "org_admin"}:
        admin = get_admin_by_email(lookup)
        if not admin or not verify_password(password, admin.get("password_hash", "")):
            if role == "org_admin":
                raise HTTPException(status_code=401, detail="Invalid org admin credentials")
        else:
            org = get_org_by_id(admin.get("org_id", ""))
            if not org or not org.get("is_active", False):
                raise HTTPException(status_code=403, detail="Organization is inactive")
            if not admin.get("is_active", True):
                raise HTTPException(status_code=403, detail="Org admin is inactive")
            set_login_session(request, "org_admin", admin)
            return session_payload(request)

    if role in {"auto", "user"}:
        user = users_collection.find_one(
            {"$or": [{"email": lookup}, {"employee_id": username}]},
            {"_id": 0},
        )
        if not user or not verify_password(password, user.get("password_hash", "")):
            if role == "user":
                raise HTTPException(status_code=401, detail="Invalid user credentials")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        org = get_org_by_id(user.get("org_id", ""))
        if not org or not org.get("is_active", False):
            raise HTTPException(status_code=403, detail="Organization is inactive")
        if not user.get("is_active", True):
            raise HTTPException(status_code=403, detail="User is inactive")
        set_login_session(request, "user", user)
        return session_payload(request)

    raise HTTPException(status_code=400, detail="Unknown role")


@app.get("/api/auth/session")
async def api_session(request: Request):
    return session_payload(request)


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    request.session.clear()
    return {"success": True}


@app.get("/api/superadmin/dashboard")
async def api_superadmin_dashboard(request: Request, page: int = 1, page_size: int = 20):
    require_api_role(request, "superadmin")
    return get_orgs_with_insights(page, page_size)


@app.post("/api/superadmin/orgs")
async def api_create_org(request: Request, payload: OrgCreateModel):
    require_api_role(request, "superadmin")
    org_code = payload.org_code.strip().lower()
    admin_email = payload.admin_email.strip().lower()

    if organizations_collection.find_one({"org_code": org_code}):
        raise HTTPException(status_code=409, detail="Organization code already exists")
    if admin_users_collection.find_one({"email": admin_email}):
        raise HTTPException(status_code=409, detail="Org admin email already exists")

    org_id = uuid.uuid4().hex
    now = utc_now()
    organizations_collection.insert_one({
        "org_id": org_id,
        "org_name": payload.org_name.strip(),
        "org_code": org_code,
        "max_users": payload.max_users,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    })
    admin_users_collection.insert_one({
        "admin_id": uuid.uuid4().hex,
        "org_id": org_id,
        "name": payload.admin_name.strip(),
        "email": admin_email,
        "password_hash": hash_password(payload.admin_password),
        "role": "org_admin",
        "is_active": True,
        "created_at": now,
    })
    return {"success": True, "org_id": org_id}


@app.get("/api/superadmin/orgs/{org_id}")
async def api_superadmin_org_detail(request: Request, org_id: str, users_page: int = 1, users_page_size: int = 20):
    require_api_role(request, "superadmin")
    return build_superadmin_org_detail(org_id, users_page, users_page_size)


@app.put("/api/superadmin/orgs/{org_id}")
async def api_update_org(request: Request, org_id: str, payload: OrgUpdateModel):
    require_api_role(request, "superadmin")
    org = get_org_by_id(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org_code = payload.org_code.strip().lower()
    admin_email = payload.admin_email.strip().lower()

    if organizations_collection.find_one({"org_code": org_code, "org_id": {"$ne": org_id}}):
        raise HTTPException(status_code=409, detail="Organization code already exists")
    if admin_users_collection.find_one({"email": admin_email, "org_id": {"$ne": org_id}}):
        raise HTTPException(status_code=409, detail="Org admin email already exists")

    organizations_collection.update_one(
        {"org_id": org_id},
        {"$set": {
            "org_name": payload.org_name.strip(),
            "org_code": org_code,
            "max_users": payload.max_users,
            "tracking_settings": normalize_tracking_settings({
                "auto_checkout_enabled": payload.auto_checkout_enabled,
                "tracking_timeout_hours": payload.tracking_timeout_hours,
                "tracking_interval_minutes": payload.tracking_interval_minutes,
            }),
            "updated_at": utc_now(),
        }},
    )

    admin_update = {
        "name": payload.admin_name.strip(),
        "email": admin_email,
    }
    if payload.admin_password.strip():
        admin_update["password_hash"] = hash_password(payload.admin_password)

    admin_users_collection.update_one(
        {"org_id": org_id},
        {"$set": admin_update},
    )
    return {"success": True}


@app.post("/api/superadmin/orgs/{org_id}/toggle")
async def api_toggle_org(request: Request, org_id: str):
    require_api_role(request, "superadmin")
    org = get_org_by_id(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    next_status = not bool(org.get("is_active", True))
    organizations_collection.update_one(
        {"org_id": org_id},
        {"$set": {"is_active": next_status, "updated_at": utc_now()}},
    )
    return {"success": True, "is_active": next_status}


@app.get("/api/org-admin/dashboard")
async def api_org_admin_dashboard(request: Request, users_page: int = 1, users_page_size: int = 20):
    require_api_role(request, "org_admin")
    return build_org_dashboard(request.session["org_id"], users_page, users_page_size)


@app.post("/api/org-admin/users")
async def api_create_org_user(request: Request, payload: UserCreateModel):
    require_api_role(request, "org_admin")
    org_id = request.session["org_id"]
    org = get_org_by_id(org_id)
    if not org or not org.get("is_active", False):
        raise HTTPException(status_code=403, detail="Organization is inactive")
    if get_user_count(org_id) >= int(org.get("max_users", 0)):
        raise HTTPException(status_code=409, detail="User limit reached for this organization")

    email = payload.email.strip().lower()
    employee_id = payload.employee_id.strip()
    if users_collection.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="User email already exists")
    if users_collection.find_one({"org_id": org_id, "employee_id": employee_id}):
        raise HTTPException(status_code=409, detail="Employee ID already exists in this organization")

    user_id = uuid.uuid4().hex
    users_collection.insert_one({
        "user_id": user_id,
        "org_id": org_id,
        "employee_id": employee_id,
        "employee_name": payload.employee_name.strip(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "role": "employee",
        "is_active": True,
        "created_at": utc_now(),
    })
    return {"success": True, "user_id": user_id}


@app.post("/api/org-admin/users/{user_id}/toggle")
async def api_toggle_org_user(request: Request, user_id: str):
    require_api_role(request, "org_admin")
    org_id = request.session["org_id"]
    user = users_collection.find_one({"user_id": user_id, "org_id": org_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    next_status = not bool(user.get("is_active", True))
    users_collection.update_one({"user_id": user_id}, {"$set": {"is_active": next_status}})
    return {"success": True, "is_active": next_status}


@app.get("/api/org-admin/attendance")
async def api_org_admin_attendance(
    request: Request,
    employee_id: str | None = None,
    date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    month: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    require_api_role(request, "org_admin")
    org_id = request.session["org_id"]
    rows = get_filtered_attendance_rows(org_id, employee_id, start, end, month, date)
    map_points = get_filtered_map_points(org_id, employee_id, start, end, month, date)
    groups = get_attendance_date_groups(rows, map_points)
    paged_groups = paginate_items(groups, page, page_size)
    paged_rows = paginate_items(rows, page, page_size)
    return {
        "groups": paged_groups["items"],
        "groups_pagination": paged_groups["pagination"],
        "rows": paged_rows["items"],
        "pagination": paged_rows["pagination"],
        "map_points": map_points,
    }


@app.get("/api/user/dashboard")
async def api_user_dashboard(
    request: Request,
    date: str | None = None,
    start: str | None = None,
    end: str | None = None,
    month: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    require_api_role(request, "user")
    org_id = request.session["org_id"]
    employee_id = request.session["employee_id"]
    user = users_collection.find_one({"org_id": org_id, "employee_id": employee_id}, {"_id": 0})
    org = get_org_by_id(org_id)
    rows = get_filtered_attendance_rows(org_id, employee_id, start, end, month, date)
    points = get_filtered_map_points(org_id, employee_id, start, end, month, date)
    paged_rows = paginate_items(rows, page, page_size)
    check_ins = sum(1 for row in rows if row.get("attendance_type") == "check_in")
    check_outs = sum(1 for row in rows if row.get("attendance_type") == "check_out")
    return {
        "profile": serialize_datetime_fields(user or {}),
        "org": serialize_datetime_fields(org or {}),
        "summary": {
            "attendance_records": len(rows),
            "check_ins": check_ins,
            "check_outs": check_outs,
            "map_points": len(points),
        },
        "rows": paged_rows["items"],
        "pagination": paged_rows["pagination"],
        "map_points": points,
    }


@app.post("/login")
async def mobile_login(payload: LoginModel):
    username = payload.username.strip()
    password = payload.password
    lookup = username.lower()

    admin = get_admin_by_email(lookup)
    if admin and verify_password(password, admin.get("password_hash", "")):
        org = get_org_by_id(admin.get("org_id", ""))
        if not org or not org.get("is_active", False):
            return {"success": False, "message": "Organization is inactive"}
        state = get_attendance_state(admin.get("org_id", ""), admin.get("admin_id") or admin.get("email", ""))
        return {
            "success": True,
            "user_type": "admin",
            "employee_id": admin.get("admin_id") or admin.get("email", ""),
            "employee_name": admin.get("name") or admin.get("email", ""),
            "org_id": admin.get("org_id", ""),
            "tracking_settings": get_org_tracking_settings(admin.get("org_id", "")),
            **state,
        }

    user = users_collection.find_one(
        {
            "$or": [
                {"email": lookup},
                {"employee_id": username},
            ]
        },
        {"_id": 0},
    )
    if user and verify_password(password, user.get("password_hash", "")):
        org = get_org_by_id(user.get("org_id", ""))
        if not org or not org.get("is_active", False):
            return {"success": False, "message": "Organization is inactive"}
        if not user.get("is_active", True):
            return {"success": False, "message": "User is inactive"}
        state = get_attendance_state(user.get("org_id", ""), user.get("employee_id", ""))
        return {
            "success": True,
            "user_type": "user",
            "employee_id": user.get("employee_id", ""),
            "employee_name": user.get("employee_name", ""),
            "org_id": user.get("org_id", ""),
            "tracking_settings": get_org_tracking_settings(user.get("org_id", "")),
            **state,
        }

    return {"success": False, "message": "Invalid credentials"}


@app.get("/superadmin/login")
async def superadmin_login_page(request: Request):
    return redirect("/app/")


@app.post("/superadmin/login")
async def superadmin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    if email.lower().strip() != SUPERADMIN_EMAIL.lower().strip() or password != SUPERADMIN_PASSWORD:
        set_flash(request, "Invalid super admin credentials", "error")
        return redirect("/superadmin/login")

    request.session["role"] = "superadmin"
    request.session["email"] = SUPERADMIN_EMAIL
    set_flash(request, "Super admin logged in", "success")
    return redirect("/superadmin/dashboard")


@app.get("/superadmin/dashboard")
async def superadmin_dashboard(request: Request):
    return redirect("/app/")


@app.post("/superadmin/orgs/create")
async def create_org(
    request: Request,
    org_name: str = Form(...),
    org_code: str = Form(...),
    max_users: int = Form(...),
    admin_name: str = Form(...),
    admin_email: str = Form(...),
    admin_password: str = Form(...),
):
    auth_redirect = require_superadmin(request)
    if auth_redirect:
        return auth_redirect
    org_code = org_code.strip().lower()
    admin_email = admin_email.strip().lower()

    if organizations_collection.find_one({"org_code": org_code}):
        set_flash(request, "Organization code already exists", "error")
        return redirect("/superadmin/dashboard")
    if admin_users_collection.find_one({"email": admin_email}):
        set_flash(request, "Org admin email already exists", "error")
        return redirect("/superadmin/dashboard")

    org_id = uuid.uuid4().hex
    now = utc_now()
    organizations_collection.insert_one({
        "org_id": org_id,
        "org_name": org_name.strip(),
        "org_code": org_code,
        "max_users": max_users,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    })
    admin_users_collection.insert_one({
        "admin_id": uuid.uuid4().hex,
        "org_id": org_id,
        "name": admin_name.strip(),
        "email": admin_email,
        "password_hash": hash_password(admin_password),
        "role": "org_admin",
        "is_active": True,
        "created_at": now,
    })

    set_flash(request, "Organization onboarded successfully", "success")
    return redirect("/superadmin/dashboard")


@app.post("/superadmin/orgs/{org_id}/toggle")
async def toggle_org_status(request: Request, org_id: str):
    auth_redirect = require_superadmin(request)
    if auth_redirect:
        return auth_redirect
    org = get_org_by_id(org_id)
    if not org:
        set_flash(request, "Organization not found", "error")
        return redirect("/superadmin/dashboard")

    next_status = not bool(org.get("is_active", True))
    organizations_collection.update_one(
        {"org_id": org_id},
        {"$set": {"is_active": next_status, "updated_at": utc_now()}},
    )
    status_text = "activated" if next_status else "deactivated"
    set_flash(request, f"Organization {status_text}", "success")
    return redirect("/superadmin/dashboard")


@app.get("/superadmin/orgs/{org_id}/edit")
async def edit_org_page(request: Request, org_id: str):
    return redirect("/app/")


@app.post("/superadmin/orgs/{org_id}/edit")
async def edit_org(
    request: Request,
    org_id: str,
    org_name: str = Form(...),
    org_code: str = Form(...),
    max_users: int = Form(...),
    admin_name: str = Form(...),
    admin_email: str = Form(...),
    admin_password: str = Form(""),
):
    auth_redirect = require_superadmin(request)
    if auth_redirect:
        return auth_redirect

    org = get_org_by_id(org_id)
    if not org:
        set_flash(request, "Organization not found", "error")
        return redirect("/superadmin/dashboard")

    org_code = org_code.strip().lower()
    admin_email = admin_email.strip().lower()

    duplicate_org = organizations_collection.find_one({"org_code": org_code, "org_id": {"$ne": org_id}})
    if duplicate_org:
        set_flash(request, "Organization code already exists", "error")
        return redirect(f"/superadmin/orgs/{org_id}/edit")

    duplicate_admin = admin_users_collection.find_one({"email": admin_email, "org_id": {"$ne": org_id}})
    if duplicate_admin:
        set_flash(request, "Org admin email already exists", "error")
        return redirect(f"/superadmin/orgs/{org_id}/edit")

    organizations_collection.update_one(
        {"org_id": org_id},
        {"$set": {
            "org_name": org_name.strip(),
            "org_code": org_code,
            "max_users": max_users,
            "updated_at": utc_now(),
        }},
    )

    admin_update = {
        "name": admin_name.strip(),
        "email": admin_email,
    }
    if admin_password.strip():
        admin_update["password_hash"] = hash_password(admin_password)

    admin_users_collection.update_one(
        {"org_id": org_id},
        {"$set": admin_update},
    )

    set_flash(request, "Organization details updated", "success")
    return redirect("/superadmin/dashboard")


@app.get("/superadmin/logout")
async def superadmin_logout(request: Request):
    request.session.clear()
    return redirect("/")


@app.get("/org-admin/login")
async def org_admin_login_page(request: Request):
    return redirect("/app/")


@app.post("/org-admin/login")
async def org_admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    admin = get_admin_by_email(email)
    if not admin or not verify_password(password, admin["password_hash"]):
        set_flash(request, "Invalid org admin credentials", "error")
        return redirect("/org-admin/login")

    org = get_org_by_id(admin["org_id"])
    if not org or not org.get("is_active", False):
        set_flash(request, "Organization is deactivated", "error")
        return redirect("/org-admin/login")
    if not admin.get("is_active", True):
        set_flash(request, "Org admin is inactive", "error")
        return redirect("/org-admin/login")

    request.session["role"] = "org_admin"
    request.session["org_id"] = admin["org_id"]
    request.session["admin_email"] = admin["email"]
    request.session["admin_name"] = admin["name"]
    set_flash(request, "Org admin logged in", "success")
    return redirect("/org-admin/dashboard")


@app.get("/org-admin/dashboard")
async def org_admin_dashboard(request: Request):
    return redirect("/app/")


@app.post("/org-admin/users/create")
async def create_org_user(
    request: Request,
    employee_id: str = Form(...),
    employee_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    photo: UploadFile | None = File(None),
):
    auth_redirect = require_org_admin(request)
    if auth_redirect:
        return auth_redirect
    org_id = request.session["org_id"]
    org = get_org_by_id(org_id)
    if not org or not org.get("is_active", False):
        set_flash(request, "Organization is inactive", "error")
        return redirect("/org-admin/dashboard")

    existing_count = get_user_count(org_id)
    if existing_count >= int(org.get("max_users", 0)):
        set_flash(request, "User limit reached for this organization", "error")
        return redirect("/org-admin/dashboard")

    email = email.strip().lower()
    employee_id = employee_id.strip()
    if users_collection.find_one({"email": email}):
        set_flash(request, "User email already exists", "error")
        return redirect("/org-admin/dashboard")
    if users_collection.find_one({"org_id": org_id, "employee_id": employee_id}):
        set_flash(request, "Employee ID already exists in this organization", "error")
        return redirect("/org-admin/dashboard")

    embedding = None
    if photo and photo.filename:
        try:
            embedding = await extract_enrollment_embedding(photo)
        except HTTPException as exc:
            set_flash(request, str(exc.detail), "error")
            return redirect("/org-admin/dashboard")

    users_collection.insert_one({
        "user_id": uuid.uuid4().hex,
        "org_id": org_id,
        "employee_id": employee_id,
        "employee_name": employee_name.strip(),
        "email": email,
        "password_hash": hash_password(password),
        "role": "employee",
        "is_active": True,
        "created_at": utc_now(),
    })

    if embedding is not None:
        collection.update_one(
            {"employee_id": employee_id, "org_id": org_id},
            {"$set": {
                "employee_id": employee_id,
                "employee_name": employee_name.strip(),
                "org_id": org_id,
                "embedding": embedding.tolist(),
                "model_version": os.path.basename(ONNX_PATH),
                "updated_at": utc_now(),
            }},
            upsert=True,
        )
        set_flash(request, "Employee user created and face enrolled", "success")
        return redirect("/org-admin/dashboard")

    set_flash(request, "Employee user created", "success")
    return redirect("/org-admin/dashboard")


@app.post("/org-admin/users/{user_id}/toggle")
async def toggle_org_user(request: Request, user_id: str):
    auth_redirect = require_org_admin(request)
    if auth_redirect:
        return auth_redirect
    org_id = request.session["org_id"]
    user = users_collection.find_one({"user_id": user_id, "org_id": org_id}, {"_id": 0})
    if not user:
        set_flash(request, "User not found", "error")
        return redirect("/org-admin/dashboard")

    next_status = not bool(user.get("is_active", True))
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"is_active": next_status}},
    )
    set_flash(request, "User status updated", "success")
    return redirect("/org-admin/dashboard")


@app.get("/org-admin/users/{user_id}/edit")
async def edit_org_user_page(request: Request, user_id: str):
    return redirect("/app/")


@app.post("/org-admin/users/{user_id}/edit")
async def edit_org_user(
    request: Request,
    user_id: str,
    employee_id: str = Form(...),
    employee_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    photo: UploadFile | None = File(None),
):
    auth_redirect = require_org_admin(request)
    if auth_redirect:
        return auth_redirect

    org_id = request.session["org_id"]
    user = users_collection.find_one({"user_id": user_id, "org_id": org_id}, {"_id": 0})
    if not user:
        set_flash(request, "User not found", "error")
        return redirect("/org-admin/dashboard")

    email = email.strip().lower()
    employee_id = employee_id.strip()

    duplicate_email = users_collection.find_one({"email": email, "user_id": {"$ne": user_id}})
    if duplicate_email:
        set_flash(request, "User email already exists", "error")
        return redirect(f"/org-admin/users/{user_id}/edit")

    duplicate_employee = users_collection.find_one({
        "org_id": org_id,
        "employee_id": employee_id,
        "user_id": {"$ne": user_id},
    })
    if duplicate_employee:
        set_flash(request, "Employee ID already exists in this organization", "error")
        return redirect(f"/org-admin/users/{user_id}/edit")

    update_fields = {
        "employee_id": employee_id,
        "employee_name": employee_name.strip(),
        "email": email,
    }
    if password.strip():
        update_fields["password_hash"] = hash_password(password)

    users_collection.update_one(
        {"user_id": user_id},
        {"$set": update_fields},
    )

    collection.update_many(
        {"org_id": org_id, "employee_id": user["employee_id"]},
        {"$set": {
            "employee_id": employee_id,
            "employee_name": employee_name.strip(),
            "updated_at": utc_now(),
        }},
    )
    attendance_collection.update_many(
        {"org_id": org_id, "employee_id": user["employee_id"]},
        {"$set": {
            "employee_id": employee_id,
            "employee_name": employee_name.strip(),
        }},
    )

    if photo and photo.filename:
        try:
            embedding = await extract_enrollment_embedding(photo)
        except HTTPException as exc:
            set_flash(request, str(exc.detail), "error")
            return redirect(f"/org-admin/users/{user_id}/edit")

        collection.update_one(
            {"employee_id": employee_id, "org_id": org_id},
            {"$set": {
                "employee_id": employee_id,
                "employee_name": employee_name.strip(),
                "org_id": org_id,
                "embedding": embedding.tolist(),
                "model_version": os.path.basename(ONNX_PATH),
                "updated_at": utc_now(),
            }},
            upsert=True,
        )

    set_flash(request, "Employee details updated", "success")
    return redirect("/org-admin/dashboard")


@app.get("/org-admin/attendance")
async def org_admin_attendance_view(request: Request):
    return redirect("/app/")


@app.get("/org-admin/logout")
async def org_admin_logout(request: Request):
    request.session.clear()
    return redirect("/")


@app.post("/enroll-face")
async def enroll_face(
    employee_id: str = Form(...),
    employee_name: str = Form(...),
    org_id: str = Form(...),
    file: UploadFile = File(...),
):
    org = get_org_by_id(org_id)
    if not org or not org.get("is_active", False):
        raise HTTPException(status_code=403, detail="Organization is inactive")

    image_bytes = await file.read(MAX_FILE_BYTES + 1)
    if len(image_bytes) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file")

    image_np = await anyio.to_thread.run_sync(read_image_from_bytes, image_bytes)
    if image_np is None:
        raise HTTPException(status_code=400, detail="Failed to decode image")

    embedding, err = await anyio.to_thread.run_sync(lambda: get_embedding_single(image_np))
    if err:
        raise HTTPException(status_code=400, detail=err)

    await anyio.to_thread.run_sync(
        lambda: collection.update_one(
            {"employee_id": employee_id, "org_id": org_id},
            {"$set": {
                "employee_id": employee_id,
                "employee_name": employee_name,
                "org_id": org_id,
                "embedding": embedding.tolist(),
                "model_version": os.path.basename(ONNX_PATH),
                "updated_at": utc_now(),
            }},
            upsert=True,
        )
    )

    return {
        "success": True,
        "message": "Employee enrolled successfully",
        "employee_id": employee_id,
        "org_id": org_id,
    }


@app.post("/authenticate")
async def authenticate(
    live_image: UploadFile = File(...),
    org_id: str | None = Form(None),
):
    if org_id:
        org = get_org_by_id(org_id)
        if not org or not org.get("is_active", False):
            return JSONResponse(
                status_code=403,
                content={"authenticated": False, "error": "Organization is inactive"},
            )

    image_bytes = await live_image.read(MAX_FILE_BYTES + 1)
    if len(image_bytes) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not image_bytes:
        return JSONResponse(
            status_code=400,
            content={"authenticated": False, "error": "Empty image"},
        )

    image_np = await anyio.to_thread.run_sync(read_image_from_bytes, image_bytes)
    if image_np is None:
        return JSONResponse(
            status_code=400,
            content={"authenticated": False, "error": "Failed to decode image"},
        )

    live_embeddings, rejections = await anyio.to_thread.run_sync(
        lambda: get_all_embeddings(image_np)
    )
    if not live_embeddings:
        reason = rejections[0] if rejections else "No face detected"
        return JSONResponse(
            status_code=422,
            content={"authenticated": False, "error": reason},
        )

    query = {"org_id": org_id} if org_id else {}
    employees = await anyio.to_thread.run_sync(
        lambda: list(collection.find(
            query,
            {"_id": 0, "employee_id": 1, "employee_name": 1, "org_id": 1, "embedding": 1},
        ))
    )
    if not employees:
        return {"authenticated": False, "error": "No enrolled employees found"}

    db_matrix = np.stack([np.array(emp["embedding"], dtype=np.float32) for emp in employees])
    best_score = -1.0
    best_match = None

    for live_emb in live_embeddings:
        scores = cosine_similarity(live_emb.reshape(1, -1), db_matrix)[0]
        idx = int(np.argmax(scores))
        if float(scores[idx]) > best_score:
            best_score = float(scores[idx])
            best_match = employees[idx]

    if best_score >= SIMILARITY_THRESHOLD:
        return {
            "authenticated": True,
            "employee_id": best_match["employee_id"],
            "employee_name": best_match["employee_name"],
            "org_id": best_match.get("org_id"),
            "similarity_score": round(best_score, 4),
            "faces_detected": len(live_embeddings),
        }

    return {
        "authenticated": False,
        "similarity_score": round(best_score, 4),
        "faces_detected": len(live_embeddings),
        "error": "Face does not match any enrolled employee",
    }


@app.get("/list")
async def list_employees(org_id: str | None = None):
    query = {"org_id": org_id} if org_id else {}
    return list(collection.find(query, {"_id": 0, "employee_id": 1, "employee_name": 1, "org_id": 1}))


@app.post("/edit/{empid}")
async def edit_employee(
    empid: str,
    employee_name: str = Form(...),
    org_id: str | None = Form(None),
):
    query = {"employee_id": empid}
    if org_id:
        query["org_id"] = org_id
    collection.update_one(query, {"$set": {"employee_name": employee_name}})
    return {"success": True}


@app.delete("/delete/{empid}")
async def delete_employee(empid: str, org_id: str | None = None):
    query = {"employee_id": empid}
    if org_id:
        query["org_id"] = org_id
    collection.delete_one(query)
    return {"success": True}


@app.post("/attendance")
async def mark_attendance(request: Request):
    try:
        body = await request.json()
        employee_id = body.get("employee_id")
        attendance_type = body.get("attendance_type")
        if not employee_id:
            return JSONResponse(status_code=400, content={"success": False, "error": "employee_id is required"})
        if attendance_type not in {"check_in", "check_out"}:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "attendance_type must be check_in or check_out"},
            )
        if "org_id" not in body and body.get("employee_id"):
            user_doc = users_collection.find_one(
                {"employee_id": body["employee_id"]},
                {"_id": 0, "org_id": 1, "employee_name": 1},
            )
            if not user_doc:
                user_doc = collection.find_one(
                    {"employee_id": body["employee_id"]},
                    {"_id": 0, "org_id": 1, "employee_name": 1},
                )
            if user_doc:
                body["org_id"] = user_doc.get("org_id")
                body.setdefault("employee_name", user_doc.get("employee_name"))
        if not body.get("org_id"):
            return JSONResponse(status_code=400, content={"success": False, "error": "org_id is required"})
        if "timestamp" not in body:
            body["timestamp"] = utc_now().isoformat()
        active_session = find_active_session(body["org_id"], employee_id)
        if active_session:
            body["session_id"] = active_session.get("session_id")
        attendance_collection.insert_one(body)
        session_doc = None
        if attendance_type == "check_in":
            session_doc = open_attendance_session(body)
            if session_doc:
                attendance_collection.update_one(
                    {
                        "employee_id": employee_id,
                        "org_id": body["org_id"],
                        "attendance_type": "check_in",
                        "timestamp": body["timestamp"],
                    },
                    {"$set": {"session_id": session_doc.get("session_id")}},
                )
        if attendance_type == "check_out":
            close_attendance_session(
                body,
                checkout_source=body.get("checkout_source", "manual"),
                remark=body.get("remark", ""),
            )
        return {
            "success": True,
            "message": "Checkout marked successfully" if attendance_type == "check_out" else "Attendance marked successfully",
            "attendance_type": attendance_type,
            "is_checked_in": attendance_type == "check_in",
            "attendance_state": "checked_in" if attendance_type == "check_in" else "checked_out",
            "next_attendance_type": "check_out" if attendance_type == "check_in" else "check_in",
            "session_id": (session_doc or active_session or {}).get("session_id", ""),
            "expected_checkout_at": format_api_timestamp((session_doc or {}).get("expected_checkout_at")),
            "tracking_interval_minutes": (session_doc or {}).get(
                "tracking_interval_minutes",
                get_org_tracking_settings(body["org_id"]).get("tracking_interval_minutes"),
            ),
            "tracking_settings": get_org_tracking_settings(body["org_id"]),
        }
    except Exception as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/attendance-record/{employee_id}")
async def get_attendance(employee_id: str, org_id: str | None = None):
    try:
        query = {"employee_id": employee_id}
        if org_id:
            query["org_id"] = org_id
        records = list(
            attendance_collection.find(
                query,
                {"_id": 0},
            ).sort("timestamp", -1)
        )
        for record in records:
            record["timestamp"] = format_api_timestamp(record.get("timestamp"))
        return records
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/location-track")
async def save_location_track(request: Request):
    try:
        body = await request.json()
        employee_id = body.get("employee_id")
        org_id = body.get("org_id")
        tracking_status = body.get("tracking_status", "ok")
        if not employee_id:
            return JSONResponse(status_code=400, content={"success": False, "error": "employee_id is required"})
        if not org_id:
            return JSONResponse(status_code=400, content={"success": False, "error": "org_id is required"})
        if tracking_status == "ok" and ("latitude" not in body or "longitude" not in body):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "latitude and longitude are required when tracking_status is ok"},
            )
        if tracking_status != "ok" and not body.get("remark"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "remark is required when tracking_status is not ok"},
            )

        user_doc = users_collection.find_one(
            {"employee_id": employee_id, "org_id": org_id},
            {"_id": 0, "employee_name": 1},
        )
        face_doc = collection.find_one(
            {"employee_id": employee_id, "org_id": org_id},
            {"_id": 0, "employee_name": 1},
        )
        employee_name = body.get("employee_name") or (user_doc or face_doc or {}).get("employee_name", "")
        if "timestamp" not in body:
            body["timestamp"] = utc_now().isoformat()
        body["employee_name"] = employee_name
        body["tracking_status"] = tracking_status
        active_session = find_active_session(org_id, employee_id)
        if active_session:
            body["session_id"] = active_session.get("session_id")
        location_collection.insert_one(body)
        return {"success": True, "message": "Location saved"}
    except Exception as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

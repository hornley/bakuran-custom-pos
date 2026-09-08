from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .db import connect
from .generated_metadata import AUTH_PROFILE


ROLES = ("admin", "manager", "operator", "viewer")
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/session"}
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1
SESSION_TTL_HOURS = 8
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5200",
    "http://100.108.61.26:5200",
    "http://localhost:5174",
    "http://localhost:5200",
    "http://localhost:5300",
    "http://localhost:8080",
)
LOGIN_WINDOW_SECONDS = 60
MAX_LOGIN_FAILURES = 5
_LOGIN_FAILURES: dict[str, list[float]] = {}


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").lower() not in {"0", "false", "no", "off"}


def session_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(SESSION_TTL_HOURS * 3600))))
    except ValueError:
        return SESSION_TTL_HOURS * 3600


def cookie_secure() -> bool:
    return _env_bool("AUTH_COOKIE_SECURE")


def cookie_samesite() -> str:
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def allowed_origins() -> list[str]:
    configured = os.getenv("AUTH_ALLOWED_ORIGINS", "")
    values = [value.strip() for value in configured.split(",") if value.strip()]
    return values or list(DEFAULT_ALLOWED_ORIGINS)


AUTH_ALLOWED_ORIGINS = allowed_origins()

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS auth_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS auth_user_roles (
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES auth_roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES auth_users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at);
"""


def auth_enabled() -> bool:
    return AUTH_PROFILE == "local" and os.getenv("AUTH_ENABLED", "false").lower() not in {"0", "false", "no", "off"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _password_hash(password: str, salt: bytes | None = None) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P)
    encoded = base64.urlsafe_b64encode
    return "scrypt${}${}${}${}${}".format(
        PASSWORD_N,
        PASSWORD_R,
        PASSWORD_P,
        encoded(salt).decode("ascii"),
        encoded(digest).decode("ascii"),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p))
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _record_event(connection: sqlite3.Connection, actor_user_id: int | None, event_type: str, path: str = "", detail: str = "") -> None:
    connection.execute(
        "INSERT INTO audit_events(actor_user_id, event_type, path, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (actor_user_id, event_type, path[:240], detail[:500], _iso(_now())),
    )


def _ensure_audit_actor_foreign_key(connection: sqlite3.Connection) -> None:
    foreign_keys = connection.execute("PRAGMA foreign_key_list(audit_events)").fetchall()
    if any(row["table"] == "auth_users" and row["from"] == "actor_user_id" for row in foreign_keys):
        return
    connection.execute("DROP TABLE IF EXISTS audit_events_with_actor_fk")
    connection.execute(
        """
        CREATE TABLE audit_events_with_actor_fk (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER REFERENCES auth_users(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO audit_events_with_actor_fk(id,actor_user_id,event_type,path,detail,created_at)
        SELECT id,
               CASE WHEN actor_user_id IS NULL OR EXISTS (SELECT 1 FROM auth_users WHERE id=actor_user_id)
                    THEN actor_user_id ELSE NULL END,
               event_type,path,detail,created_at
        FROM audit_events
        """
    )
    connection.execute("DROP TABLE audit_events")
    connection.execute("ALTER TABLE audit_events_with_actor_fk RENAME TO audit_events")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at)")


def record_event(actor_user_id: int | None, event_type: str, path: str = "", detail: str = "") -> None:
    with connect() as connection:
        _record_event(connection, actor_user_id, event_type, path, detail)


def initialize_auth() -> None:
    if not auth_enabled():
        return
    with connect() as connection:
        connection.executescript(AUTH_SCHEMA)
        _ensure_audit_actor_foreign_key(connection)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(auth_sessions)").fetchall()}
        if "csrf_hash" not in columns:
            connection.execute("ALTER TABLE auth_sessions ADD COLUMN csrf_hash TEXT NOT NULL DEFAULT ''")
        connection.executemany("INSERT OR IGNORE INTO auth_roles(name) VALUES (?)", [(role,) for role in ROLES])
        existing = connection.execute("SELECT id FROM auth_users LIMIT 1").fetchone()
        if existing is None:
            username = os.getenv("AUTH_BOOTSTRAP_USERNAME", "").strip()
            password = os.getenv("AUTH_BOOTSTRAP_PASSWORD", "")
            if not username or not password:
                raise RuntimeError(
                    "Local authentication requires AUTH_BOOTSTRAP_USERNAME and AUTH_BOOTSTRAP_PASSWORD on first startup."
                )
            cursor = connection.execute(
                "INSERT INTO auth_users(username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, _password_hash(password), _iso(_now())),
            )
            admin_role = connection.execute("SELECT id FROM auth_roles WHERE name = 'admin'").fetchone()[0]
            connection.execute(
                "INSERT INTO auth_user_roles(user_id, role_id) VALUES (?, ?)",
                (cursor.lastrowid, admin_role),
            )
            _record_event(connection, cursor.lastrowid, "auth.bootstrap", detail="Initial local administrator created")


def _user(connection: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT u.id, u.username, u.is_active, GROUP_CONCAT(r.name) AS role_names
        FROM auth_users u LEFT JOIN auth_user_roles ur ON ur.user_id = u.id
        LEFT JOIN auth_roles r ON r.id = ur.role_id
        WHERE u.id = ? GROUP BY u.id
        """,
        (user_id,),
    ).fetchone()
    if row is None or not row["is_active"]:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "roles": sorted(filter(None, (row["role_names"] or "").split(","))),
    }


def _authenticate(username: str, password: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash FROM auth_users WHERE username = ? COLLATE NOCASE AND is_active = 1",
            (username.strip(),),
        ).fetchone()
        if row is None or not _verify_password(password, row["password_hash"]):
            _record_event(connection, None, "auth.login_denied", detail="Invalid credentials")
            return None
        now = _iso(_now())
        connection.execute("UPDATE auth_users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        user = _user(connection, row["id"])
        _record_event(connection, row["id"], "auth.login", detail="Login succeeded")
        return user


def _new_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    now = _now()
    with connect() as connection:
        connection.execute(
            "INSERT INTO auth_sessions(user_id, token_hash, csrf_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, _token_hash(token), _token_hash(csrf_token), _iso(now), _iso(now + timedelta(seconds=session_ttl_seconds()))),
        )
    return token, csrf_token


def _csrf_valid(request: Request, session_token: str | None = None) -> bool:
    token = session_token or request.cookies.get("local_session")
    csrf_token = request.cookies.get("local_csrf")
    header = request.headers.get("x-csrf-token")
    if not token or not csrf_token or not header or not secrets.compare_digest(csrf_token, header):
        return False
    with connect() as connection:
        row = connection.execute(
            "SELECT csrf_hash, expires_at, revoked_at FROM auth_sessions WHERE token_hash = ?",
            (_token_hash(token),),
        ).fetchone()
    return bool(row and not row["revoked_at"] and row["expires_at"] > _iso(_now()) and secrets.compare_digest(_token_hash(csrf_token), row["csrf_hash"]))


def current_user(request: Request, session_token: str | None = None) -> dict[str, Any] | None:
    token = session_token or request.cookies.get("local_session")
    if not token:
        return None
    with connect() as connection:
        row = connection.execute(
            "SELECT user_id, expires_at, revoked_at FROM auth_sessions WHERE token_hash = ?",
            (_token_hash(token),),
        ).fetchone()
        if row is None or row["revoked_at"] or row["expires_at"] <= _iso(_now()):
            return None
        return _user(connection, row["user_id"])


def _role_allows(user: dict[str, Any], request: Request) -> bool:
    roles = set(user.get("roles", []))
    if request.url.path.startswith("/api/auth/users"):
        return "admin" in roles
    if "admin" in roles or "manager" in roles:
        return True
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return bool(roles & {"viewer", "operator"})
    return "operator" in roles


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not auth_enabled() or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in PUBLIC_PATHS or request.method.upper() == "OPTIONS":
            if request.url.path == "/api/auth/logout" and request.method.upper() not in {"GET", "HEAD"} and request.cookies.get("local_session") and not _csrf_valid(request):
                record_event(None, "auth.csrf_denied", request.url.path, "CSRF validation failed")
                return JSONResponse({"detail": "CSRF validation failed."}, status_code=403)
            return await call_next(request)
        user = current_user(request)
        if user is None:
            record_event(None, "auth.denied", request.url.path, "Authentication required")
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        request.state.auth_user = user
        if not _role_allows(user, request):
            record_event(user["id"], "auth.denied", request.url.path, "Insufficient role")
            return JSONResponse({"detail": "This role cannot perform that action."}, status_code=403)
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"} and not _csrf_valid(request):
            record_event(user["id"], "auth.csrf_denied", request.url.path, "CSRF validation failed")
            return JSONResponse({"detail": "CSRF validation failed."}, status_code=403)
        response = await call_next(request)
        if response.status_code in {401, 403}:
            record_event(user["id"], "auth.denied", request.url.path, f"HTTP {response.status_code}")
        return response


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=512)
    roles: list[str] = Field(default_factory=lambda: ["operator"], min_length=1)


class UserRolesRequest(BaseModel):
    roles: list[str] = Field(min_length=1)


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _require_auth_mode() -> None:
    if not auth_enabled():
        raise HTTPException(status_code=404, detail="Local authentication is disabled.")


def _login_key(request: Request, username: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{username.strip().lower()}"


def _login_allowed(key: str) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _LOGIN_FAILURES.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
    _LOGIN_FAILURES[key] = recent
    return len(recent) < MAX_LOGIN_FAILURES


def _login_failed(key: str) -> None:
    _LOGIN_FAILURES.setdefault(key, []).append(time.monotonic())


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    if not auth_enabled():
        return {"authenticated": False, "auth_enabled": False}
    key = _login_key(request, payload.username)
    if not _login_allowed(key):
        record_event(None, "auth.login_rate_limited", detail="Login rate limit exceeded")
        raise HTTPException(status_code=429, detail="Invalid username or password.")
    user = _authenticate(payload.username, payload.password)
    if user is None:
        _login_failed(key)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    _LOGIN_FAILURES.pop(key, None)
    session_token, csrf_token = _new_session(user["id"])
    response.set_cookie("local_session", session_token, httponly=True, samesite=cookie_samesite(), secure=cookie_secure(), max_age=session_ttl_seconds())
    response.set_cookie("local_csrf", csrf_token, httponly=False, samesite=cookie_samesite(), secure=cookie_secure(), max_age=session_ttl_seconds())
    return {"authenticated": True, "auth_enabled": True, "user": user}


@router.post("/logout")
def logout(request: Request, response: Response, local_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    _require_auth_mode() if local_session else None
    if local_session and not _csrf_valid(request, local_session):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    user = current_user(request, local_session) if local_session else None
    if local_session:
        with connect() as connection:
            connection.execute("UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ?", (_iso(_now()), _token_hash(local_session)))
        record_event(user["id"] if user else None, "auth.logout")
    response.delete_cookie("local_session")
    response.delete_cookie("local_csrf")
    return {"authenticated": False, "auth_enabled": auth_enabled()}


@router.get("/session")
def session(request: Request) -> dict[str, Any]:
    if not auth_enabled():
        return {"authenticated": False, "auth_enabled": False}
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return {"authenticated": True, "auth_enabled": True, "user": user}


@router.get("/users")
def users() -> dict[str, Any]:
    _require_auth_mode()
    with connect() as connection:
        values = connection.execute(
            """
            SELECT u.id, u.username, u.is_active, u.created_at, u.last_login_at,
                   GROUP_CONCAT(r.name) AS role_names
            FROM auth_users u LEFT JOIN auth_user_roles ur ON ur.user_id = u.id
            LEFT JOIN auth_roles r ON r.id = ur.role_id GROUP BY u.id ORDER BY u.username
            """
        ).fetchall()
    return {
        "users": [
            {
                "id": row["id"],
                "username": row["username"],
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "last_login_at": row["last_login_at"],
                "roles": sorted(filter(None, (row["role_names"] or "").split(","))),
            }
            for row in values
        ],
        "roles": list(ROLES),
    }


@router.post("/users")
def create_user(payload: UserCreateRequest, request: Request) -> dict[str, Any]:
    _require_auth_mode()
    invalid = sorted(set(payload.roles) - set(ROLES))
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported roles: {', '.join(invalid)}")
    with connect() as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO auth_users(username, password_hash, created_at) VALUES (?, ?, ?)",
                (payload.username.strip(), _password_hash(payload.password), _iso(_now())),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Username already exists.") from error
        for role in sorted(set(payload.roles)):
            role_id = connection.execute("SELECT id FROM auth_roles WHERE name = ?", (role,)).fetchone()[0]
            connection.execute("INSERT INTO auth_user_roles(user_id, role_id) VALUES (?, ?)", (cursor.lastrowid, role_id))
        _record_event(connection, request.state.auth_user["id"], "auth.user_created", detail=payload.username)
    return {"id": cursor.lastrowid, "username": payload.username.strip(), "roles": sorted(set(payload.roles))}


@router.put("/users/{user_id}/roles")
def update_user_roles(user_id: int, payload: UserRolesRequest, request: Request) -> dict[str, Any]:
    _require_auth_mode()
    invalid = sorted(set(payload.roles) - set(ROLES))
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported roles: {', '.join(invalid)}")
    with connect() as connection:
        if connection.execute("SELECT 1 FROM auth_users WHERE id = ?", (user_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="User not found.")
        connection.execute("DELETE FROM auth_user_roles WHERE user_id = ?", (user_id,))
        for role in sorted(set(payload.roles)):
            role_id = connection.execute("SELECT id FROM auth_roles WHERE name = ?", (role,)).fetchone()[0]
            connection.execute("INSERT INTO auth_user_roles(user_id, role_id) VALUES (?, ?)", (user_id, role_id))
        _record_event(connection, request.state.auth_user["id"], "auth.roles_updated", detail=str(user_id))
    return {"id": user_id, "roles": sorted(set(payload.roles))}

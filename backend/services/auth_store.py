import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException

from backend.models.schemas import AuditResponse, ChatMessage, HistoryDetail, HistorySummary, UserProfile

logger = logging.getLogger("audit-api.auth-store")

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "app_state.db"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "sql" / "init_app_state.sql"
PBKDF2_ROUNDS = 200_000
DEFAULT_ADMIN_USERNAME = os.getenv("SAMSA_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("SAMSA_ADMIN_PASSWORD", "Admin@Samsa2026!")


@dataclass
class AuthenticatedUser:
    id: int
    username: str
    created_at: str

    def to_profile(self) -> UserProfile:
        return UserProfile(id=self.id, username=self.username, created_at=self.created_at)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_preview(text: str, limit: int = 140) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def build_history_title(document: str, source_name: Optional[str] = None) -> str:
    if source_name:
        return source_name.strip()[:80]

    compact = " ".join(document.split())
    if not compact:
        return "Untitled audit"

    for separator in [". ", "! ", "? ", "\n"]:
        if separator in compact:
            candidate = compact.split(separator, 1)[0].strip()
            if candidate:
                return candidate[:80]

    return compact[:80]


class AuthStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.ensure_default_admin()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        try:
            schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            logger.exception("Failed to load SQLite init script from %s", SCHEMA_PATH)
            raise RuntimeError("Failed to load SQLite initialization script.") from exc

        with self._lock, self._connect() as connection:
            connection.executescript(schema_sql)

    def _hash_password(self, password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS).hex()

    def _row_to_user(self, row: sqlite3.Row) -> AuthenticatedUser:
        return AuthenticatedUser(id=row["id"], username=row["username"], created_at=row["created_at"])

    def get_user_by_username(self, username: str) -> Optional[AuthenticatedUser]:
        normalized = username.strip()
        if not normalized:
            return None

        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, created_at FROM users WHERE username = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_user(row)

    def create_user(self, username: str, password: str) -> AuthenticatedUser:
        normalized = username.strip()
        if not normalized:
            raise ValueError("Username is required.")

        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt)
        created_at = _utc_now()

        try:
            with self._lock, self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (username, password_hash, password_salt, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (normalized, password_hash, salt.hex(), created_at),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("That username is already taken.") from exc

        logger.info("Created new user '%s' with id %s", normalized, user_id)
        return AuthenticatedUser(id=user_id, username=normalized, created_at=created_at)

    def ensure_user(self, username: str, password: str) -> tuple[AuthenticatedUser, bool]:
        existing = self.get_user_by_username(username)
        if existing is not None:
            return existing, False

        try:
            return self.create_user(username, password), True
        except ValueError:
            existing = self.get_user_by_username(username)
            if existing is None:
                raise
            return existing, False

    def ensure_default_admin(self) -> AuthenticatedUser:
        user, created = self.ensure_user(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
        if created:
            logger.info("Seeded local admin account '%s' with id %s", user.username, user.id)
        else:
            logger.info("Local admin account '%s' already exists", user.username)
        return user

    def authenticate(self, username: str, password: str) -> Optional[AuthenticatedUser]:
        normalized = username.strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, password_salt, created_at FROM users WHERE username = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()

        if row is None:
            return None

        candidate_hash = self._hash_password(password, bytes.fromhex(row["password_salt"]))
        if not hmac.compare_digest(candidate_hash, row["password_hash"]):
            return None

        return self._row_to_user(row)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        created_at = _utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (token, user_id, created_at, last_used_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, created_at, created_at),
            )
        return token

    def get_user_by_token(self, token: str, *, touch: bool = True) -> Optional[AuthenticatedUser]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.username, users.created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

            if row is None:
                return None

            if touch:
                connection.execute(
                    "UPDATE sessions SET last_used_at = ? WHERE token = ?",
                    (_utc_now(), token),
                )

        return self._row_to_user(row)

    def delete_session(self, token: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def save_chat_message(
        self,
        *,
        user_id: int,
        session_id: str,
        role: str,
        message: str,
    ) -> ChatMessage:
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            raise ValueError("Session ID is required.")

        normalized_role = role.strip().lower()
        if normalized_role not in {"user", "assistant"}:
            raise ValueError("Role must be either 'user' or 'assistant'.")

        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("Message cannot be empty.")

        timestamp = _utc_now()

        try:
            with self._lock, self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO chat_history (user_id, session_id, role, message, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, normalized_session_id, normalized_role, normalized_message, timestamp),
                )
                message_id = cursor.lastrowid
        except sqlite3.Error as exc:
            logger.exception("Failed to save chat message for user %s", user_id)
            raise RuntimeError("Failed to save chat history.") from exc

        return ChatMessage(
            id=message_id,
            session_id=normalized_session_id,
            role=normalized_role,
            message=normalized_message,
            timestamp=timestamp,
        )

    def get_chat_history(self, user_id: int, session_id: str, limit: int = 50) -> list[ChatMessage]:
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            raise ValueError("Session ID is required.")

        safe_limit = max(1, min(limit, 200))

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT id, session_id, role, message, timestamp
                    FROM (
                        SELECT id, session_id, role, message, timestamp
                        FROM chat_history
                        WHERE user_id = ? AND session_id = ?
                        ORDER BY timestamp DESC, id DESC
                        LIMIT ?
                    ) recent
                    ORDER BY timestamp ASC, id ASC
                    """,
                    (user_id, normalized_session_id, safe_limit),
                ).fetchall()
        except sqlite3.Error as exc:
            logger.exception("Failed to load chat history for user %s", user_id)
            raise RuntimeError("Failed to load chat history.") from exc

        return [
            ChatMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                message=row["message"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def save_audit_history(
        self,
        *,
        user_id: int,
        audit: AuditResponse,
        source_name: Optional[str] = None,
    ) -> int:
        title = build_history_title(audit.document, source_name)
        preview = _compact_preview(audit.document)
        created_at = _utc_now()

        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_history (
                    user_id, title, preview, source_name,
                    total, verified, plausible, hallucinations,
                    audit_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    title,
                    preview,
                    source_name,
                    audit.total,
                    audit.verified,
                    audit.plausible,
                    audit.hallucinations,
                    json.dumps(audit.model_dump()),
                    created_at,
                ),
            )
            history_id = cursor.lastrowid

        logger.info("Saved audit history %s for user %s", history_id, user_id)
        return history_id

    def list_history(self, user_id: int, limit: int = 50) -> list[HistorySummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, preview, created_at, total, verified, plausible, hallucinations, source_name
                FROM audit_history
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [
            HistorySummary(
                id=row["id"],
                title=row["title"],
                preview=row["preview"],
                created_at=row["created_at"],
                total=row["total"],
                verified=row["verified"],
                plausible=row["plausible"],
                hallucinations=row["hallucinations"],
                source_name=row["source_name"],
            )
            for row in rows
        ]

    def get_history_detail(self, user_id: int, history_id: int) -> Optional[HistoryDetail]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, preview, created_at, total, verified, plausible, hallucinations, source_name, audit_json
                FROM audit_history
                WHERE user_id = ? AND id = ?
                """,
                (user_id, history_id),
            ).fetchone()

        if row is None:
            return None

        summary = HistorySummary(
            id=row["id"],
            title=row["title"],
            preview=row["preview"],
            created_at=row["created_at"],
            total=row["total"],
            verified=row["verified"],
            plausible=row["plausible"],
            hallucinations=row["hallucinations"],
            source_name=row["source_name"],
        )
        audit = AuditResponse.model_validate(json.loads(row["audit_json"]))
        return HistoryDetail(item=summary, audit=audit)


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    return token


def get_current_user(authorization: Optional[str] = Header(default=None)) -> AuthenticatedUser:
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")

    user = auth_store.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[AuthenticatedUser]:
    token = _extract_token(authorization)
    if not token:
        return None

    user = auth_store.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return user


auth_store = AuthStore(DB_PATH)

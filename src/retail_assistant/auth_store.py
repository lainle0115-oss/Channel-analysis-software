from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterator


PBKDF2_ITERATIONS = 210_000
DEFAULT_DB_PATH = Path(".streamlit") / "app_data.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    password_salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return password_hash, password_salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    name: str
    role: str
    created_at: str
    last_login_at: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_session(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }


class AuthStoreError(RuntimeError):
    pass


class AuthStore:
    def __init__(self, database_url: str | None = None, sqlite_path: Path | None = None) -> None:
        self.database_url = (database_url or os.environ.get("DATABASE_URL") or "").strip()
        self.sqlite_path = sqlite_path or Path(os.environ.get("APP_DB_PATH", DEFAULT_DB_PATH))
        self.backend = "postgres" if self.database_url.startswith(("postgres://", "postgresql://")) else "sqlite"

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.backend == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - only hit when deployed without dependency.
                raise AuthStoreError("Postgres 需要安装 psycopg[binary]。") from exc
            with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
                yield conn
        else:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _placeholder(self) -> str:
        return "%s" if self.backend == "postgres" else "?"

    def _execute(self, conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return conn.execute(sql, params)

    def init_db(self) -> None:
        with self.connect() as conn:
            self._execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                )
                """,
            )
            self._execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """,
            )
            self._execute(conn, "CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id)")
            self._execute(conn, "CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at)")
            self._ensure_admin_from_env(conn)

    def _row_to_user(self, row: Any | None) -> AuthUser | None:
        if row is None:
            return None
        return AuthUser(
            id=str(row["id"]),
            email=str(row["email"]),
            name=str(row["name"] or ""),
            role=str(row["role"] or "user"),
            created_at=str(row["created_at"]),
            last_login_at=str(row["last_login_at"]) if row["last_login_at"] else None,
        )

    def _user_count(self, conn: Any) -> int:
        row = self._execute(conn, "SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"])

    def _ensure_admin_from_env(self, conn: Any) -> None:
        admin_email = normalize_email(os.environ.get("ADMIN_EMAIL", ""))
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if not admin_email or not admin_password:
            return
        existing = self._execute(
            conn,
            f"SELECT * FROM users WHERE email = {self._placeholder()}",
            (admin_email,),
        ).fetchone()
        password_hash, salt = hash_password(admin_password)
        if existing is None:
            self._execute(
                conn,
                f"""
                INSERT INTO users (id, email, password_hash, salt, name, role, created_at)
                VALUES ({self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()})
                """,
                (secrets.token_hex(16), admin_email, password_hash, salt, "管理员", "admin", utc_now()),
            )
            return
        self._execute(
            conn,
            f"""
            UPDATE users
            SET password_hash = {self._placeholder()}, salt = {self._placeholder()}, role = 'admin'
            WHERE email = {self._placeholder()}
            """,
            (password_hash, salt, admin_email),
        )

    def register_user(self, email: str, password: str, name: str = "") -> AuthUser:
        clean_email = normalize_email(email)
        if not clean_email or "@" not in clean_email:
            raise ValueError("请输入有效邮箱。")
        if len(password) < 8:
            raise ValueError("密码至少需要 8 位。")
        with self.connect() as conn:
            role = "admin" if self._user_count(conn) == 0 else "user"
            password_hash, salt = hash_password(password)
            user_id = secrets.token_hex(16)
            try:
                self._execute(
                    conn,
                    f"""
                    INSERT INTO users (id, email, password_hash, salt, name, role, created_at)
                    VALUES ({self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()})
                    """,
                    (user_id, clean_email, password_hash, salt, name.strip(), role, utc_now()),
                )
            except Exception as exc:
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    raise ValueError("该邮箱已注册。") from exc
                raise
            row = self._execute(
                conn,
                f"SELECT * FROM users WHERE id = {self._placeholder()}",
                (user_id,),
            ).fetchone()
            user = self._row_to_user(row)
            if user is None:
                raise AuthStoreError("注册失败，请重试。")
            return user

    def authenticate(self, email: str, password: str) -> AuthUser | None:
        clean_email = normalize_email(email)
        with self.connect() as conn:
            row = self._execute(
                conn,
                f"SELECT * FROM users WHERE email = {self._placeholder()}",
                (clean_email,),
            ).fetchone()
            if row is None or not verify_password(password, str(row["password_hash"]), str(row["salt"])):
                return None
            now = utc_now()
            self._execute(
                conn,
                f"UPDATE users SET last_login_at = {self._placeholder()} WHERE id = {self._placeholder()}",
                (now, row["id"]),
            )
            refreshed = dict(row)
            refreshed["last_login_at"] = now
            return self._row_to_user(refreshed)

    def get_user(self, user_id: str) -> AuthUser | None:
        with self.connect() as conn:
            row = self._execute(
                conn,
                f"SELECT * FROM users WHERE id = {self._placeholder()}",
                (user_id,),
            ).fetchone()
            return self._row_to_user(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = self._execute(
                conn,
                """
                SELECT
                    users.id,
                    users.email,
                    users.name,
                    users.role,
                    users.created_at,
                    users.last_login_at,
                    COUNT(uploads.id) AS upload_count,
                    COALESCE(SUM(uploads.size), 0) AS upload_bytes
                FROM users
                LEFT JOIN uploads ON uploads.user_id = users.id
                GROUP BY users.id, users.email, users.name, users.role, users.created_at, users.last_login_at
                ORDER BY users.created_at DESC
                """,
            ).fetchall()
            return [dict(row) for row in rows]

    def list_uploads(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if user_id:
                rows = self._execute(
                    conn,
                    f"""
                    SELECT uploads.*, users.email AS user_email
                    FROM uploads
                    JOIN users ON users.id = uploads.user_id
                    WHERE uploads.user_id = {self._placeholder()}
                    ORDER BY uploads.created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
            else:
                rows = self._execute(
                    conn,
                    """
                    SELECT uploads.*, users.email AS user_email
                    FROM uploads
                    JOIN users ON users.id = uploads.user_id
                    ORDER BY uploads.created_at DESC
                    """,
                ).fetchall()
            return [dict(row) for row in rows]

    def add_upload(self, user_id: str, name: str, path: str, size: int, upload_id: str | None = None) -> dict[str, Any]:
        record_id = upload_id or secrets.token_hex(16)
        with self.connect() as conn:
            self._execute(
                conn,
                f"""
                INSERT INTO uploads (id, user_id, name, path, size, created_at)
                VALUES ({self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()}, {self._placeholder()})
                """,
                (record_id, user_id, name, path, int(size), utc_now()),
            )
            row = self._execute(
                conn,
                f"SELECT * FROM uploads WHERE id = {self._placeholder()}",
                (record_id,),
            ).fetchone()
            return dict(row)

    def delete_upload(self, upload_id: str, user_id: str, is_admin: bool = False) -> dict[str, Any] | None:
        with self.connect() as conn:
            if is_admin:
                row = self._execute(
                    conn,
                    f"SELECT * FROM uploads WHERE id = {self._placeholder()}",
                    (upload_id,),
                ).fetchone()
            else:
                row = self._execute(
                    conn,
                    f"SELECT * FROM uploads WHERE id = {self._placeholder()} AND user_id = {self._placeholder()}",
                    (upload_id, user_id),
                ).fetchone()
            if row is None:
                return None
            self._execute(
                conn,
                f"DELETE FROM uploads WHERE id = {self._placeholder()}",
                (upload_id,),
            )
            return dict(row)

    def clear_uploads(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = self._execute(
                conn,
                f"SELECT * FROM uploads WHERE user_id = {self._placeholder()}",
                (user_id,),
            ).fetchall()
            self._execute(
                conn,
                f"DELETE FROM uploads WHERE user_id = {self._placeholder()}",
                (user_id,),
            )
            return [dict(row) for row in rows]


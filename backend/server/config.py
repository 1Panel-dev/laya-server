import os
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher


@dataclass(frozen=True)
class Settings:
    admin_username: str
    admin_password_hash: str
    database_path: Path
    public_origin: str
    secure_cookie: bool
    session_hours: int
    model_dir: Path
    device: str | None
    max_loaded_models: int
    frontend_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        username = os.environ.get("LAYA_ADMIN_USERNAME", "")
        password = os.environ.get("LAYA_ADMIN_PASSWORD", "")
        password_hash = os.environ.get("LAYA_ADMIN_PASSWORD_HASH", "")
        origin = os.environ.get("LAYA_PUBLIC_ORIGIN", "").rstrip("/")
        if not username or not origin:
            raise RuntimeError("Set LAYA_ADMIN_USERNAME and LAYA_PUBLIC_ORIGIN")
        if bool(password) == bool(password_hash):
            raise RuntimeError("Set exactly one of LAYA_ADMIN_PASSWORD or LAYA_ADMIN_PASSWORD_HASH")
        if password:
            if len(password) < 10:
                raise RuntimeError("LAYA_ADMIN_PASSWORD must contain at least 10 characters")
            password_hash = PasswordHasher().hash(password)
        if not origin.startswith(("https://", "http://")):
            raise RuntimeError("LAYA_PUBLIC_ORIGIN must be an absolute HTTP(S) origin")
        if origin.startswith("http://") and os.environ.get("LAYA_ALLOW_INSECURE_LOCAL") != "1":
            raise RuntimeError("HTTP origin requires LAYA_ALLOW_INSECURE_LOCAL=1")
        if "/" in origin.split("://", 1)[1]:
            raise RuntimeError("LAYA_PUBLIC_ORIGIN must not contain a path")
        return cls(
            username, password_hash,
            Path(os.environ.get("LAYA_DATABASE_PATH", "/data/laya.sqlite3")),
            origin, origin.startswith("https://"),
            int(os.environ.get("LAYA_SESSION_HOURS", "12")),
            Path(os.environ.get("LAYA_MODEL_DIR", "/models")),
            os.environ.get("LAYA_DEVICE") or None,
            int(os.environ.get("LAYA_MAX_LOADED_MODELS", "1")),
            Path(os.environ.get("LAYA_FRONTEND_DIR", "/app/frontend/dist")),
        )

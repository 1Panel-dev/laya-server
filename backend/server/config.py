import os
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher


@dataclass(frozen=True)
class Settings:
    admin_username: str
    admin_password_hash: str
    database_path: Path
    session_hours: int
    model_dir: Path
    device: str | None
    max_loaded_models: int
    frontend_dir: Path
    model_profile: str = "all"

    @classmethod
    def from_env(cls) -> "Settings":
        username = os.environ.get("LAYA_ADMIN_USERNAME", "")
        password = os.environ.get("LAYA_ADMIN_PASSWORD", "")
        password_hash = os.environ.get("LAYA_ADMIN_PASSWORD_HASH", "")
        if not username:
            raise RuntimeError("Set LAYA_ADMIN_USERNAME")
        if bool(password) == bool(password_hash):
            raise RuntimeError("Set exactly one of LAYA_ADMIN_PASSWORD or LAYA_ADMIN_PASSWORD_HASH")
        if password:
            if len(password) < 10:
                raise RuntimeError("LAYA_ADMIN_PASSWORD must contain at least 10 characters")
            password_hash = PasswordHasher().hash(password)
        model_profile = os.environ.get("LAYA_MODEL_PROFILE", "all")
        if model_profile not in ("all", "multilingual"):
            raise RuntimeError("LAYA_MODEL_PROFILE must be all or multilingual")
        return cls(
            username, password_hash,
            Path(os.environ.get("LAYA_DATABASE_PATH", "/data/laya.sqlite3")),
            int(os.environ.get("LAYA_SESSION_HOURS", "12")),
            Path(os.environ.get("LAYA_MODEL_DIR", "/models")),
            os.environ.get("LAYA_DEVICE") or None,
            int(os.environ.get("LAYA_MAX_LOADED_MODELS", "1")),
            Path(os.environ.get("LAYA_FRONTEND_DIR", "/app/frontend/dist")),
            model_profile,
        )

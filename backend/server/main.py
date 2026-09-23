import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .database import Database, utc_now
from .laya_adapter import LayaAdapter, Predictor
from .schemas import CreateKeyRequest, InferenceRequest, LoginRequest

logger = logging.getLogger(__name__)
SESSION_COOKIE = "laya_session"
CSRF_COOKIE = "laya_csrf"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def create_app(settings: Settings | None = None, predictor: Predictor | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)
    db.initialize()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    hasher = PasswordHasher()
    router_holder: dict[str, Predictor] = {}
    router_lock = threading.Lock()

    @app.exception_handler(RequestValidationError)
    def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"loc": list(item["loc"]), "type": item["type"], "message": item["msg"]}
                  for item in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": {
            "code": "VALIDATION_ERROR", "message": "Request validation failed", "errors": fields,
        }})

    def require_origin(request: Request) -> None:
        if request.headers.get("origin") != settings.public_origin:
            raise error(403, "ORIGIN_MISMATCH", "Request origin is not allowed")

    def current_session(request: Request) -> str:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise error(401, "UNAUTHENTICATED", "Sign in required")
        with db.connect() as connection:
            row = connection.execute(
                "SELECT digest FROM sessions WHERE digest=? AND expires_at>?",
                (digest(token), utc_now()),
            ).fetchone()
        if row is None:
            raise error(401, "UNAUTHENTICATED", "Sign in required")
        return token

    Session = Annotated[str, Depends(current_session)]

    def require_csrf(request: Request, session: Session, x_csrf_token: Annotated[str | None, Header()] = None) -> None:
        require_origin(request)
        cookie = request.cookies.get(CSRF_COOKIE)
        if not cookie or not x_csrf_token or not hmac.compare_digest(cookie, x_csrf_token):
            raise error(403, "CSRF_INVALID", "CSRF token is invalid")
        with db.connect() as connection:
            row = connection.execute("SELECT csrf_digest FROM sessions WHERE digest=?", (digest(session),)).fetchone()
        if row is None or not hmac.compare_digest(row["csrf_digest"], digest(cookie)):
            raise error(403, "CSRF_INVALID", "CSRF token is invalid")

    WriteSession = Annotated[None, Depends(require_csrf)]

    def identify_key(authorization: str | None) -> int:
        if not authorization or not authorization.startswith("Bearer "):
            raise error(401, "INVALID_API_KEY", "Valid Bearer API key required")
        token = authorization[7:]
        if not token.startswith("laya_") or len(token) < 32:
            raise error(401, "INVALID_API_KEY", "Valid Bearer API key required")
        with db.connect() as connection:
            row = connection.execute(
                "SELECT id FROM api_keys WHERE digest=? AND revoked_at IS NULL", (digest(token),)
            ).fetchone()
        if row is None:
            raise error(401, "INVALID_API_KEY", "Valid Bearer API key required")
        return row["id"]

    def api_key_id(authorization: Annotated[str | None, Header()] = None) -> int:
        return identify_key(authorization)

    ApiKeyId = Annotated[int, Depends(api_key_id)]

    def infer(payload: InferenceRequest, source: str, key_id: int | None) -> dict[str, Any]:
        with router_lock:
            if "router" not in router_holder:
                try:
                    router_holder["router"] = predictor or LayaAdapter(
                        settings.model_dir, settings.device, settings.max_loaded_models
                    )
                except Exception:
                    logger.exception("Failed to initialize model router")
                    raise error(503, "MODEL_UNAVAILABLE", "Model is unavailable")
        started = time.monotonic()
        try:
            result = router_holder["router"].predict(
                payload.state,
                {qid: q.model_dump(exclude_none=True) for qid, q in payload.questions.items()},
                model=None if payload.model == "auto" else payload.model,
            )
            if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
                raise ValueError("Laya returned invalid answers")
            usage = result["usage"]
            if not isinstance(usage["input_tokens"], int) or not isinstance(usage["output_tokens"], int):
                raise ValueError("Laya returned invalid usage")
            if usage["input_tokens"] < 0 or usage["output_tokens"] < 0:
                raise ValueError("Laya returned negative usage")
            if not isinstance(result.get("model"), str):
                raise ValueError("Laya returned invalid model")
        except Exception as exc:
            logger.error("Laya inference failed: %s", type(exc).__name__)
            raise error(503, "MODEL_UNAVAILABLE", "Model is unavailable")
        duration_ms = round((time.monotonic() - started) * 1000)
        try:
            with db.connect() as connection:
                connection.execute(
                    "INSERT INTO usage_events (created_at,source,key_id,model,input_tokens,output_tokens,duration_ms) VALUES (?,?,?,?,?,?,?)",
                    (utc_now(), source, key_id, result["model"], usage["input_tokens"], usage["output_tokens"], duration_ms),
                )
                if key_id is not None:
                    connection.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (utc_now(), key_id))
        except sqlite3.Error:
            logger.exception("Failed to persist usage")
            raise error(503, "USAGE_UNAVAILABLE", "Usage could not be recorded")
        return result

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        for name in ("english", "multilingual", "typed-decisions"):
            directory = settings.model_dir / name
            if (not (directory / "rl_agent_config.json").is_file()
                    or not (directory / "model.safetensors").is_file()
                    or not (directory / "tokenizer" / "tokenizer.json").is_file()
                    or not (directory / "encoder" / "config.json").is_file()):
                raise error(503, "MODEL_UNAVAILABLE", f"Model files for {name} are missing")
        return {"status": "ready"}

    @app.post("/internal/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, str]:
        require_origin(request)
        source = request.client.host if request.client else "unknown"
        since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(timespec="seconds")
        with db.connect() as connection:
            connection.execute("DELETE FROM login_attempts WHERE attempted_at<?", (since,))
            attempts = connection.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE source=? AND username=?",
                (source, payload.username),
            ).fetchone()[0]
            if attempts >= 5:
                raise error(429, "LOGIN_RATE_LIMITED", "Too many login attempts. Try again later")
            connection.execute("INSERT INTO login_attempts VALUES (?,?,?)", (source, payload.username, utc_now()))
        try:
            valid_password = hasher.verify(settings.admin_password_hash, payload.password)
        except VerificationError:
            valid_password = False
        if payload.username != settings.admin_username or not valid_password:
            raise error(401, "INVALID_CREDENTIALS", "Invalid username or password")
        with db.connect() as connection:
            connection.execute("DELETE FROM login_attempts WHERE source=? AND username=?", (source, payload.username))
        session = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)).isoformat(timespec="seconds")
        with db.connect() as connection:
            connection.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(session), digest(csrf), expires))
        cookie_options = {"secure": settings.secure_cookie, "samesite": "lax", "path": "/", "max_age": settings.session_hours * 3600}
        response.set_cookie(SESSION_COOKIE, session, httponly=True, **cookie_options)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **cookie_options)
        return {"username": settings.admin_username}

    @app.get("/internal/auth/session")
    def session(request: Request, session: Session) -> dict[str, str]:
        return {"username": settings.admin_username, "csrf_token": request.cookies.get(CSRF_COOKIE, "")}

    @app.post("/internal/auth/logout")
    def logout(request: Request, response: Response, session: Session, _: WriteSession) -> dict[str, bool]:
        with db.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE digest=?", (digest(session),))
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
        return {"ok": True}

    @app.get("/internal/api-keys")
    def list_keys(session: Session) -> list[dict[str, Any]]:
        with db.connect() as connection:
            rows = connection.execute(
                "SELECT id,name,mask,created_at,revoked_at,last_used_at FROM api_keys ORDER BY id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    @app.post("/internal/api-keys", status_code=201)
    def create_key(payload: CreateKeyRequest, session: Session, _: WriteSession) -> dict[str, Any]:
        token = "laya_" + secrets.token_urlsafe(32)
        mask = "laya_••••" + token[-6:]
        with db.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO api_keys (name,digest,mask,created_at) VALUES (?,?,?,?)",
                (payload.name, digest(token), mask, utc_now()),
            )
        return {"id": cursor.lastrowid, "name": payload.name, "key": token, "mask": mask}

    @app.post("/internal/api-keys/{key_id}/revoke")
    def revoke_key(key_id: int, session: Session, _: WriteSession) -> dict[str, bool]:
        with db.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (utc_now(), key_id),
            )
        if cursor.rowcount == 0:
            raise error(404, "KEY_NOT_FOUND", "Active API key not found")
        return {"ok": True}

    @app.post("/v1/systemone")
    def systemone(key_id: ApiKeyId, payload: InferenceRequest) -> dict[str, Any]:
        return infer(payload, "api_key", key_id)

    @app.post("/internal/playground")
    def playground(payload: InferenceRequest, session: Session, _: WriteSession) -> dict[str, Any]:
        return infer(payload, "playground", None)

    @app.get("/internal/usage")
    def usage(session: Session) -> dict[str, Any]:
        with db.connect() as connection:
            totals = connection.execute(
                "SELECT COUNT(*) requests, COALESCE(SUM(input_tokens),0) input_tokens, COALESCE(SUM(output_tokens),0) output_tokens FROM usage_events"
            ).fetchone()
            daily = connection.execute(
                "SELECT substr(created_at,1,10) day, COUNT(*) requests, SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens FROM usage_events GROUP BY day ORDER BY day"
            ).fetchall()
            sources = connection.execute(
                "SELECT source, key_id, COUNT(*) requests, SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens FROM usage_events GROUP BY source,key_id ORDER BY requests DESC"
            ).fetchall()
        return {"totals": dict(totals), "daily": [dict(row) for row in daily], "sources": [dict(row) for row in sources]}

    if settings.frontend_dir.is_dir():
        app.frontend("/", directory=str(settings.frontend_dir))
    return app


app = create_app()

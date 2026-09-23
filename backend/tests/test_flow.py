import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

os.environ.setdefault("LAYA_ADMIN_USERNAME", "test-admin")
os.environ.setdefault("LAYA_ADMIN_PASSWORD_HASH", PasswordHasher().hash("test-password"))
os.environ.setdefault("LAYA_PUBLIC_ORIGIN", "http://testserver")
os.environ.setdefault("LAYA_ALLOW_INSECURE_LOCAL", "1")
os.environ.setdefault("LAYA_DATABASE_PATH", "/tmp/laya-server-import-test.sqlite3")

from server.config import Settings  # noqa: E402
from server.main import create_app  # noqa: E402


class FakePredictor:
    def __init__(self):
        self.calls = 0

    def predict(self, state, questions, model=None):
        self.calls += 1
        assert set(questions) == {"flag", "intent", "score"}
        return {
            "model": "laya-rl-agent",
            "answers": {"flag": {"value": True}, "intent": {"value": "refund"}, "score": {"value": 2}},
            "usage": {"input_tokens": 37, "output_tokens": 0},
        }


PAYLOAD = {
    "state": {"message": "I need a refund today"},
    "questions": {
        "flag": {"type": "noul", "instructions": "Is it urgent?"},
        "intent": {"type": "choice", "instructions": "What does the user want?", "criteria": {"refund": "money back", "help": "technical help"}},
        "score": {"type": "score", "instructions": "How urgent?", "criteria": ["low", "medium", "high"]},
    },
}


def test_admin_password_from_environment(tmp_path, monkeypatch):
    password = "0123456789"
    monkeypatch.setenv("LAYA_ADMIN_USERNAME", "configured-admin")
    monkeypatch.setenv("LAYA_ADMIN_PASSWORD", password)
    monkeypatch.setenv("LAYA_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setenv("LAYA_PUBLIC_ORIGIN", "http://testserver")
    monkeypatch.setenv("LAYA_ALLOW_INSECURE_LOCAL", "1")
    monkeypatch.setenv("LAYA_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    settings = Settings.from_env()
    assert settings.admin_password_hash != password
    assert settings.admin_password_hash.startswith("$argon2id$")
    client = TestClient(create_app(settings, FakePredictor()))
    response = client.post(
        "/internal/auth/login",
        json={"username": "configured-admin", "password": password},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200

    monkeypatch.setenv("LAYA_ADMIN_PASSWORD_HASH", PasswordHasher().hash(password))
    with pytest.raises(RuntimeError, match="exactly one"):
        Settings.from_env()
    monkeypatch.setenv("LAYA_ADMIN_PASSWORD", "")
    assert Settings.from_env().admin_password_hash == os.environ["LAYA_ADMIN_PASSWORD_HASH"]
    monkeypatch.setenv("LAYA_ADMIN_PASSWORD_HASH", "")
    with pytest.raises(RuntimeError, match="exactly one"):
        Settings.from_env()
    monkeypatch.setenv("LAYA_ADMIN_PASSWORD", "123456789")
    with pytest.raises(RuntimeError, match="at least 10"):
        Settings.from_env()


def test_login_key_inference_usage_revoke_logout(tmp_path):
    fake = FakePredictor()
    db_path = tmp_path / "db.sqlite3"
    settings = Settings("admin", PasswordHasher().hash("correct horse battery staple"), db_path,
                        "http://testserver", False, 1, tmp_path / "models", None, 1, tmp_path / "missing-dist")
    client = TestClient(create_app(settings, fake))
    origin = {"Origin": "http://testserver"}

    assert client.get("/internal/api-keys").status_code == 401
    assert client.post("/internal/auth/login", json={"username": "admin", "password": "wrong"}, headers=origin).status_code == 401
    assert client.post("/internal/auth/login", json={"username": "admin", "password": "correct horse battery staple"}, headers=origin).status_code == 200
    csrf = client.get("/internal/auth/session").json()["csrf_token"]
    assert csrf
    assert client.post("/internal/api-keys", json={"name": "production"}, headers=origin).status_code == 403
    assert client.post("/internal/api-keys", json={"name": "production"}, headers={"X-CSRF-Token": csrf}).status_code == 403
    assert client.post("/internal/api-keys", json={"name": "production"}, headers={**origin, "X-CSRF-Token": "incorrect"}).status_code == 403
    write_headers = {**origin, "X-CSRF-Token": csrf}
    created = client.post("/internal/api-keys", json={"name": "production"}, headers=write_headers)
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    key_id = created.json()["id"]
    listing = client.get("/internal/api-keys").json()
    assert key not in str(listing)
    assert listing[0]["mask"].endswith(key[-6:])
    with sqlite3.connect(db_path) as connection:
        assert key not in str(connection.execute("SELECT * FROM api_keys").fetchall())

    assert client.post("/v1/systemone", json=PAYLOAD).status_code == 401
    assert client.post("/v1/systemone", json={"questions": {}}, headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.post("/v1/systemone", json=PAYLOAD, headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert fake.calls == 0
    invalid = client.post("/v1/systemone", json={**PAYLOAD, "model": "wrong"}, headers={"Authorization": f"Bearer {key}"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "VALIDATION_ERROR"
    missing = client.post("/v1/systemone", json={"questions": PAYLOAD["questions"]}, headers={"Authorization": f"Bearer {key}"})
    assert missing.status_code == 422
    assert missing.json()["detail"]["errors"][0]["loc"] == ["body", "state"]
    invalid_score = client.post(
        "/v1/systemone",
        json={
            **PAYLOAD,
            "questions": {
                "score": {"type": "score", "instructions": "How urgent?", "criteria": ["same", "same"]},
            },
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert invalid_score.status_code == 422
    assert invalid_score.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert fake.calls == 0
    prediction = client.post("/v1/systemone", json=PAYLOAD, headers={"Authorization": f"Bearer {key}"})
    assert prediction.status_code == 200, prediction.text
    assert prediction.json()["usage"] == {"input_tokens": 37, "output_tokens": 0}
    assert set(prediction.json()["answers"]) == set(PAYLOAD["questions"])
    assert fake.calls == 1
    assert client.get("/internal/usage").json()["totals"] == {"requests": 1, "input_tokens": 37, "output_tokens": 0}
    debug = client.post("/internal/playground", json=PAYLOAD, headers=write_headers)
    assert debug.status_code == 200
    usage = client.get("/internal/usage").json()
    assert usage["totals"] == {"requests": 2, "input_tokens": 74, "output_tokens": 0}
    assert {item["source"] for item in usage["sources"]} == {"api_key", "playground"}

    assert client.post(f"/internal/api-keys/{key_id}/revoke", headers=write_headers).status_code == 200
    assert client.post("/v1/systemone", json=PAYLOAD, headers={"Authorization": f"Bearer {key}"}).status_code == 401
    assert fake.calls == 2
    assert client.post("/internal/auth/logout", headers=write_headers).status_code == 200
    assert client.get("/internal/api-keys").status_code == 401

    restarted = TestClient(create_app(settings, fake))
    assert restarted.post("/v1/systemone", json=PAYLOAD, headers={"Authorization": f"Bearer {key}"}).status_code == 401
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 2


def test_rate_limit_expiry_and_model_failure(tmp_path):
    class UnavailablePredictor:
        def predict(self, state, questions, model=None):
            raise FileNotFoundError("secret internal model path")

    db_path = tmp_path / "db.sqlite3"
    settings = Settings("admin", PasswordHasher().hash("password"), db_path,
                        "http://testserver", False, 1, tmp_path / "models", None, 1, tmp_path / "missing-dist")
    client = TestClient(create_app(settings, UnavailablePredictor()))
    origin = {"Origin": "http://testserver"}
    assert client.get("/health/ready").json()["detail"]["code"] == "MODEL_UNAVAILABLE"
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    for _ in range(5):
        assert client.post("/internal/auth/login", json={"username": "admin", "password": "wrong"}, headers=origin).status_code == 401
    assert client.post("/internal/auth/login", json={"username": "admin", "password": "password"}, headers=origin).status_code == 429
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM login_attempts")
    assert client.post("/internal/auth/login", json={"username": "admin", "password": "password"}, headers=origin).status_code == 200
    csrf = client.get("/internal/auth/session").json()["csrf_token"]
    created = client.post("/internal/api-keys", json={"name": "test"}, headers={**origin, "X-CSRF-Token": csrf})
    key = created.json()["key"]
    response = client.post("/v1/systemone", json=PAYLOAD, headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MODEL_UNAVAILABLE"
    assert "secret internal" not in response.text
    assert client.get("/internal/usage").json()["totals"]["requests"] == 0
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get("/internal/api-keys").status_code == 401


def test_concurrent_inference_requests_are_not_rejected(tmp_path):
    class ConcurrentPredictor(FakePredictor):
        def __init__(self):
            super().__init__()
            self.started = Barrier(3, timeout=10)

        def predict(self, state, questions, model=None):
            self.started.wait()
            return super().predict(state, questions, model)

    settings = Settings("admin", PasswordHasher().hash("test-password"), tmp_path / "db.sqlite3",
                        "http://testserver", False, 1, tmp_path / "models", None, 1, tmp_path / "missing-dist")
    app = create_app(settings, ConcurrentPredictor())
    client = TestClient(app)
    origin = {"Origin": "http://testserver"}
    assert client.post("/internal/auth/login", json={"username": "admin", "password": "test-password"}, headers=origin).status_code == 200
    csrf = client.get("/internal/auth/session").json()["csrf_token"]
    key = client.post("/internal/api-keys", json={"name": "parallel"},
                      headers={**origin, "X-CSRF-Token": csrf}).json()["key"]

    def request(index: int):
        if index == 2:
            return client.post("/internal/playground", json=PAYLOAD,
                               headers={**origin, "X-CSRF-Token": csrf})
        return TestClient(app).post("/v1/systemone", json=PAYLOAD, headers={"Authorization": f"Bearer {key}"})

    with ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(request, range(3)))

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert client.get("/internal/usage").json()["totals"]["requests"] == 3
    with sqlite3.connect(settings.database_path) as connection:
        assert dict(connection.execute("SELECT source, COUNT(*) FROM usage_events GROUP BY source").fetchall()) == {
            "api_key": 2, "playground": 1,
        }


def test_question_criteria_validation():
    from server.schemas import ChoiceQuestion, ScoreQuestion
    from pydantic import ValidationError

    valid_score = ScoreQuestion(instructions="Rate", type="score", criteria=["low", "medium", "high"])
    assert valid_score.criteria == ["low", "medium", "high"]

    with pytest.raises(ValidationError, match="score criteria labels must be nonempty and unique"):
        ScoreQuestion(instructions="Rate", type="score", criteria=["low", "low"])

    with pytest.raises(ValidationError, match="score criteria labels must be nonempty and unique"):
        ScoreQuestion(instructions="Rate", type="score", criteria=["low", "   "])

    ChoiceQuestion(instructions="Choose", type="choice", criteria=["option_a", "option_b"])
    ChoiceQuestion(instructions="Choose", type="choice", criteria={"option_a": "desc A", "option_b": "desc B"})

    with pytest.raises(ValidationError, match="choice labels must be nonempty and unique"):
        ChoiceQuestion(instructions="Choose", type="choice", criteria=["opt", "opt"])

    with pytest.raises(ValidationError, match="choice labels must be nonempty and unique"):
        ChoiceQuestion(instructions="Choose", type="choice", criteria=["opt", "  "])


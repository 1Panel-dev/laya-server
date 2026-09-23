"""Exercise login, key management and the public API against a local Laya checkpoint."""

import os
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from argon2 import PasswordHasher
from fastapi.testclient import TestClient


with TemporaryDirectory() as temporary:
    password = "smoke-" + secrets.token_urlsafe(24)
    os.environ["LAYA_ADMIN_USERNAME"] = "smoke-admin"
    os.environ["LAYA_ADMIN_PASSWORD_HASH"] = PasswordHasher().hash(password)
    os.environ["LAYA_PUBLIC_ORIGIN"] = "http://testserver"
    os.environ["LAYA_ALLOW_INSECURE_LOCAL"] = "1"
    os.environ["LAYA_DATABASE_PATH"] = str(Path(temporary) / "smoke.sqlite3")
    os.environ["LAYA_MODEL_DIR"] = os.environ.get("LAYA_MODEL_DIR", "models")
    os.environ.setdefault("HF_HOME", str(Path(os.environ["LAYA_MODEL_DIR"]) / ".cache"))
    os.environ["LAYA_DEVICE"] = "cpu"
    os.environ["LAYA_FRONTEND_DIR"] = str(Path(temporary) / "no-frontend")
    from server.main import app

    client = TestClient(app)
    assert client.get("/health/ready").status_code == 200
    origin = {"Origin": "http://testserver"}
    login = client.post("/internal/auth/login", json={"username": "smoke-admin", "password": password}, headers=origin)
    assert login.status_code == 200, login.text
    csrf = client.get("/internal/auth/session").json()["csrf_token"]
    write_headers = {**origin, "X-CSRF-Token": csrf}
    created = client.post("/internal/api-keys", json={"name": "real-model-smoke"}, headers=write_headers)
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    english_payload = {
        "state": {"message": "I was charged twice and need a refund today."},
        "model": "english",
        "questions": {
            "refund": {"type": "noul", "instructions": "Does the customer ask for a refund?"},
            "intent": {"type": "choice", "instructions": "What does the customer want?", "criteria": {"refund": "money returned", "help": "technical assistance"}},
            "urgency": {"type": "score", "instructions": "How urgent is this request?", "criteria": ["not urgent", "moderately urgent", "very urgent"]},
        },
    }
    headers = {"Authorization": f"Bearer {key}"}
    chinese_payload = {
        **english_payload,
        "state": {"message": "我的账户被重复扣费了，请尽快退款。"},
        "model": "multilingual",
    }
    profile = os.environ.get("LAYA_MODEL_PROFILE", "all")
    if profile == "multilingual":
        cases = (
            (chinese_payload, "multilingual"),
            ({**english_payload, "model": "auto"}, "multilingual"),
        )
        assert client.get("/internal/models").json() == {"models": ["auto", "multilingual"]}
        assert client.post("/v1/systemone", json=english_payload, headers=headers).status_code == 422
    else:
        cases = (
            (english_payload, "english"),
            (chinese_payload, "multilingual"),
            ({**chinese_payload, "model": "auto"}, "multilingual"),
            ({**english_payload, "model": "typed-decisions"}, "typed-decisions"),
        )
    results = []
    for payload, expected_route in cases:
        prediction = client.post("/v1/systemone", json=payload, headers=headers)
        assert prediction.status_code == 200, prediction.text
        data = prediction.json()
        assert set(data["answers"]) == set(payload["questions"])
        assert isinstance(data["usage"]["input_tokens"], int)
        assert isinstance(data["usage"]["output_tokens"], int)
        assert data["routing"]["model"] == expected_route, data["routing"]
        results.append(data)
    usage = client.get("/internal/usage").json()["totals"]
    assert usage["requests"] == len(cases)
    assert usage["input_tokens"] == sum(item["usage"]["input_tokens"] for item in results)
    assert client.post(f"/internal/api-keys/{created.json()['id']}/revoke", headers=write_headers).status_code == 200
    assert client.post("/v1/systemone", json=payload, headers=headers).status_code == 401
    print({"result": "passed", "routes": [item["routing"]["model"] for item in results],
           "input_tokens": usage["input_tokens"], "answer_ids": list(results[0]["answers"])})

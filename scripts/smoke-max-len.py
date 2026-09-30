"""Verify request-scoped long-context inference with the pinned multilingual checkpoint."""

import json
import os
import platform
import resource
import secrets
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from argon2 import PasswordHasher
from fastapi.testclient import TestClient


def peak_memory_mib():
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(maximum / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


with TemporaryDirectory() as temporary:
    password = "smoke-" + secrets.token_urlsafe(24)
    model_dir = Path(os.environ.get("LAYA_MODEL_DIR", "models")).resolve()
    os.environ["LAYA_ADMIN_USERNAME"] = "smoke-admin"
    os.environ.pop("LAYA_ADMIN_PASSWORD", None)
    os.environ["LAYA_ADMIN_PASSWORD_HASH"] = PasswordHasher().hash(password)
    os.environ["LAYA_DATABASE_PATH"] = str(Path(temporary) / "smoke.sqlite3")
    os.environ["LAYA_MODEL_DIR"] = str(model_dir)
    os.environ["LAYA_MODEL_PROFILE"] = "multilingual"
    os.environ["LAYA_DEVICE"] = "cpu"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["LAYA_FRONTEND_DIR"] = str(Path(temporary) / "no-frontend")

    from server.laya_adapter import LayaAdapter
    from server.main import create_app
    import torch
    from transformers import AutoTokenizer

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    adapter = LayaAdapter(model_dir, "cpu", 1, "multilingual")
    from laya.common import build_sequence

    tokenizer = AutoTokenizer.from_pretrained(model_dir / "multilingual" / "tokenizer", local_files_only=True)
    state = "This is ordinary background context. " * 1350 + "TAIL_SENTINEL_ZX921. Please refund the duplicate charge."
    question = {"type": "noul", "instructions": "Does this customer request a refund?"}
    internal = {"t": "noul", "ins": question["instructions"], "crit": None}
    encoded = {}
    for maximum in (1024, 8192):
        ids, _ = build_sequence(tokenizer, state, internal, maximum, 256)
        encoded[maximum] = len(ids)
        assert ("TAIL_SENTINEL_ZX921" in tokenizer.decode(ids)) == (maximum == 8192)
    assert encoded[1024] == 1024
    assert 1024 < encoded[8192] <= 8192
    state_tokens = len(tokenizer.encode(state, add_special_tokens=False))

    measurements = []
    with TestClient(create_app(predictor=adapter)) as client:
        assert client.post("/internal/auth/login", json={"username": "smoke-admin", "password": password}).status_code == 200
        csrf = client.get("/internal/auth/session").json()["csrf_token"]
        write_headers = {"X-CSRF-Token": csrf}
        created = client.post("/internal/api-keys", json={"name": "long-input-smoke"}, headers=write_headers)
        assert created.status_code == 201, created.text
        bearer = {"Authorization": f"Bearer {created.json()['key']}"}
        payload = {"state": state, "questions": {"refund": question}, "model": "multilingual"}
        cases = (
            ("/v1/systemone", {}, bearer, 1024),
            ("/internal/playground", {"max_len": 8192}, write_headers, 8192),
            ("/v1/systemone", {}, bearer, 1024),
        )
        for endpoint, options, headers, maximum in cases:
            started = time.perf_counter()
            response = client.post(endpoint, json={**payload, **options}, headers=headers)
            duration = round(time.perf_counter() - started, 3)
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["routing"]["model"] == "multilingual"
            assert data["answers"]["refund"]["type"] == "noul"
            usage = data["usage"]
            assert usage["input_tokens"] == encoded[maximum], usage
            assert usage["output_tokens"] == 0, usage
            assert usage["state_tokens"] == state_tokens, usage
            assert usage["truncated"] is (maximum == 1024), usage
            assert (usage["state_tokens_dropped"] > 0) == (maximum == 1024), usage
            assert usage["truncated_questions"] == (["refund"] if maximum == 1024 else []), usage
            measurements.append({"endpoint": endpoint, "max_len": options.get("max_len"),
                                 "input_tokens": data["usage"]["input_tokens"], "seconds": duration,
                                 "peak_memory_mib": peak_memory_mib()})
        totals = client.get("/internal/usage").json()["totals"]
        assert totals == {"requests": len(cases), "input_tokens": sum(case["input_tokens"] for case in measurements), "output_tokens": 0}
        sources = client.get("/internal/usage").json()["sources"]
        assert {item["source"]: item["requests"] for item in sources} == {"api_key": 2, "playground": 1}
        assert adapter.router.load("multilingual").cfg["max_len"] == 1024
    print(json.dumps({"result": "passed", "hardware": f"{platform.system()} {platform.machine()}",
                      "device": "cpu", "torch_threads": torch.get_num_threads(), "question_count": 1,
                      "measurements": measurements, "totals": totals}, ensure_ascii=False))

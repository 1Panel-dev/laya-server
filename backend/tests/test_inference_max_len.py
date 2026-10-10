from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from argon2 import PasswordHasher
from conftest import wait_for_usage

from server.config import Settings


PAYLOAD = {"state": "Please refund the duplicate charge.",
           "questions": {"refund": {"type": "noul", "instructions": "Is a refund requested?"}}}


class RecordingPredictor:
    def __init__(self):
        self.calls = []
        self.barrier = None
        self.input_tokens = 37

    def predict(self, state, questions, model=None, **overrides):
        if self.barrier is not None:
            self.barrier.wait()
        self.calls.append((state, model, overrides))
        return {"model": "laya-rl-agent", "answers": {qid: {"type": "noul", "probability": 0.9} for qid in questions},
                "usage": {"input_tokens": self.input_tokens, "output_tokens": 0}}


@pytest.fixture(scope="module")
def password_hash():
    return PasswordHasher().hash("test-password")


@pytest.fixture
def inference_client(tmp_path, monkeypatch, password_hash, client_factory):
    monkeypatch.setenv("LAYA_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("LAYA_ADMIN_PASSWORD_HASH", password_hash)
    monkeypatch.delenv("LAYA_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("LAYA_DATABASE_PATH", str(tmp_path / "import.sqlite3"))
    from server.main import create_app

    predictor = RecordingPredictor()
    settings = Settings("admin", password_hash, tmp_path / "db.sqlite3", 1,
                        tmp_path / "models", None, 1, tmp_path / "missing-dist", "multilingual")
    client = client_factory(create_app(settings, predictor))
    assert client.post("/internal/auth/login", json={"username": "admin", "password": "test-password"}).status_code == 200
    csrf = client.get("/internal/auth/session").json()["csrf_token"]
    playground_headers = {"X-CSRF-Token": csrf}
    key = client.post("/internal/api-keys", json={"name": "max-len-test"}, headers=playground_headers).json()["key"]
    headers = {"/v1/systemone": {"Authorization": f"Bearer {key}"},
               "/internal/playground": playground_headers}
    yield client, predictor, headers


@pytest.mark.parametrize("endpoint", ["/v1/systemone", "/internal/playground"])
@pytest.mark.parametrize("options", [{}, {"max_len": None}, {"max_len": 512}, {"max_len": 3000}, {"max_len": 8192}])
def test_max_len_valid_and_default_requests(inference_client, endpoint, options):
    client, predictor, headers = inference_client
    response = client.post(endpoint, json={**PAYLOAD, **options}, headers=headers[endpoint])
    assert response.status_code == 200, response.text
    expected = {} if options.get("max_len") is None else options
    assert predictor.calls == [(PAYLOAD["state"], "multilingual", expected)]
    assert wait_for_usage(client, 1)["totals"] == {
        "requests": 1, "input_tokens": 37, "output_tokens": 0,
    }


@pytest.mark.parametrize("endpoint", ["/v1/systemone", "/internal/playground"])
@pytest.mark.parametrize("value", [-1, 0, 511, 8193, True, False, "8192", 8192.0, 1024.5, [], {}])
def test_max_len_invalid_requests_do_not_infer(inference_client, endpoint, value):
    client, predictor, headers = inference_client
    response = client.post(endpoint, json={**PAYLOAD, "max_len": value}, headers=headers[endpoint])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert detail["errors"][0]["loc"] == ["body", "max_len"]
    assert predictor.calls == []
    assert client.get("/internal/usage").json()["totals"]["requests"] == 0


def test_concurrent_max_len_requests_keep_individual_budgets(inference_client):
    client, predictor, headers = inference_client
    predictor.barrier = Barrier(3, timeout=10)
    cases = [("default", {}), ("medium", {"max_len": 2048}), ("long", {"max_len": 8192})]

    def request(case):
        state, options = case
        endpoint = "/internal/playground" if state == "long" else "/v1/systemone"
        return client.post(endpoint, json={**PAYLOAD, "state": state, **options}, headers=headers[endpoint])

    with ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(request, cases))
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert {state: overrides for state, model, overrides in predictor.calls} == dict(cases)
    assert wait_for_usage(client, 3)["totals"]["requests"] == 3


@pytest.mark.parametrize("endpoint", ["/v1/systemone", "/internal/playground"])
def test_multi_question_usage_is_not_capped_by_max_len(inference_client, endpoint):
    client, predictor, headers = inference_client
    predictor.input_tokens = 600
    questions = {**PAYLOAD["questions"], "urgent": {"type": "noul", "instructions": "Is the request urgent?"}}
    response = client.post(endpoint, json={**PAYLOAD, "questions": questions, "max_len": 512}, headers=headers[endpoint])
    assert response.status_code == 200, response.text
    assert set(response.json()["answers"]) == set(questions)
    assert response.json()["usage"]["input_tokens"] == 600
    assert wait_for_usage(client, 1)["totals"]["input_tokens"] == 600


@pytest.mark.parametrize("endpoint", ["/v1/systemone", "/internal/playground"])
@pytest.mark.parametrize("storage_error", [False, True], ids=["blocked-storage", "failed-storage"])
def test_usage_storage_does_not_block_successful_inference(inference_client, monkeypatch, endpoint, storage_error):
    import sqlite3
    from threading import Event
    from server.usage_writer import UsageWriter

    entered = Event()
    release = Event()
    original = UsageWriter._write_batch

    def blocked_write(connection, batch):
        entered.set()
        assert release.wait(5)
        if storage_error:
            raise sqlite3.OperationalError("simulated slow storage failure")
        original(connection, batch)

    monkeypatch.setattr(UsageWriter, '_write_batch', staticmethod(blocked_write))
    client, predictor, headers = inference_client
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            response = pool.submit(client.post, endpoint, json=PAYLOAD, headers=headers[endpoint])
            assert entered.wait(3)
            # The writer is still blocked here: HTTP completion cannot depend on it.
            result = response.result(timeout=1)
            assert result.status_code == 200
            assert result.json()['usage']['input_tokens'] == 37
            assert client.post(endpoint, json=PAYLOAD, headers=headers[endpoint]).status_code == 200
            if endpoint == '/v1/systemone':
                assert client.post(endpoint, json=PAYLOAD).status_code == 401
        finally:
            release.set()

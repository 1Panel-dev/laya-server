import time
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_factory():
    with ExitStack() as stack:
        yield lambda *args, **kwargs: stack.enter_context(TestClient(*args, **kwargs))


def wait_for_usage(client, requests):
    deadline = time.monotonic() + 5
    while True:
        usage = client.get('/internal/usage').json()
        if usage['totals']['requests'] == requests:
            return usage
        assert time.monotonic() < deadline, usage
        time.sleep(0.01)

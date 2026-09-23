import sys
from pathlib import Path
from types import ModuleType

from server.laya_adapter import LayaAdapter


def test_adapter_uses_pinned_router_public_interface(monkeypatch, tmp_path: Path):
    calls = []
    fake_module = ModuleType("laya")

    class Router:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def predict(self, state, questions, model=None):
            calls.append(("predict", state, questions, model))
            return {"model": "laya-rl-agent", "answers": {"q": {"value": True}}, "usage": {"input_tokens": 1, "output_tokens": 0}}

    fake_module.Router = Router
    monkeypatch.setitem(sys.modules, "laya", fake_module)
    adapter = LayaAdapter(tmp_path, "cpu", 2)
    result = adapter.predict("text", {"q": {"type": "noul", "instructions": "yes?"}}, model="english")
    assert calls[0][1]["models"] == {name: str(tmp_path / name) for name in ("english", "multilingual", "typed-decisions")}
    assert calls[0][1]["max_loaded"] == 2
    assert calls[1] == ("predict", "text", {"q": {"type": "noul", "instructions": "yes?"}}, "english")
    assert result["usage"]["input_tokens"] == 1

from pathlib import Path
from typing import Any, Protocol
import sys


class Predictor(Protocol):
    def predict(self, state: Any, questions: dict[str, Any], model: str | None = None) -> dict[str, Any]: ...


class LayaAdapter:
    def __init__(self, model_dir: Path, device: str | None, max_loaded: int):
        checkout = Path(__file__).resolve().parents[2] / "laya"
        if (checkout / "laya" / "__init__.py").is_file():
            # The repository's ignored checkout shadows the installed package when
            # developing from the project root; put its actual package root first.
            if str(checkout) not in sys.path:
                sys.path.insert(0, str(checkout))
            cached = sys.modules.get("laya")
            if cached is not None and getattr(cached, "__file__", None) is None and not hasattr(cached, "Router"):
                del sys.modules["laya"]
        from laya import Router

        models = {name: str(model_dir / name) for name in ("english", "multilingual", "typed-decisions")}
        self.router = Router(models=models, device=device, max_loaded=max_loaded)

    def predict(self, state: Any, questions: dict[str, Any], model: str | None = None) -> dict[str, Any]:
        return self.router.predict(state, questions, model=model)

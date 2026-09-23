"""Fail the image build if the bundled multilingual model cannot infer offline."""

import os
from pathlib import Path

from server.laya_adapter import LayaAdapter


model_dir = Path(os.environ["LAYA_MODEL_DIR"])
assert os.environ["LAYA_MODEL_PROFILE"] == "multilingual"
assert (model_dir / "multilingual" / "model.safetensors").is_file()
for unavailable in ("english", "typed-decisions"):
    assert not (model_dir / unavailable).exists()

predictor = LayaAdapter(model_dir, "cpu", 1, "multilingual")
question = {"flag": {"type": "noul", "instructions": "Does this customer request a refund?"}}
for state in ("Please refund the duplicate charge.", "请退还重复扣除的费用。"):
    result = predictor.predict(state, question)
    assert result["routing"]["model"] == "multilingual", result
    assert "flag" in result["answers"], result
print("Bundled multilingual model passed offline inference in both languages")

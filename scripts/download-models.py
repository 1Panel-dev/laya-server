"""Download selected model files from one pinned Hugging Face snapshot."""

import argparse
import os
import time
from pathlib import Path

from huggingface_hub import hf_hub_download
from requests.exceptions import ConnectionError, SSLError, Timeout


REPO = "convaiinnovations/laya"
REVISION = "1c5edc17a7acd8701df6fc341c0d179f1c62c982"
FILES = (
    "rl_agent_config.json",
    "model.safetensors",
    "tokenizer/tokenizer.json",
    "tokenizer/tokenizer_config.json",
    "encoder/config.json",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("all", "english", "multilingual", "typed-decisions"), default="all")
    selected = parser.parse_args().model
    root = Path(os.environ.get("LAYA_MODEL_DIR", "/models"))
    root.mkdir(parents=True, exist_ok=True)
    names = ("english", "multilingual", "typed-decisions") if selected == "all" else (selected,)
    for name in names:
        prefix = "" if name == "english" else f"{name}/"
        destination = root / "english" if name == "english" else root
        for filename in FILES:
            remote = prefix + filename
            print(f"Downloading {remote} at {REVISION}", flush=True)
            for attempt in range(5):
                try:
                    hf_hub_download(repo_id=REPO, filename=remote, revision=REVISION, local_dir=destination)
                    break
                except (ConnectionError, SSLError, Timeout):
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
    print(f"Models are ready in {root}")


if __name__ == "__main__":
    main()

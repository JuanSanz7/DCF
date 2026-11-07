"""Publishes the app to a Hugging Face Space (Docker). Run by the GitHub Action.

Environment: HF_TOKEN (write token), optional HF_SPACE ("user/name" or just "name"),
DCF_DATABASE_URL and DCF_INVITE_CODE (copied into the Space's secrets).
"""
import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
FRONT_MATTER = """---
title: Value field
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: DCF valuation with Monte Carlo simulation
---

"""

api = HfApi(token=os.environ["HF_TOKEN"])
user = api.whoami()["name"]
space = os.environ.get("HF_SPACE") or "value-field"
repo_id = space if "/" in space else f"{user}/{space}"
api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True, private=False)

for key in ("DCF_DATABASE_URL", "DCF_INVITE_CODE"):
    val = os.environ.get(key)
    if val:
        api.add_space_secret(repo_id, key, val)
        print(f"secret {key} set")

with tempfile.TemporaryDirectory() as tmp:
    dst = Path(tmp)
    for item in ("Dockerfile", "backend", "frontend"):
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, dst / item, ignore=shutil.ignore_patterns(
                "node_modules", "dist", "__pycache__", ".pytest_cache", "tests", "*.egg-info"))
        else:
            shutil.copy2(src, dst / item)
    (dst / "README.md").write_text(FRONT_MATTER + (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(dst),
                      commit_message=f"Deploy {os.environ.get('GITHUB_SHA', 'local')[:7]}",
                      delete_patterns=["*"])
host = repo_id.replace("/", "-").replace("_", "-").replace(".", "-").lower()
url = f"https://{host}.hf.space"
print(f"Deployed. App: {url}  (Space page: https://huggingface.co/spaces/{repo_id})")
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a") as f:
        f.write(f"### Deployed\n\nOpen the app: **{url}**\n\nSpace page (build logs): https://huggingface.co/spaces/{repo_id}\n")

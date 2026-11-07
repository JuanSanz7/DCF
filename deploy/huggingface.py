"""Publishes the app to a Hugging Face Space (Docker). Run by the GitHub Action.

Environment: HF_TOKEN (write token), optional HF_SPACE ("user/name" or just "name"),
DCF_DATABASE_URL and DCF_INVITE_CODE (copied into the Space's secrets).
"""
import json
import os
import shutil
import urllib.parse
import urllib.request
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

def neon_database_url() -> str | None:
    """Asks Neon for the connection string of the project's main branch (no pooler)."""
    key = os.environ.get("NEON_API_KEY")
    if not key:
        return None

    def get(path):
        req = urllib.request.Request("https://console.neon.tech/api/v2" + path,
                                     headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    pid = os.environ.get("NEON_PROJECT_ID")
    if not pid:
        projects = get("/projects")["projects"]
        if len(projects) != 1:
            raise SystemExit(f"Found {len(projects)} Neon projects; set the NEON_PROJECT_ID variable to choose one.")
        pid = projects[0]["id"]
    branches = get(f"/projects/{pid}/branches")["branches"]
    branch = next((b for b in branches if b.get("default")), branches[0])
    dbs = get(f"/projects/{pid}/branches/{branch['id']}/databases")["databases"]
    db = next((d for d in dbs if d["name"] == "neondb"), dbs[0])
    q = urllib.parse.urlencode({"branch_id": branch["id"], "database_name": db["name"],
                                "role_name": db["owner_name"], "pooled": "false"})
    uri = get(f"/projects/{pid}/connection_uri?{q}")["uri"]
    print(f"Neon database: project {pid}, branch {branch['name']}, database {db['name']}")
    return uri


token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE")
if not token:
    raise SystemExit("No Hugging Face token: add a repository secret named HF_TOKEN (or HUGGINGFACE).")
if not os.environ.get("DCF_DATABASE_URL"):
    url = neon_database_url()
    if url:
        os.environ["DCF_DATABASE_URL"] = url
    else:
        print("WARNING: no database configured; saved valuations will be lost when the Space restarts.")

api = HfApi(token=token)
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

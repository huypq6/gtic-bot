"""Phiên bản đang chạy — hiện trên web để biết đã cập nhật chưa.

Prod (docker): stage `version` trong Dockerfile ghi `VERSION.json` từ git lúc build.
Dev: không có file → hỏi git trực tiếp. Không có git → "dev".
"""

import json
import subprocess
import tomllib
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTED_AT = datetime.now(UTC).isoformat(timespec="seconds")


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=3, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _base_version() -> str:
    try:
        return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    except (OSError, KeyError, ValueError):
        return "0.0.0"


@lru_cache
def get_version() -> dict:
    info: dict = {}
    f = ROOT / "VERSION.json"
    if f.is_file():
        try:
            info = json.loads(f.read_text())
        except ValueError:
            info = {}
    if not info.get("commit"):
        info = {
            "commit": _git("rev-parse", "--short", "HEAD"),
            "build": _git("rev-list", "--count", "HEAD"),
            "commit_date": _git("log", "-1", "--format=%cI"),
            "subject": _git("log", "-1", "--format=%s"),
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        }
    info["version"] = info.get("version") or _base_version()
    info["started_at"] = STARTED_AT
    return info

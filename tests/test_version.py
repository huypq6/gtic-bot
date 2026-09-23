"""/api/version — phiên bản hiện trên web."""

import json

from app import version as v


def test_version_from_file(tmp_path, monkeypatch):
    (tmp_path / "VERSION.json").write_text(json.dumps({"commit": "abc1234", "build": "7"}))
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    monkeypatch.setattr(v, "ROOT", tmp_path)
    v.get_version.cache_clear()
    info = v.get_version()
    v.get_version.cache_clear()
    assert info["commit"] == "abc1234" and info["build"] == "7"
    assert info["version"] == "1.2.3"
    assert info["started_at"]


def test_version_falls_back_to_git():
    v.get_version.cache_clear()
    info = v.get_version()
    assert info["version"] and info["commit"]  # repo dev có git

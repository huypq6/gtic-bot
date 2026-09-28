"""GET /strategies/{name}/doc — English by default, `lang=vi` serves `<name>.vi.md` if present."""

import asyncio

import pytest
from fastapi import HTTPException

from app.api.trading import strategy_doc
from app.strategy import strategies as strat_pkg


@pytest.fixture
def docs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(strat_pkg, "__path__", [str(tmp_path)])
    (tmp_path / "foo.md").write_text("english", encoding="utf-8")
    (tmp_path / "foo.vi.md").write_text("vietnamese", encoding="utf-8")
    (tmp_path / "bar.md").write_text("bar english", encoding="utf-8")
    return tmp_path


def _doc(name, **kw):
    return asyncio.run(strategy_doc(name, **kw))["markdown"]


def test_default_is_english(docs_dir):
    assert _doc("foo") == "english"


def test_vi_served_when_present(docs_dir):
    assert _doc("foo", lang="vi") == "vietnamese"


def test_vi_falls_back_to_english(docs_dir):
    assert _doc("bar", lang="vi") == "bar english"


def test_unknown_lang_is_english(docs_dir):
    assert _doc("foo", lang="fr") == "english"


def test_missing_doc_placeholder(docs_dir):
    assert "No methodology" in _doc("nope")


def test_invalid_name(docs_dir):
    with pytest.raises(HTTPException):
        _doc("../etc")

"""Tests for structured.py.

Two kinds:
  * MOCKED (default): the Gemini response is monkeypatched, so no network and no API key.
  * ONLINE (`pytest -m online`): calls the real Gemini API. Needs a real GEMINI_API_KEY in .env.
"""
import json
import os
from types import SimpleNamespace

import pytest

import structured  # imported first: it loads .env
from structured import ExtractionError, Ticket, get_structured

OBJ = {"title": "Login crash", "category": "bug", "priority": 5, "tags": ["auth"], "needs_human": True}
GOOD = json.dumps(OBJ)


def mock_llm(monkeypatch, *replies):
    """Monkeypatch the Gemini client so each call returns the next scripted reply text.

    Returns the list of prompts the model was sent (to assert on retry feedback).
    """
    prompts, it = [], iter(replies)

    def generate_content(model, contents, config):
        prompts.append(contents)
        return SimpleNamespace(text=next(it))

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(structured, "make_client", lambda: fake_client)
    return prompts


# ------------------------------------------------------------- mocked tests
def test_valid_first_try(monkeypatch):
    prompts = mock_llm(monkeypatch, GOOD)
    t = get_structured("x", Ticket)
    assert isinstance(t, Ticket) and t.priority == 5 and len(prompts) == 1


def test_retry_on_bad_json_then_success(monkeypatch):
    prompts = mock_llm(monkeypatch, "{nope", GOOD)
    assert get_structured("x", Ticket).title == "Login crash"
    assert len(prompts) == 2


def test_retry_on_schema_violation_and_error_fed_back(monkeypatch):
    prompts = mock_llm(monkeypatch, json.dumps({**OBJ, "category": "urgent", "priority": 9}), GOOD)
    get_structured("x", Ticket)
    assert "category" in prompts[1] and "priority" in prompts[1]


def test_no_silent_coercion(monkeypatch):
    prompts = mock_llm(monkeypatch, json.dumps({**OBJ, "priority": "5"}), GOOD)
    get_structured("x", Ticket)
    assert len(prompts) == 2


def test_none_text_is_handled(monkeypatch):  # e.g. safety-blocked response
    mock_llm(monkeypatch, None, GOOD)
    assert get_structured("x", Ticket).priority == 5


def test_raises_after_budget(monkeypatch):
    prompts = mock_llm(monkeypatch, "a", "b", "c")
    with pytest.raises(ExtractionError):
        get_structured("x", Ticket, retries=2)
    assert len(prompts) == 3


def test_list_of_models(monkeypatch):
    mock_llm(monkeypatch, json.dumps([OBJ, OBJ]))
    out = get_structured("x", list[Ticket])
    assert len(out) == 2 and all(isinstance(t, Ticket) for t in out)


def test_missing_key_fails_early_and_clearly(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        structured.make_client()  # raises before any client or network call is created


# -------------------------------------------------------------- online test
def _has_real_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return bool(key) and key != "your-api-key-here"


@pytest.mark.online
@pytest.mark.skipif(not _has_real_key(), reason="needs a real GEMINI_API_KEY (set it in .env)")
def test_real_gemini_returns_valid_ticket():
    """Hits the real API. Asserts only what validation guarantees; the wording is up to the model."""
    t = get_structured("Triage this support message:\nApp crashes on login since the update. Fix ASAP!", Ticket)
    assert isinstance(t, Ticket)
    assert 1 <= t.priority <= 5
    assert t.category in {"bug", "feature", "question"}
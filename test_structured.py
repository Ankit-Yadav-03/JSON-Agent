"""Offline tests: scripted fake Gemini client, no API key needed."""
import json
from types import SimpleNamespace

import pytest

from structured import ExtractionError, Ticket, get_structured

OBJ = {"title": "Login crash", "category": "bug", "priority": 5, "tags": ["auth"], "needs_human": True}
GOOD = json.dumps(OBJ)


def fake_client(*replies):
    prompts, it = [], iter(replies)

    def generate_content(model, contents, config):
        prompts.append(contents)
        return SimpleNamespace(text=next(it))

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content), prompts=prompts)


def test_valid_first_try():
    c = fake_client(GOOD)
    t = get_structured("x", Ticket, client=c)
    assert isinstance(t, Ticket) and t.priority == 5 and len(c.prompts) == 1


def test_retry_on_bad_json_then_success():
    c = fake_client("{nope", GOOD)
    assert get_structured("x", Ticket, client=c).title == "Login crash"
    assert len(c.prompts) == 2


def test_retry_on_schema_violation_and_error_fed_back():
    c = fake_client(json.dumps({**OBJ, "category": "urgent", "priority": 9}), GOOD)
    get_structured("x", Ticket, client=c)
    assert "category" in c.prompts[1] and "priority" in c.prompts[1]


def test_no_silent_coercion():
    c = fake_client(json.dumps({**OBJ, "priority": "5"}), GOOD)
    get_structured("x", Ticket, client=c)
    assert len(c.prompts) == 2


def test_none_text_is_handled():  # e.g. safety-blocked response
    c = fake_client(None, GOOD)
    assert get_structured("x", Ticket, client=c).priority == 5


def test_raises_after_budget():
    c = fake_client("a", "b", "c")
    with pytest.raises(ExtractionError):
        get_structured("x", Ticket, retries=2, client=c)
    assert len(c.prompts) == 3


def test_list_of_models():
    c = fake_client(json.dumps([OBJ, OBJ]))
    out = get_structured("x", list[Ticket], client=c)
    assert len(out) == 2 and all(isinstance(t, Ticket) for t in out)
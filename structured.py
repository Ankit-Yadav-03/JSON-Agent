"""Reliable JSON from Gemini: native schema-constrained output + pydantic validation + retry."""
import os
import sys
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, TypeAdapter

load_dotenv()
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")


class Ticket(BaseModel):  # 1. SCHEMA
    title: str = Field(min_length=3, max_length=120)
    category: Literal["bug", "feature", "question"]
    priority: int = Field(ge=1, le=5, description="1 = lowest, 5 = urgent")
    tags: list[str] = Field(default_factory=list, max_length=5)
    needs_human: bool


class ExtractionError(Exception):
    pass


def make_client():
    """Build the Gemini client, failing early with a clear message if the key is missing."""
    key = os.environ.get("GEMINI_API_KEY") 
    if not key or key == "your_api_key_here":
        raise RuntimeError(
            "No API key found. Copy .env.example to .env (next to structured.py) "
            "and set GEMINI_API_KEY to your real key from https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=key)


def get_structured(prompt, schema, retries=2):
    """Return a validated `schema` instance (a BaseModel, list[Model], ...) or raise ExtractionError."""
    client = make_client()
    config = types.GenerateContentConfig(  # native constraint: Gemini is forced to the schema
        response_mime_type="application/json", response_schema=schema
    )
    adapter, contents, err = TypeAdapter(schema), prompt, ""
    for _ in range(retries + 1):
        text = ""
        try:
            text = client.models.generate_content(model=MODEL, contents=contents, config=config).text or ""
            return adapter.validate_json(text, strict=True)  # 2. VALIDATION (rejects bad output)
        except ValueError as e:  # bad JSON or schema violation (pydantic errors subclass ValueError)
            err = str(e)  # 3. RETRY: feed the exact error back
            contents = f"{prompt}\n\nYour previous output:\n{text}\n\nwas invalid:\n{err}\nReturn corrected JSON."
    raise ExtractionError(f"Failed after {retries + 1} attempts. Last error: {err}")


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "App crashes on login since the update, I can't work. Fix ASAP!"
    print(get_structured(f"Triage this support message:\n{msg}", Ticket).model_dump_json(indent=2))
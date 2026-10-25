# Reliable JSON from Gemini

~45 lines: a pydantic schema goes to Gemini as a native `response_schema`, the reply is validated, and failures are retried with the exact error fed back. The caller gets a typed object or an `ExtractionError`, never bad data.

| Requirement | Where |
|---|---|
| Schema | `Ticket` (pydantic `BaseModel`), passed as `response_schema` |
| Validation | `TypeAdapter(schema).validate_json(text, strict=True)`: no coercion, ranges and enums enforced |
| Retry / repair | loop in `get_structured()`: error and bad output go back into the prompt, 2 retries, then `ExtractionError` |

## Run

```bash
pip install -r requirements.txt
cp .env.example .env     # add your GEMINI_API_KEY (free at aistudio.google.com/apikey)
python structured.py "App crashes on login since the update. Fix ASAP!"
```

Other schemas: `get_structured(prompt, MyModel)` or `get_structured(prompt, list[MyModel])`.

## Tests

| Command | What it does | API key needed? |
|---|---|---|
| `pytest -q` | Mocked tests. The Gemini response is **monkeypatched**, so the retry, validation and error paths run deterministically with no network. | No |
| `pytest -m online -q` | One **online** test that calls the real Gemini API and checks the result is a valid `Ticket`. | **Yes**: a real `GEMINI_API_KEY` in `.env` (or exported). Skipped if missing. |

The mocked tests prove the validation and retry logic. They do **not** prove that Gemini accepts your schema or that your key and model name work. Only the online test does that, so run it once before relying on this.

## Troubleshooting: "No API key found"

- `.env` must exist (not just `.env.example`) in the same folder as `structured.py`, with a real `GEMINI_API_KEY=...` and no quotes or spaces around `=`.
- Or skip the file and export it: `export GEMINI_API_KEY=...` (Windows PowerShell: `$env:GEMINI_API_KEY="..."`).
- If `GOOGLE_API_KEY` is also set in your shell, it is used when `GEMINI_API_KEY` is empty, so make sure it isn't a stale key.

## Troubleshooting: "400 API key not valid"

Google rejected the key. The script does not pre-check key format, so a typo, a revoked key, or the untouched `your-api-key-here` placeholder from `.env.example` all end up here. Fix the value in `.env`; retrying will not help, so the script does not retry auth errors.

## Decisions

- **`google-genai` only, no ADK.** ADK is an agent framework (agents, runners, sessions). One structured call doesn't need it, and it would add code, not remove it.
- **Native schema constraint plus our own validation.** Gemini's constrained decoding makes bad output rare, not impossible. Truncation at the output limit, safety blocks (`text` is `None`) and unsupported schema features still happen, so validation and retry stay.
- **Strict validation.** `"5"` is not accepted as an int.
- **No `extra="forbid"` on the model.** Gemini's schema support has historically rejected `additionalProperties`.
- **Tests monkeypatch the client** instead of the code taking an injectable client, which keeps `get_structured` signature minimal.

## Limitations

- Valid shape does not mean a correct answer. Domain rules are on you.
- Retries cost extra calls.
- The default `MODEL` is not verified as current. Check the docs.
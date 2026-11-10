# OffScript backend

An English-only, local voice-agent transcript and prompt evaluation harness. Python owns booking authorization; model-generated confirmation flags never authorize writes. This phase simulates conversations and mock bookings. It does not make calls or process microphone audio.

## Setup and run

From the project root, use Python 3.11 or later:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
python3 backend/cli_eval.py
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Alternatively, `uv venv .venv --python 3.12` and `uv pip install --python .venv/bin/python -r backend/requirements.txt` install the environment. `backend/requirements.lock` records the exact dependency versions used during verification; use it in place of `requirements.txt` to reproduce that environment.

Interactive API documentation: <http://127.0.0.1:8000/docs>. The stack is FastAPI, Uvicorn, Pydantic v2, python-dotenv, httpx, Google GenAI, and the OpenAI Python SDK. The tests use Python's standard `unittest` library.

## Configuration

Replay needs no credentials. To enable live calls, copy `backend/.env.example` to `backend/.env` and enter a fresh provider key there. Environment variables take precedence over that file. Keep keys local; `.env` files are excluded from version control.

| Variable | Default | Meaning |
| --- | --- | --- |
| `EXECUTION_MODE` | `auto` | `auto`, `live`, or `replay` |
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | empty | Selected Gemini credential |
| `OPENAI_API_KEY` | empty | Selected OpenAI credential |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Configurable Gemini model |
| `OPENAI_MODEL` | `gpt-4o-mini` | Configurable OpenAI model |
| `LLM_TIMEOUT_SECONDS` | `20` | Timeout per attempt, maximum 120 seconds |
| `CORS_ORIGINS` | localhost and 127.0.0.1 on port 5173 | Comma-separated allowed frontend origins |

`auto` uses the selected provider if its key exists, otherwise verified replay. A key for the other provider does not enable live mode. Explicit live mode requires a key; a missing key fails server startup. Health reports the configured active mode, not a successful connectivity probe. Models and account access can change: unavailable models produce a visible error, and the configured names can be updated without code changes.

Calls are asynchronous and schema-constrained. Responses are validated again by Pydantic. SDK retries are disabled; the runner permits one retry for connection errors, timeouts, rate limits, and selected server errors. The worst-case provider wait is approximately twice the configured timeout plus a short backoff. Authentication failures, refusals, malformed or truncated responses, and exhausted retries return sanitized errors. A live failure never silently becomes a replay success.

The CLI defaults to replay even when a key exists:

```sh
python3 backend/cli_eval.py               # deterministic replay
python3 backend/cli_eval.py --mode live   # billable provider calls
python3 backend/cli_eval.py --mode auto
```

The CLI saves `backend/eval_report.json`. A replay regression returns exit code 1; a configuration or provider error returns 2. Successful live runs report actual scores rather than requiring a predetermined percentage.

## API examples

All request schemas reject extra fields. Caller text is limited to 4,000 characters. Errors contain `error.code` and an English `error.message`; validation errors add field details without echoing submitted values.

```sh
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/scenarios
curl http://127.0.0.1:8000/api/prompt-diff

curl -X POST http://127.0.0.1:8000/api/compare-turn1 \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"TC-01","execution_mode":"replay"}'
```

Copy `conversation_id` from the comparison into the next request. TC-01 proposes Thursday at 7:00 PM, with a null Turn-1 v2 tool call:

```sh
curl -X POST http://127.0.0.1:8000/api/simulate-turn2 \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"REPLACE_WITH_RETURNED_ID","caller_text":"Yes, please book it."}'

curl -X POST http://127.0.0.1:8000/api/evaluate-suite \
  -H 'Content-Type: application/json' \
  -d '{"execution_mode":"replay"}'
```

`/api/evaluate-suite` also accepts `{}` or an empty body to use the configured execution mode. Comparisons return `v1_result.turn1`, `v2_result.turn1`, and nullable `turn2` fields under each version. The confirmation endpoint returns `v2_result` (the second turn) and that conversation's resulting calendar. The suite includes each comparison with its v2 second turn populated when applicable. A suite's internal conversation IDs are report identifiers and are not registered as interactive sessions.

For custom English text, provide `caller_text` instead of `scenario_id`:

```json
{
  "caller_text": "I'm busy. Could you call Thursday after 6 PM?",
  "execution_mode": "live"
}
```

Exactly one input selector is required. Custom text in replay returns `409 LIVE_MODE_REQUIRED`; explicit live without a key returns `503 API_KEY_REQUIRED`. A comparison pins its mode for Turn 2. Clients cannot submit slot state, confirmation flags, rubric scores, or mutation results to the confirmation endpoint.

## Calendar and booking safeguards

The reference time is **Tuesday, November 10, 2026, at 10:00 AM, Asia/Riyadh**. Tomorrow is Wednesday. Operating hours are Monday–Friday, 09:00 inclusive to 20:00 exclusive. Only the listed slots exist:

| Day | Time | Initial status |
| --- | --- | --- |
| Wednesday | 16:30 | AVAILABLE |
| Thursday | 18:00 | BOOKED_FULL |
| Thursday | 19:00 | AVAILABLE |
| Monday | 10:00 | AVAILABLE |

Every comparison starts fresh. Its v1 and v2 calendars are isolated copies of the same facts. A suite also starts each case fresh and never changes interactive calendars. Turn 2 commits only to the corresponding conversation's v2 calendar.

All Turn-1 attempts are rejected as `PREMATURE_UNCONFIRMED_MUTATION`, even if the model supplies `customer_confirmed=true`. The response retains the attempted tool and raw reply so the rubric can measure the failure.

A pending slot is established only from one exact affirmative available proposal in the spoken reply with an awaiting-confirmation state. Rejected-slot explanations can precede that offer. Turn 2 requires server-verified consent to that pending slot. Contextual “Yes, please book it” works. Questions reject consent even without a question mark, including “Is that confirmed”. Negation, uncertainty, conflicts, and unrecognized phrasing cannot authorize a booking. The parser uses a conservative positive grammar; an unusual but valid English confirmation may need rephrasing. Availability and session expiry are checked under the calendar lock immediately before commit. Duplicate identical submissions return a cached original response without another write; different requests after a completed booking return `409 CONVERSATION_COMPLETED`.

This is a two-turn comparison. A caller correction or requested time change clears the original proposal and returns a server-generated clarification requiring a fresh comparison. Ordinary uncertainty can be clarified against the unchanged proposal. If a live model introduces a different slot during confirmation, pending authority is also cleared; its original reply and attempted tool remain visible for scoring, and a later “Yes” cannot revive the old slot. An opt-out clears authorization before awaiting a provider, so even a failed request leaves the conversation terminal.

Sessions expire 30 minutes after creation. Unknown IDs return 404 and expired stored sessions return 410. Expired sessions may be pruned by later comparisons, after which their IDs return 404. At most 1,000 active interactive sessions are retained. Restarting clears all state. Opt-outs end the simulation without claiming any external do-not-call registry was modified.

## Evaluation and provenance

Replay outputs are **curated, validated fixtures**, not recordings or evidence of live model performance. `execution` on every turn identifies the mode, provider/model when live, and source. Server-generated responses for ended conversations or missing proposals are separately identified.

The four rubric pillars assess booking gates, cue and correction handling, hallucination guards, and spoken brevity. Scores use caller text, raw replies, proposed actions, history, and calendar evidence rather than model self-scores. Busy/driving context carries into confirmation scoring. Availability checks associate each spoken day with its actual time and distinguish affirmative offers from rejected alternatives. Negated statements such as “Nothing is booked yet” do not count as booking claims. Attempted unsafe mutations fail even when the Python boundary blocks them. Every pillar includes evidence. Replies are retained unchanged, including overlong or whitespace-only replies; blank speech fails the voice pillar. Fewer than 25 words means a maximum of 24 whitespace tokens after punctuation normalization.

The Turn-1 headline is the fraction of scenarios passing **all four** pillars, calculated from individual scores. In the replay fixtures, v1 passes TC-05 only (1/5 = 20%); v2 passes all five (5/5 = 100%). Confirmation execution is reported separately: four successful v2 bookings and TC-05's no-booking opt-out. In live mode, the suite confirms the exact slot actually proposed and reports observed results. It never forces the replay percentages.

Expected v2 proposals are Thursday 19:00 for TC-01, Wednesday 16:30 for TC-02, Monday 10:00 for TC-03, Wednesday 16:30 with an unverified ATM-fee disclaimer for TC-04, and no callback for TC-05.

Semantic and naturalness checks are heuristic, especially for custom input. Explicit numeric fee claims, unavailable proposals, false booking states, continued pitching, ignored opt-outs, and known fixture corrections are checked deterministically. The language filter rejects non-Latin scripts and inputs without English letters; it is not a full language classifier and cannot reliably distinguish all languages written in Latin script. The evaluator likewise cannot prove that every possible paraphrase is correct, natural English, or free of invented facts.

This is a reliable **local, single-worker harness**, without authentication, shared persistence, telephony, or public deployment support. Use the documented loopback binding. A shared deployed service needs durable conversation and booking storage, authentication, and cross-worker transactions.

## Verification

```sh
python3 -m pip install -r backend/requirements-dev.txt
python3 -m ruff check backend
python3 -m ruff format --check backend
python3 -m mypy backend
python3 -m unittest discover -s backend/tests -v
python3 backend/cli_eval.py
python3 backend/smoke_api.py  # with the server running on port 8000
```

Ruff and mypy are development-only dependencies configured in the root `pyproject.toml`. Type checking covers every runtime module with required function annotations; tests are checked by execution and Ruff. Tests exercise each audited authorization and scoring regression, the calculated benchmark, calendar isolation, concurrent retries, expiry during generation and lock contention, opt-outs surviving provider errors, runtime/OpenAPI contracts, docs, and CORS. Provider tests include actual Gemini/OpenAI SDK schema serialization and parsing over `httpx.MockTransport`, alongside failure/retry mocks. `smoke_api.py` checks the six real HTTP endpoints, docs, and CORS in replay. Live smoke tests require a fresh locally configured key; mocks never send provider requests.

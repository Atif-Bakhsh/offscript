# OffScript

An English-only voice-agent reliability lab. Compare a naive sales prompt with a state-guarded prompt, inspect four-pillar evaluation evidence, and exercise a Python-controlled mock booking gate.

The application simulates transcripts and callbacks. It runs locally with one backend worker and in-memory conversation state. Restarting the backend clears sessions; sessions also expire after 30 minutes. Authentication, public deployment, durable storage, microphone processing, and telephony are outside this phase.

## Start the application

Use Python 3.11+ and Node.js 22.13+, 24, or 26 (Node 26 was used for verification). From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.lock
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. API documentation is at **http://127.0.0.1:8000/docs**. The frontend server requires port 5173; it does not silently select another port.

The frontend uses React, TypeScript, Vite, native Fetch, and CSS variables. The backend uses FastAPI, Pydantic v2, and asynchronous Gemini/OpenAI SDK clients. See [backend setup and API examples](backend/README.md), [frontend architecture](frontend/README.md), and [design notes](frontend/DESIGN.md).

## Replay and live execution

Startup always requests **replay** for TC-01 and the five-case suite. Replay needs no credentials. Its curated, validated fixtures produce the calculated Turn-1 benchmark of **20% → 100%**, four confirmed callbacks, and five confirmation checks including the opt-out. These fixtures are not proof of live model performance.

The header's backend status describes the backend's configured default. The run-mode selector controls subsequent comparison and suite requests; actual execution provenance is shown with each result. An existing conversation keeps its original mode for confirmation.

For live execution, copy `backend/.env.example` to `backend/.env`, configure a fresh selected provider key, and restart FastAPI. Choose **Live** or **Auto** in the console. Custom caller text requires live execution. Scores reflect the actual model output; provider failures remain visible and never silently turn into replay results. Real provider connectivity requires a valid local key and was not exercised during offline verification.

Credentials belong only in the backend. Never place API keys in frontend environment variables. The optional `frontend/.env.local` may contain only an API URL:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8000
```

That is also the default. Vite provides an `/api` development proxy for convenience. Set `VITE_API_BASE_URL=/` to use that same-origin development proxy; API paths already include `/api`. Backend CORS permits localhost and 127.0.0.1 on port 5173. See `CORS_ORIGINS` in the backend environment template for other local origins.

## Booking and inspection

Selecting a scenario starts a fresh, isolated comparison. Turn 1 cannot mutate the calendar. Edit the second-turn caller text to test affirmative consent, questions, negation, or a changed time; Python determines whether a write is permitted. A rejected baseline tool attempt stays visible even if the agent claims it booked a callback.

After a confirmation result or error, start a fresh comparison to run another trial. Network errors may leave a request's server-side outcome unknown; the UI does not automatically retry POSTs or infer a successful booking. The calendar is updated only from a matching server confirmation response.

**Inspect in arena** shows the exact suite snapshot, labeled read-only. Suite report IDs cannot authorize interactive bookings. Use **Start fresh comparison** to create a new session.

## Verification

```sh
cd frontend
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:e2e  # backend must be running on port 8000
```

Playwright starts or reuses the frontend development server. To check the built application, stop the development server, run `npm run preview`, and execute `FRONTEND_URL=http://127.0.0.1:5173 npm run test:e2e` from another terminal. Preview is for local verification, not a public production server.

Backend verification commands:

```sh
.venv/bin/python backend/cli_eval.py
.venv/bin/python backend/smoke_api.py
```

Exact results and browser coverage are recorded in [frontend/VALIDATION.md](frontend/VALIDATION.md). Dependency versions are locked in `frontend/package-lock.json` and `backend/requirements.lock`.
# offscript

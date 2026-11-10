# Frontend validation

Verified November 9, 2026 on macOS ARM64, Node 26.3.0, npm 11.16.0, and the existing Python 3.12 backend environment. All browser runs used the real replay backend at `http://127.0.0.1:8000`.

| Check | Result |
| --- | --- |
| `npm install` | Completed; dependency versions recorded in `package-lock.json` |
| Dependency audit during final lockfile synchronization | 0 vulnerabilities across production and development dependencies |
| `npm run typecheck` | Passed with zero TypeScript errors |
| `npm run lint` | Passed with zero warnings |
| `npm test` | 24 tests passed across 4 files |
| `npm run build` | Passed; compiled static application in `dist/` |
| `npm run test:e2e` against Vite development server | 11 / 11 passed |
| `FRONTEND_URL=http://127.0.0.1:5173 npm run test:e2e` against production preview | 11 / 11 passed |
| `.venv/bin/python backend/cli_eval.py` | v1 20% (1/5), v2 100% (5/5), confirmation checks 5/5 |
| `.venv/bin/python backend/smoke_api.py` | All six API endpoints, `/docs`, CORS preflight, benchmark, and duplicate booking check passed |

The final locked toolchain includes React / React DOM 19.3.1, TypeScript 5.9.3, Vite 8.3.7, Vitest 5.1.0, ESLint 10.14.0, and Playwright 1.65.0. A clean resolution replaced the initial development dependency tree after its audit reported advisories. The current lockfile includes patched tools and a patched `minimatch` override, exercised by lint and tests.

## Browser coverage

- Automatic TC-01 comparison and five-case suite execute once, using replay.
- All five scenarios display actual server speech, rubric evidence, and tool outcomes.
- TC-01 through TC-04 confirm successfully, commit to the matching calendar, and preserve Turn-1 speech after Turn 2.
- Each new comparison resets calendar availability; suite runs and inspection do not authorize writes to interactive sessions.
- TC-05 displays the terminal opt-out and has no confirmation control.
- Calculated metrics show **20% → 100%**, **4 / 4** confirmed bookings, **5 / 5** confirmation checks, and **0** observed Turn-1 mutations.
- Questions without punctuation, negated confirmation, and a changed slot do not book. A fresh comparison restores the intended workflow.
- Suite inspection displays the exact read-only snapshot and requires a separate fresh comparison for interaction.
- Custom replay input receives the real backend `LIVE_MODE_REQUIRED` error while preserving the submitted caller line.
- Controlled responses verify expired sessions, provider timeout, authentication errors, missing credentials, field diagnostics, malformed payloads, and network loss without automatic retries or fabricated replay successes.
- The main real-backend workflow produces zero application console errors, zero uncaught page errors, and zero third-party font network errors.
- Desktop at 1440 × 1000 and mobile at 390 × 844 were visually reviewed. The wide scorecard scrolls inside its own container; JSON panels do not widen the document.
- Keyboard scenario selection and confirmation commit work. Reduced-motion mode removes transitions. Visible status text supplements semantic colors.

The mobile test initially found that absolutely positioned screen-reader text in the table escaped a static scroll container. Establishing that container as a positioning context fixed the document overflow; the regression is covered by the passing browser check. A development watcher exclusion also prevents generated browser reports from triggering application reloads and additional startup requests.

## Unit and component coverage

Request exclusivity; nested response validation; sanitized errors; malformed simulation clocks; evidence-derived KPIs; live confirmation text using the actual proposal; StrictMode initialization; stale comparison and confirmation responses; duplicate submission locks; pinned conversation provenance; independent metadata failures; read-only snapshots; raw baseline booking claims; terminal opt-out controls; and fresh-comparison recovery.

Browser screenshots are generated at `test-results/desktop.png`, `test-results/mobile.png`, and `test-results/arena.png`. Reports and screenshots are local generated artifacts excluded from source control. Rerunning tests replaces them.

## Verification boundary

Replay outputs are curated validated fixtures. Live-provider account access was not tested; it requires a fresh configured backend key. Provider/session failure presentation uses controlled browser responses where those conditions cannot reliably be triggered through normal UI actions. This verification covers the local single-worker harness and makes no claim about authentication, public hosting, real calls, or durable bookings.

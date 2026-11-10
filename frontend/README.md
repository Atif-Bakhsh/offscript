# OffScript console

A single-page React + TypeScript interface for the existing local FastAPI harness. Startup loads health, scenarios, and prompt rules independently and runs TC-01 and the suite in replay once, including under React development StrictMode.

## Structure

- `src/types.ts` mirrors `backend/models.py`, including nullable values, rubric evidence, tool statuses, and execution provenance.
- `src/api.ts` performs HTTP access, validates complete nested response shapes, and preserves sanitized backend error envelopes. Invalid payloads and connectivity failures become inline diagnostics.
- `src/useHarness.ts` owns independent request states, replay-first initialization, comparison generations, synchronous submission locks, and matching-conversation calendar updates.
- `src/domain.ts` derives metrics, display labels, and default confirmation text from backend evidence.
- `src/components/` renders the header, scenarios, arena, scorecard, and prompt lab. Raw replies are displayed unchanged.
- `src/styles.css` defines the architectural grid, design tokens, responsive layouts, and reduced-motion behavior.
- `src/__tests__/` exercises HTTP, domain, state, and presentation boundaries; `e2e/` exercises actual browser interactions.

No UI framework or routing layer is used. Fonts are loaded from Google Fonts; system fonts provide offline fallbacks. React escapes all caller, model, and JSON content; the app does not render model HTML.

## Commands

```sh
npm ci
npm run dev        # http://127.0.0.1:5173
npm run typecheck
npm run lint
npm test
npm run build
npm run preview    # locally serves dist/ at port 5173
npm run test:e2e   # FastAPI must already be running at port 8000
```

`npm run test:watch` is available for development. Playwright's HTML report is generated in `playwright-report/`; failed runs retain screenshots and traces in `test-results/`. Both directories are excluded from source control.

Use Node 22.13+, 24, or 26. The `minimatch` override selects its patched 11.x release for the development lint dependency tree; lint and tests exercise that resolution. `package-lock.json` records all exact versions. Run `npm audit` when updating dependencies, since advisory status changes over time.

The optional `.env.local` uses the template `.env.example`. `VITE_API_BASE_URL` defaults to `http://127.0.0.1:8000`. It is public build configuration, never a place for provider credentials. Vite is bound to 127.0.0.1 and uses a strict port; the development proxy forwards `/api` to the backend.

## State and evidence

Comparison requests send exactly one selector: `scenario_id` or `caller_text`. No client confirmation flags, calendar state, or rubric scores are submitted. Confirmation sends only a conversation ID and caller text.

Stale comparison or confirmation responses cannot overwrite a newer selection. Duplicate in-flight submissions are blocked. POSTs are never automatically retried. Changing the mode controls future runs without changing an existing conversation's provenance. A nonbooking confirmation or uncertain network outcome offers a fresh comparison.

Suite snapshots are read-only and retain their original evidence. The booking KPI counts actual reschedule-case mutations, while the five-case confirmation check includes the no-booking opt-out. Neither score is hard-coded. The 24-word maximum is the rubric's fixed threshold.

The backend performs heuristic English/semantic checks; the frontend does not pretend to prove naturalness or full language understanding. See the [backend documentation](../backend/README.md) for those limits and the guarded booking model.

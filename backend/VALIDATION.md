# Verification results

Verified after audit remediation on November 9, 2026, using Python 3.12.14 and the runtime versions in `requirements.lock`. Development checks used Ruff 0.17.4 and mypy 1.20.2.

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s backend/tests -v` | 54 tests passed |
| `python3 -m ruff check backend` | Passed |
| `python3 -m ruff format --check backend` | All 18 Python files formatted |
| `python3 -m mypy backend` | No issues in all 12 runtime modules |
| `python3 backend/cli_eval.py` | Exit 0; report saved to `backend/eval_report.json` |
| Replay v1 Turn-1 benchmark | 1/5 scenarios, 20% |
| Replay v2 Turn-1 benchmark | 5/5 scenarios, 100% |
| Replay v2 confirmation checks | 5/5: four bookings and one opt-out with no mutation |
| Six REST endpoints over real HTTP at `127.0.0.1:8000` | All returned 200 and passed response assertions |
| `/docs` | 200 |
| CORS preflight from `http://localhost:5173` | 200; correct allow-origin header |
| Duplicate confirmation over HTTP | Original response returned; one booked slot |
| Gemini/OpenAI adapters | Actual SDK schema serialization/parsing over offline `httpx.MockTransport`, plus mocked refusal, invalid response, timeouts, auth failure, model unavailability, and bounded retries passed |
| Runtime/OpenAPI contracts | All three GET schemas and validation/session/provider error envelopes match real ASGI responses |
| Real provider calls | Not run; no fresh key configured locally |

Commands were run from the project root with `.venv/bin` on `PATH`. Replay fixtures are curated examples, not measured live model performance. See `README.md` for setup, request examples, and the local in-memory storage and heuristic evaluation limits.

## Audit decisions and verification

The supplied [reference workflow](/Users/social/Documents/Studies/Backend/References/hajj-backend-review-workflow/SKILL.md) was applied through its responsibility boundaries, contract consistency, and verification practices. The backend remains English-only FastAPI with an in-memory, single-worker scope; its NestJS-specific patterns were not introduced.

| Confirmed finding | Implementation | Regression evidence |
| --- | --- | --- |
| Questions authorized bookings | Explicit ordered affirmative grammar; interrogative phrasing fails without relying on punctuation | `test_unpunctuated_questions_do_not_book`, `test_interrogatives_and_reordered_words_do_not_authorize` |
| Provider failure lost opt-out | Persist caller-owned terminal state and clear pending authorization before awaiting the provider | `test_optout_survives_failed_provider_request` |
| Changed times retained old authority | Caller changes clear pending state and return a fresh-comparison clarification; model changes also clear pending authority while retaining raw replies and unsafe tool evidence | `test_caller_time_changes_require_fresh_comparison`, `test_model_changed_proposal_cannot_reauthorize_original`, `test_changed_model_proposal_retains_unsafe_attempt_evidence` |
| Session expired during generation or lock contention | Check expiry after generation and inside the calendar commit lock | `test_expiry_during_generation_cannot_commit`, `test_expiry_while_waiting_for_calendar_lock_cannot_commit` |
| Rejected mentions confused with offers | One shared parser associates day/time pairs and local polarity for pending state and rubric checks | `test_pending_state_uses_affirmative_offer_not_rejected_mentions`, `test_negated_alternatives_preserve_local_polarity` |
| Scores contradicted observable evidence | Check actual offered pairs and affirmative claims; retain caller busy context; fail blank speech without rewriting raw replies | `test_denied_or_mismatched_pairs_fail`, `test_negated_retracted_preference_and_booking_claim_pass`, `test_busy_context_survives_into_confirmation`, `test_blank_and_punctuation_only_speech_fail_unchanged` |
| OpenAPI drifted from runtime | Strict GET response DTOs and shared error-envelope schemas | Four tests in `test_contracts.py` |

Existing tests additionally verify fresh calendars across repeated comparisons and suites, blocked mutations leaving calendars unchanged, and twelve concurrent duplicate confirmations returning the original result with one booked slot. No Git repository exists in this workspace, so Git branch/diff checks are unavailable. No public deployment or real provider account access was tested.

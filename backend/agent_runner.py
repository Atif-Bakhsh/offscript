"""Structured model execution, replay, isolated sessions, and suite orchestration."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from pydantic import ValidationError

from .calendar_store import SIMULATION_CONTEXT, CalendarStore, same_slot
from .config import HarnessError, Settings
from .conversation_rules import (
    affirmative_slots,
    confirmation_allowed,
    is_opt_out,
    mentions_exact_slot,
    normalized,
    requested_slot_change,
)
from .evaluator import PILLARS, evaluate
from .models import (
    AgentDecision,
    AgentTurnOutput,
    AggregateScore,
    CompareRequest,
    ConfirmationResponse,
    ExecutionProvenance,
    Mode,
    MutationResult,
    ResolvedMode,
    ScenarioCompareResponse,
    ScenarioScore,
    SlotReference,
    SuiteEvaluationReport,
    ToolCallPayload,
    ToolIntent,
    VersionResult,
)
from .prompts import PROMPT_DIFF_RULES, PROMPT_V1, PROMPT_V2
from .scenarios import SCENARIO_BY_ID, SCENARIOS, decision


def provenance(
    mode: ResolvedMode, settings: Settings, *, guarded: bool = False
) -> ExecutionProvenance:
    live = mode != "verified_replay"
    return ExecutionProvenance(
        mode=mode,
        provider=settings.provider if live else None,
        model=settings.model if live else None,
        source="server_confirmation_guard"
        if guarded
        else ("live_model" if live else "curated_validated_fixture"),
    )


class ProviderGateway:
    """One retry for transient errors; no replay fallback after a live call."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _openai(self, prompt: str, payload: str) -> AgentDecision:
        async with AsyncOpenAI(
            api_key=self.settings.api_key, timeout=self.settings.timeout_seconds, max_retries=0
        ) as client:
            response = await client.chat.completions.parse(
                model=self.settings.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": payload},
                ],
                response_format=AgentDecision,
                temperature=0,
                max_completion_tokens=2000,
            )
            message = response.choices[0].message
            if message.refusal:
                raise HarnessError("PROVIDER_REFUSAL", "The model refused the request.", 502)
            if message.parsed is None:
                raise HarnessError(
                    "INVALID_MODEL_RESPONSE",
                    "The model did not return a valid structured decision.",
                    502,
                )
            return AgentDecision.model_validate(message.parsed)

    async def _gemini(self, prompt: str, payload: str) -> AgentDecision:
        client = genai.Client(
            api_key=self.settings.api_key,
            http_options=types.HttpOptions(
                timeout=int(self.settings.timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        try:
            response = await client.aio.models.generate_content(
                model=self.settings.model,
                contents=payload,
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    response_mime_type="application/json",
                    response_schema=AgentDecision,
                    temperature=0,
                    max_output_tokens=4000,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                raise HarnessError("PROVIDER_REFUSAL", "The model refused the request.", 502)
            for candidate in response.candidates or []:
                if str(candidate.finish_reason).split(".")[-1] in {
                    "SAFETY",
                    "BLOCKLIST",
                    "PROHIBITED_CONTENT",
                    "SPII",
                }:
                    raise HarnessError("PROVIDER_REFUSAL", "The model refused the request.", 502)
            if not response.text:
                raise HarnessError(
                    "INVALID_MODEL_RESPONSE", "The model returned no structured decision.", 502
                )
            return AgentDecision.model_validate_json(response.text)
        finally:
            await client.aio.aclose()
            client.close()

    async def generate(self, prompt: str, payload: dict[str, object]) -> AgentDecision:
        serialized = json.dumps(payload, ensure_ascii=False)
        operation = self._gemini if self.settings.provider == "gemini" else self._openai
        for attempt in range(2):
            try:
                async with asyncio.timeout(self.settings.timeout_seconds):
                    output = await operation(prompt, serialized)
                    return AgentDecision.model_validate(output)
            except HarnessError:
                raise
            except (ValidationError, ValueError, IndexError, AttributeError):
                raise HarnessError(
                    "INVALID_MODEL_RESPONSE",
                    "The model returned an invalid structured decision.",
                    502,
                ) from None
            except Exception as exc:
                if type(exc).__name__ == "ContentFilterFinishReasonError":
                    raise HarnessError(
                        "PROVIDER_REFUSAL", "The model refused the request.", 502
                    ) from None
                if type(exc).__name__ == "LengthFinishReasonError":
                    raise HarnessError(
                        "INVALID_MODEL_RESPONSE",
                        "The model response was truncated before a complete decision.",
                        502,
                    ) from None
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                timed_out = (
                    isinstance(exc, (TimeoutError, httpx.TimeoutException))
                    or "timeout" in type(exc).__name__.lower()
                )
                connection = (
                    isinstance(exc, httpx.TransportError)
                    or "connection" in type(exc).__name__.lower()
                )
                transient = timed_out or connection or status in {408, 429, 500, 502, 503, 504}
                if transient and attempt == 0:
                    await asyncio.sleep(0.1)
                    continue
                if status in {401, 403}:
                    code, message, http_status = (
                        "PROVIDER_AUTHENTICATION_FAILED",
                        "The provider rejected authentication. Check the local API key.",
                        502,
                    )
                elif status == 404:
                    code, message, http_status = (
                        "PROVIDER_MODEL_UNAVAILABLE",
                        "The configured model is unavailable. Check the model name and account access.",
                        502,
                    )
                elif timed_out:
                    code, message, http_status = (
                        "PROVIDER_TIMEOUT",
                        "The provider timed out after bounded retries.",
                        504,
                    )
                else:
                    code, message, http_status = (
                        "PROVIDER_UNAVAILABLE",
                        "The provider request failed. No replay result was substituted.",
                        502,
                    )
                raise HarnessError(code, message, http_status) from None
        raise AssertionError("Unreachable retry state")


@dataclass
class Conversation:
    comparison: ScenarioCompareResponse
    calendar: CalendarStore
    pending: SlotReference | None
    mode: ResolvedMode
    opted_out: bool
    created_at: float = field(default_factory=time.monotonic)
    completed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    responses: dict[str, ConfirmationResponse] = field(default_factory=dict)


class AgentRunner:
    def __init__(self, settings: Settings, gateway: ProviderGateway | None = None) -> None:
        self.settings = settings
        self.gateway = gateway or ProviderGateway(settings)
        self.sessions: dict[str, Conversation] = {}

    async def _decision(
        self,
        *,
        version: str,
        mode: ResolvedMode,
        caller: str,
        calendar: CalendarStore,
        scenario_id: str | None,
        turn: int = 1,
        history: list[dict[str, object]] | None = None,
        pending: SlotReference | None = None,
    ) -> AgentDecision:
        if mode == "verified_replay":
            if turn == 1:
                if scenario_id is None:
                    raise HarnessError(
                        "LIVE_MODE_REQUIRED",
                        "Custom caller text requires live mode and a configured provider key.",
                        409,
                    )
                return getattr(SCENARIO_BY_ID[scenario_id], version).model_copy(deep=True)
            if is_opt_out(caller):
                return decision(
                    "Understood. I'll end this call. Goodbye.", state="ENDED", cues=("opt_out",)
                )
            if confirmation_allowed(caller, pending):
                assert pending is not None
                slot = calendar.find(pending)
                assert slot is not None
                label = slot.label
                return decision(
                    f"I will book {label} for your callback.",
                    tool=ToolIntent(
                        action="schedule_callback", **pending.model_dump(), customer_confirmed=True
                    ),
                    state="AWAITING_CONFIRMATION",
                    cues=("explicit_confirmation",),
                )
            return decision(
                "Please confirm the proposed day and time before I book your callback.",
                state="NEEDS_CLARIFICATION",
            )
        return await self.gateway.generate(
            PROMPT_V1 if version == "v1" else PROMPT_V2,
            {
                "turn": turn,
                "caller_text": caller,
                "calendar": [s.model_dump() for s in calendar.snapshot()],
                "simulation_context": SIMULATION_CONTEXT,
                "pending_slot": pending.model_dump() if pending else None,
                "history": history or [],
            },
        )

    async def _enrich(
        self,
        raw: AgentDecision,
        *,
        caller: str,
        calendar: CalendarStore,
        mode: ResolvedMode,
        turn: int,
        scenario_id: str | None = None,
        pending: SlotReference | None = None,
        confirmed: bool = False,
        guarded: bool = False,
        caller_history: tuple[str, ...] = (),
        expires_at: float | None = None,
    ) -> AgentTurnOutput:
        before = calendar.snapshot()
        mutation = MutationResult(mutated=False, reason="NO_TOOL_CALL")
        tool = None
        if raw.tool_call:
            mutation = await calendar.schedule_callback(
                raw.tool_call,
                turn=turn,
                pending_slot=pending,
                server_confirmed=confirmed,
                expires_at=expires_at,
            )
            tool = ToolCallPayload(
                **raw.tool_call.model_dump(),
                status="EXECUTED" if mutation.mutated else "REJECTED",
                error_reason=None if mutation.mutated else mutation.reason,
            )
        rubric = evaluate(
            raw,
            caller_text=caller,
            calendar_before=before,
            turn=turn,
            mutation=mutation,
            pending_slot=pending,
            server_confirmed=confirmed,
            scenario_id=scenario_id,
            caller_history=caller_history,
        )
        return AgentTurnOutput(
            conversation_state="BOOKED" if mutation.mutated else raw.conversation_state,
            detected_cues=raw.detected_cues,
            agent_reply=raw.agent_reply,
            proposed_slot=raw.proposed_slot,
            tool_call=tool,
            db_mutation_result=mutation,
            rubric_evaluation=rubric,
            execution=provenance(mode, self.settings, guarded=guarded),
        )

    async def _compare(self, request: CompareRequest, *, register: bool) -> Conversation:
        mode = self.settings.resolve_mode(request.execution_mode)
        if request.caller_text is not None and mode == "verified_replay":
            raise HarnessError(
                "LIVE_MODE_REQUIRED",
                "Custom caller text requires live mode and a configured provider key.",
                409,
            )
        if request.caller_text is not None:
            caller = request.caller_text
        else:
            assert request.scenario_id is not None  # Enforced by CompareRequest.
            caller = SCENARIO_BY_ID[request.scenario_id].caller_turn1
        calendars = [CalendarStore(), CalendarStore()]
        # Both versions receive independent copies of identical initial evidence.
        raw_results = await asyncio.gather(
            *[
                self._decision(
                    version=v, mode=mode, caller=caller, calendar=c, scenario_id=request.scenario_id
                )
                for v, c in zip(("v1", "v2"), calendars)
            ]
        )
        results = [
            await self._enrich(
                raw, caller=caller, calendar=c, mode=mode, turn=1, scenario_id=request.scenario_id
            )
            for raw, c in zip(raw_results, calendars)
        ]
        comparison = ScenarioCompareResponse(
            conversation_id=str(uuid4()),
            scenario_id=request.scenario_id,
            caller_text=caller,
            v1_result=VersionResult(turn1=results[0]),
            v2_result=VersionResult(turn1=results[1]),
        )
        v2 = raw_results[1]
        pending = v2.proposed_slot
        opted_out = is_opt_out(caller)
        if (
            opted_out
            or v2.conversation_state != "AWAITING_CONFIRMATION"
            or pending is None
            or calendars[1].rejection_reason(pending)
            or not mentions_exact_slot(v2.agent_reply, pending)
        ):
            pending = None
        session = Conversation(comparison, calendars[1], pending, mode, opted_out)
        if register:
            now = time.monotonic()
            self.sessions = {
                key: s
                for key, s in self.sessions.items()
                if now - s.created_at < self.settings.session_ttl_seconds
            }
            if len(self.sessions) >= self.settings.max_sessions:
                raise HarnessError(
                    "SESSION_CAPACITY_REACHED",
                    "The local session limit was reached. Wait for older sessions to expire.",
                    503,
                )
            self.sessions[comparison.conversation_id] = session
        return session

    async def compare(self, request: CompareRequest) -> ScenarioCompareResponse:
        return (await self._compare(request, register=True)).comparison.model_copy(deep=True)

    async def _confirm(self, session: Conversation, caller_text: str) -> ConfirmationResponse:
        async with session.lock:
            if time.monotonic() - session.created_at >= self.settings.session_ttl_seconds:
                raise HarnessError(
                    "SESSION_EXPIRED", "This conversation has expired. Start a new comparison.", 410
                )
            key = normalized(caller_text)
            if key in session.responses:
                return session.responses[key].model_copy(deep=True)
            if session.completed:
                raise HarnessError(
                    "CONVERSATION_COMPLETED",
                    "This callback is already booked. Start a new comparison.",
                    409,
                )
            guarded = session.opted_out or session.pending is None
            # Caller-owned authorization state is updated before any provider await.
            # A failed model request must never restore an opt-out or a retracted slot.
            if is_opt_out(caller_text):
                session.opted_out, session.pending = True, None
            changed = requested_slot_change(caller_text, session.pending)
            if changed:
                session.pending = None
            confirmed = not guarded and confirmation_allowed(caller_text, session.pending)
            if changed:
                raw = decision(
                    "The requested time changed. Please start a new comparison before confirming a callback.",
                    state="NEEDS_CLARIFICATION",
                )
                guarded = True
            elif guarded:
                raw = (
                    decision("This conversation has ended. Goodbye.", state="ENDED")
                    if session.opted_out
                    else decision(
                        "There is no exact pending slot to confirm. Please start a new comparison.",
                        state="NEEDS_CLARIFICATION",
                    )
                )
            else:
                first = session.comparison.v2_result.turn1
                raw = await self._decision(
                    version="v2",
                    mode=session.mode,
                    caller=caller_text,
                    calendar=session.calendar,
                    scenario_id=session.comparison.scenario_id,
                    turn=2,
                    pending=session.pending,
                    history=[
                        {
                            "caller_text": session.comparison.caller_text,
                            "agent_reply": first.agent_reply,
                            "proposed_slot": first.proposed_slot.model_dump()
                            if first.proposed_slot
                            else None,
                        }
                    ],
                )
                if session.pending and (
                    (raw.proposed_slot and not same_slot(raw.proposed_slot, session.pending))
                    or any(
                        not same_slot(slot, session.pending)
                        for slot in affirmative_slots(raw.agent_reply)
                    )
                ):
                    session.pending = None
                    confirmed = False
                    # Retain the model's reply and attempted tool for evaluation.
                    # Clearing pending authority blocks this and every later booking.
            expires_at = session.created_at + self.settings.session_ttl_seconds
            if time.monotonic() >= expires_at:
                raise HarnessError(
                    "SESSION_EXPIRED", "This conversation has expired. Start a new comparison.", 410
                )
            result = await self._enrich(
                raw,
                caller=caller_text,
                calendar=session.calendar,
                mode=session.mode,
                turn=2,
                pending=session.pending,
                confirmed=confirmed,
                guarded=guarded,
                caller_history=(session.comparison.caller_text,),
                expires_at=expires_at,
            )
            session.completed = result.db_mutation_result.mutated
            session.comparison.v2_result.turn2 = result
            response = ConfirmationResponse(
                conversation_id=session.comparison.conversation_id,
                v2_result=result,
                calendar=session.calendar.snapshot(),
            )
            session.responses[key] = response.model_copy(deep=True)
            return response

    async def confirm(self, conversation_id: str, caller_text: str) -> ConfirmationResponse:
        session = self.sessions.get(conversation_id)
        if session is None:
            raise HarnessError(
                "CONVERSATION_NOT_FOUND",
                "This conversation does not exist. Start a new comparison.",
                404,
            )
        return await self._confirm(session, caller_text)

    async def evaluate_suite(self, execution_mode: Mode | None = None) -> SuiteEvaluationReport:
        mode = self.settings.resolve_mode(execution_mode)
        rows = []
        for scenario in SCENARIOS:
            session = await self._compare(
                CompareRequest(scenario_id=scenario.scenario_id, execution_mode=execution_mode),
                register=False,
            )
            if scenario.caller_turn2 is None:
                first = session.comparison.v2_result.turn1
                confirmation_passed = (
                    session.opted_out
                    and session.pending is None
                    and first.conversation_state == "ENDED"
                    and first.tool_call is None
                    and first.proposed_slot is None
                    and not first.db_mutation_result.mutated
                )
            elif session.pending is None:
                confirmation_passed = False
            else:
                # Live confirmation agrees to the actual exact pending proposal.
                slot = session.calendar.find(session.pending)
                assert slot is not None
                label = slot.label
                caller = (
                    scenario.caller_turn2
                    if mode == "verified_replay"
                    else f"Yes, please book {label}."
                )
                response = await self._confirm(session, caller)
                confirmation_passed = (
                    response.v2_result.db_mutation_result.mutated
                    and response.v2_result.rubric_evaluation.all_passed
                )
            rows.append(
                ScenarioScore(
                    scenario_id=scenario.scenario_id,
                    title=scenario.title,
                    comparison=session.comparison,
                    confirmation_passed=confirmation_passed,
                )
            )

        def aggregate(version: str) -> AggregateScore:
            scores = [
                getattr(row.comparison, f"{version}_result").turn1.rubric_evaluation for row in rows
            ]
            passed = sum(s.all_passed for s in scores)
            return AggregateScore(
                passed=passed,
                total=len(scores),
                pass_rate_percent=100.0 * passed / len(scores),
                pillar_pass_rates={
                    p: 100.0 * sum(getattr(s, p) for s in scores) / len(scores) for p in PILLARS
                },
            )

        confirmed_count = sum(row.confirmation_passed for row in rows)
        return SuiteEvaluationReport(
            execution=provenance(mode, self.settings),
            benchmark_basis="Turn-1 scenarios passing all four rubric pillars. Replay uses curated validated fixtures; live scores are observed model results.",
            v1=aggregate("v1"),
            v2=aggregate("v2"),
            v2_confirmation=AggregateScore(
                passed=confirmed_count,
                total=len(rows),
                pass_rate_percent=100.0 * confirmed_count / len(rows),
                pillar_pass_rates={},
            ),
            per_scenario=rows,
            prompt_diff_summary=PROMPT_DIFF_RULES,
        )

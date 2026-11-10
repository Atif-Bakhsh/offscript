"""Strict API and model-output contracts; model output cannot set tool results."""

import re
import unicodedata
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Day = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
Mode = Literal["auto", "live", "replay"]
Version = Literal["v1", "v2"]
ResolvedMode = Literal["verified_replay", "live_gemini", "live_openai"]
ConversationState = Literal[
    "PITCHING", "AWAITING_CONFIRMATION", "BOOKED", "ENDED", "NEEDS_CLARIFICATION"
]


def english_text(value: str) -> str:
    if not value.strip():
        raise ValueError("Please provide English caller text.")
    if any(c.isalpha() and "LATIN" not in unicodedata.name(c, "") for c in value):
        raise ValueError("Only English text is supported.")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Please provide English caller text.")
    # A script filter, not a full language classifier. See README.
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SlotReference(StrictModel):
    day: Day
    time_24h: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class CalendarSlot(SlotReference):
    slot_id: str
    label: str
    status: Literal["AVAILABLE", "BOOKED_FULL", "BOOKED_BY_AGENT"]


class ToolIntent(SlotReference):
    action: Literal["schedule_callback"]
    customer_confirmed: bool


class ToolCallPayload(ToolIntent):
    status: Literal["REJECTED", "EXECUTED"]
    error_reason: str | None


class AgentDecision(StrictModel):
    conversation_state: ConversationState
    detected_cues: list[str] = Field(max_length=20)
    agent_reply: str = Field(min_length=1, max_length=8000)
    proposed_slot: SlotReference | None
    tool_call: ToolIntent | None


class MutationResult(StrictModel):
    mutated: bool
    reason: str
    slot: CalendarSlot | None = None


class RubricEvaluation(StrictModel):
    booking_gate_passed: bool
    cue_and_correction_passed: bool
    hallucination_guard_passed: bool
    voice_brevity_passed: bool
    all_passed: bool
    word_count: int
    evidence: dict[str, list[str]]
    methodology: str = "Deterministic checks; semantic and naturalness checks are heuristic."


class ExecutionProvenance(StrictModel):
    mode: ResolvedMode
    provider: str | None
    model: str | None
    source: Literal["curated_validated_fixture", "live_model", "server_confirmation_guard"]


class AgentTurnOutput(StrictModel):
    conversation_state: str
    detected_cues: list[str]
    agent_reply: str
    proposed_slot: SlotReference | None
    tool_call: ToolCallPayload | None
    db_mutation_result: MutationResult
    rubric_evaluation: RubricEvaluation
    execution: ExecutionProvenance


class VersionResult(StrictModel):
    turn1: AgentTurnOutput
    turn2: AgentTurnOutput | None = None


class ScenarioCompareResponse(StrictModel):
    conversation_id: str
    scenario_id: str | None
    caller_text: str
    v1_result: VersionResult
    v2_result: VersionResult


class CompareRequest(StrictModel):
    scenario_id: str | None = Field(default=None, pattern=r"^TC-0[1-5]$")
    caller_text: str | None = Field(default=None, min_length=1, max_length=4000)
    execution_mode: Mode | None = None

    @field_validator("caller_text")
    @classmethod
    def validate_english(cls, value: str | None) -> str | None:
        return english_text(value) if value is not None else value

    @model_validator(mode="after")
    def exactly_one_input(self) -> Self:
        if (self.scenario_id is None) == (self.caller_text is None):
            raise ValueError("Provide exactly one of scenario_id or caller_text.")
        return self


class ConfirmationRequest(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=100)
    caller_text: str = Field(min_length=1, max_length=4000)

    @field_validator("caller_text")
    @classmethod
    def validate_english(cls, value: str) -> str:
        return english_text(value)


class ConfirmationResponse(StrictModel):
    conversation_id: str
    v2_result: AgentTurnOutput
    calendar: list[CalendarSlot]


class SuiteRequest(StrictModel):
    execution_mode: Mode | None = None


class AggregateScore(StrictModel):
    passed: int
    total: int
    pass_rate_percent: float
    pillar_pass_rates: dict[str, float]


class ScenarioScore(StrictModel):
    scenario_id: str
    title: str
    comparison: ScenarioCompareResponse
    confirmation_passed: bool


class SuiteEvaluationReport(StrictModel):
    execution: ExecutionProvenance
    benchmark_basis: str
    v1: AggregateScore
    v2: AggregateScore
    v2_confirmation: AggregateScore
    per_scenario: list[ScenarioScore]
    prompt_diff_summary: list[dict[str, str]]


class ErrorDetail(StrictModel):
    field: str
    message: str


class ErrorPayload(StrictModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(StrictModel):
    error: ErrorPayload


class HealthResponse(StrictModel):
    status: Literal["ok"]
    mode: ResolvedMode
    provider: str | None
    model: str | None
    storage: Literal["conversation-local in-memory"]
    durable: Literal[False]
    workers: Literal[1]
    session_ttl_seconds: float


class VerifiedOutputs(StrictModel):
    v1: AgentDecision
    v2: AgentDecision


class PublicScenario(StrictModel):
    scenario_id: str
    title: str
    caller_turn1: str
    caller_turn2: str | None
    expected_behavior: str
    expected_slot: SlotReference | None
    verified_outputs: VerifiedOutputs
    fixture_source: str


class SimulationContext(StrictModel):
    reference_datetime: str
    reference_day: Day
    timezone: str
    tomorrow: Day
    operating_hours: str
    calendar_scope: str


class ScenariosResponse(StrictModel):
    scenarios: list[PublicScenario]
    initial_calendar: list[CalendarSlot]
    simulation_context: SimulationContext


class PromptDiffRule(StrictModel):
    rule_id: str
    title: str
    description: str


class PromptDiffResponse(StrictModel):
    prompt_v1: str
    prompt_v2: str
    rules: list[PromptDiffRule]

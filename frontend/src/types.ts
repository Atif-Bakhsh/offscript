export type Day = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'
export type Mode = 'auto' | 'live' | 'replay'
export type Version = 'v1' | 'v2'
export type ResolvedMode = 'verified_replay' | 'live_gemini' | 'live_openai'
export type ConversationState = 'PITCHING' | 'AWAITING_CONFIRMATION' | 'BOOKED' | 'ENDED' | 'NEEDS_CLARIFICATION'
export interface SlotReference { day: Day; time_24h: string }
export interface CalendarSlot extends SlotReference { slot_id: string; label: string; status: 'AVAILABLE' | 'BOOKED_FULL' | 'BOOKED_BY_AGENT' }
export interface ToolIntent extends SlotReference { action: 'schedule_callback'; customer_confirmed: boolean }
export interface ToolCallPayload extends ToolIntent { status: 'REJECTED' | 'EXECUTED'; error_reason: string | null }
export interface AgentDecision { conversation_state: ConversationState; detected_cues: string[]; agent_reply: string; proposed_slot: SlotReference | null; tool_call: ToolIntent | null }
export interface MutationResult { mutated: boolean; reason: string; slot: CalendarSlot | null }
export interface RubricEvaluation {
  booking_gate_passed: boolean
  cue_and_correction_passed: boolean
  hallucination_guard_passed: boolean
  voice_brevity_passed: boolean
  all_passed: boolean
  word_count: number
  evidence: Record<string, string[]>
  methodology: string
}
export interface ExecutionProvenance { mode: ResolvedMode; provider: string | null; model: string | null; source: 'curated_validated_fixture' | 'live_model' | 'server_confirmation_guard' }
export interface AgentTurnOutput { conversation_state: string; detected_cues: string[]; agent_reply: string; proposed_slot: SlotReference | null; tool_call: ToolCallPayload | null; db_mutation_result: MutationResult; rubric_evaluation: RubricEvaluation; execution: ExecutionProvenance }
export interface VersionResult { turn1: AgentTurnOutput; turn2: AgentTurnOutput | null }
export interface ScenarioCompareResponse { conversation_id: string; scenario_id: string | null; caller_text: string; v1_result: VersionResult; v2_result: VersionResult }
export type CompareRequest = ({ scenario_id: string; caller_text?: never } | { caller_text: string; scenario_id?: never }) & { execution_mode?: Mode | null }
export interface ConfirmationRequest { conversation_id: string; caller_text: string }
export interface ConfirmationResponse { conversation_id: string; v2_result: AgentTurnOutput; calendar: CalendarSlot[] }
export interface SuiteRequest { execution_mode?: Mode | null }
export interface AggregateScore { passed: number; total: number; pass_rate_percent: number; pillar_pass_rates: Record<string, number> }
export interface ScenarioScore { scenario_id: string; title: string; comparison: ScenarioCompareResponse; confirmation_passed: boolean }
export interface SuiteEvaluationReport { execution: ExecutionProvenance; benchmark_basis: string; v1: AggregateScore; v2: AggregateScore; v2_confirmation: AggregateScore; per_scenario: ScenarioScore[]; prompt_diff_summary: Record<string, string>[] }
export interface ErrorDetail { field: string; message: string }
export interface ErrorPayload { code: string; message: string; details?: ErrorDetail[] | null }
export interface ErrorResponse { error: ErrorPayload }
export interface HealthResponse { status: 'ok'; mode: ResolvedMode; provider: string | null; model: string | null; storage: 'conversation-local in-memory'; durable: false; workers: 1; session_ttl_seconds: number }
export interface VerifiedOutputs { v1: AgentDecision; v2: AgentDecision }
export interface PublicScenario { scenario_id: string; title: string; caller_turn1: string; caller_turn2: string | null; expected_behavior: string; expected_slot: SlotReference | null; verified_outputs: VerifiedOutputs; fixture_source: string }
export interface SimulationContext { reference_datetime: string; reference_day: Day; timezone: string; tomorrow: Day; operating_hours: string; calendar_scope: string }
export interface ScenariosResponse { scenarios: PublicScenario[]; initial_calendar: CalendarSlot[]; simulation_context: SimulationContext }
export interface PromptDiffRule { rule_id: string; title: string; description: string }
export interface PromptDiffResponse { prompt_v1: string; prompt_v2: string; rules: PromptDiffRule[] }

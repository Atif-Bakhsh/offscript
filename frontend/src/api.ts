import type { CompareRequest, ConfirmationRequest, ConfirmationResponse, ErrorDetail, HealthResponse, PromptDiffResponse, ScenarioCompareResponse, ScenariosResponse, SuiteEvaluationReport, SuiteRequest } from './types'

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: ErrorDetail[]

  constructor(code: string, message: string, status = 0, details: ErrorDetail[] = []) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

type Guard = (value: unknown) => boolean
const string: Guard = (value) => typeof value === 'string'
const number: Guard = (value) => typeof value === 'number' && Number.isFinite(value)
const boolean: Guard = (value) => typeof value === 'boolean'
const oneOf = (...values: readonly unknown[]): Guard => (value) => values.includes(value)
const nullable = (guard: Guard): Guard => (value) => value === null || guard(value)
const optional = (guard: Guard): Guard => (value) => value === undefined || guard(value)
const array = (guard: Guard): Guard => (value) => Array.isArray(value) && value.every(guard)
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const dictionary = (guard: Guard): Guard => (value) => record(value) && Object.values(value).every(guard)
const object = (fields: Record<string, Guard>): Guard => (value) => record(value)
  && Object.entries(fields).every(([key, guard]) => guard(value[key]))
  && Object.keys(value).every((key) => key in fields)

const day = oneOf('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
const time: Guard = (value) => typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)
const datetime: Guard = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value))
const timezone: Guard = (value) => {
  if (typeof value !== 'string') return false
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value }).format(0)
    return true
  } catch {
    return false
  }
}
const slotFields = { day, time_24h: time }
const slot = object(slotFields)
const calendarSlot = object({ ...slotFields, slot_id: string, label: string, status: oneOf('AVAILABLE', 'BOOKED_FULL', 'BOOKED_BY_AGENT') })
const intentFields = { ...slotFields, action: oneOf('schedule_callback'), customer_confirmed: boolean }
const intent = object(intentFields)
const decision = object({ conversation_state: oneOf('PITCHING', 'AWAITING_CONFIRMATION', 'BOOKED', 'ENDED', 'NEEDS_CLARIFICATION'), detected_cues: array(string), agent_reply: string, proposed_slot: nullable(slot), tool_call: nullable(intent) })
const execution = object({ mode: oneOf('verified_replay', 'live_gemini', 'live_openai'), provider: nullable(string), model: nullable(string), source: oneOf('curated_validated_fixture', 'live_model', 'server_confirmation_guard') })
const tool = object({ ...intentFields, status: oneOf('REJECTED', 'EXECUTED'), error_reason: nullable(string) })
const mutation = object({ mutated: boolean, reason: string, slot: nullable(calendarSlot) })
const rubric = object({ booking_gate_passed: boolean, cue_and_correction_passed: boolean, hallucination_guard_passed: boolean, voice_brevity_passed: boolean, all_passed: boolean, word_count: number, evidence: dictionary(array(string)), methodology: string })
const turn = object({ conversation_state: string, detected_cues: array(string), agent_reply: string, proposed_slot: nullable(slot), tool_call: nullable(tool), db_mutation_result: mutation, rubric_evaluation: rubric, execution })
const version = object({ turn1: turn, turn2: nullable(turn) })
const comparison = object({ conversation_id: string, scenario_id: nullable(string), caller_text: string, v1_result: version, v2_result: version })
const aggregate = object({ passed: number, total: number, pass_rate_percent: number, pillar_pass_rates: dictionary(number) })
const scenario = object({ scenario_id: string, title: string, caller_turn1: string, caller_turn2: nullable(string), expected_behavior: string, expected_slot: nullable(slot), verified_outputs: object({ v1: decision, v2: decision }), fixture_source: string })
const context = object({ reference_datetime: datetime, reference_day: day, timezone, tomorrow: day, operating_hours: string, calendar_scope: string })
const health = object({ status: oneOf('ok'), mode: oneOf('verified_replay', 'live_gemini', 'live_openai'), provider: nullable(string), model: nullable(string), storage: oneOf('conversation-local in-memory'), durable: oneOf(false), workers: oneOf(1), session_ttl_seconds: number })
const scenarios = object({ scenarios: array(scenario), initial_calendar: array(calendarSlot), simulation_context: context })
const prompts = object({ prompt_v1: string, prompt_v2: string, rules: array(object({ rule_id: string, title: string, description: string })) })
const confirmation = object({ conversation_id: string, v2_result: turn, calendar: array(calendarSlot) })
const suite = object({ execution, benchmark_basis: string, v1: aggregate, v2: aggregate, v2_confirmation: aggregate, per_scenario: array(object({ scenario_id: string, title: string, comparison, confirmation_passed: boolean })), prompt_diff_summary: array(dictionary(string)) })
const detail = object({ field: string, message: string })
const error = object({ error: object({ code: string, message: string, details: optional(nullable(array(detail))) }) })

const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request<T>(path: string, guard: Guard, body?: object): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, body === undefined ? { method: 'GET' } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError('NETWORK_ERROR', 'Cannot reach the backend. Check that FastAPI is running on port 8000, then try again.')
  }

  let value: unknown
  try { value = await response.json() } catch {
    throw new ApiError('INVALID_RESPONSE', 'The backend returned an unreadable response. Check the backend logs.', response.status)
  }
  if (!response.ok) {
    if (error(value)) {
      const payload = (value as { error: { code: string; message: string; details?: ErrorDetail[] | null } }).error
      throw new ApiError(payload.code, payload.message, response.status, payload.details ?? [])
    }
    throw new ApiError('INVALID_RESPONSE', 'The backend returned an unexpected error response. Check the backend logs.', response.status)
  }
  if (!guard(value)) throw new ApiError('INVALID_RESPONSE', 'The backend response does not match the OffScript API contract.', response.status)
  return value as T
}

export const api = {
  health: () => request<HealthResponse>('/api/health', health),
  scenarios: () => request<ScenariosResponse>('/api/scenarios', scenarios),
  prompts: () => request<PromptDiffResponse>('/api/prompt-diff', prompts),
  compare: (body: CompareRequest) => {
    if ((body.scenario_id !== undefined) === (body.caller_text !== undefined)) {
      return Promise.reject(new ApiError('INVALID_REQUEST', 'Provide exactly one of scenario_id or caller_text.'))
    }
    return request<ScenarioCompareResponse>('/api/compare-turn1', comparison, body)
  },
  confirm: (body: ConfirmationRequest) => request<ConfirmationResponse>('/api/simulate-turn2', confirmation, body),
  suite: (body: SuiteRequest = {}) => request<SuiteEvaluationReport>('/api/evaluate-suite', suite, body),
}

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('UNEXPECTED_ERROR', 'The request could not be completed. Start a fresh run and try again.')
}

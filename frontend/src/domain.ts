import type { AgentTurnOutput, ExecutionProvenance, PublicScenario, ResolvedMode, SlotReference, SuiteEvaluationReport } from './types'

export const PILLARS = [
  { key: 'booking_gate_passed', label: 'Booking Gate', short: 'Gate' },
  { key: 'cue_and_correction_passed', label: 'Cue & Correction', short: 'Cues' },
  { key: 'hallucination_guard_passed', label: 'Hallucination Guard', short: 'Facts' },
  { key: 'voice_brevity_passed', label: 'Voice Brevity (<25w)', short: 'Voice' },
] as const

export function modeLabel(mode: ResolvedMode): string {
  return ({ verified_replay: 'VERIFIED REPLAY', live_gemini: 'LIVE GEMINI', live_openai: 'LIVE OPENAI' })[mode]
}

export function provenanceLabel(execution: ExecutionProvenance): string {
  if (execution.source === 'server_confirmation_guard') return 'Server confirmation guard'
  return execution.source === 'curated_validated_fixture' ? 'Curated validated fixtures' : 'Measured model outcome'
}

export function slotLabel(slot: SlotReference): string {
  const [hour, minute] = slot.time_24h.split(':').map(Number)
  return `${slot.day} at ${(hour % 12) || 12}:${String(minute).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`
}

export function defaultConfirmation(turn: AgentTurnOutput, scenario?: PublicScenario): string {
  if (turn.execution.mode === 'verified_replay' && scenario?.caller_turn2) return scenario.caller_turn2
  return turn.proposed_slot ? `Yes, please book ${slotLabel(turn.proposed_slot)}.` : ''
}

export function suiteMetrics(suite: SuiteEvaluationReport) {
  const rescheduleCases = suite.per_scenario.filter(({ scenario_id }) => ['TC-01', 'TC-02', 'TC-03', 'TC-04'].includes(scenario_id))
  return {
    v1Rate: suite.v1.pass_rate_percent,
    v2Rate: suite.v2.pass_rate_percent,
    confirmedBookings: rescheduleCases.filter(({ comparison }) => comparison.v2_result.turn2?.db_mutation_result.mutated === true).length,
    rescheduleCases: rescheduleCases.length,
    confirmationPassed: suite.v2_confirmation.passed,
    confirmationTotal: suite.v2_confirmation.total,
    unconfirmedMutations: suite.per_scenario.reduce((count, { comparison }) => count + Number(comparison.v1_result.turn1.db_mutation_result.mutated) + Number(comparison.v2_result.turn1.db_mutation_result.mutated), 0),
    maxWords: 24,
  }
}

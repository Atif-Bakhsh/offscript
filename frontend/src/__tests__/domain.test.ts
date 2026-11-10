import { describe, expect, it } from 'vitest'
import { defaultConfirmation, modeLabel, provenanceLabel, slotLabel, suiteMetrics } from '../domain'
import { comparison, scenarios, suite } from './fixtures'

describe('evidence-derived presentation', () => {
  it('calculates the replay benchmark, four real bookings, and five confirmation checks separately', () => {
    expect(suiteMetrics(suite)).toEqual({
      v1Rate: 20, v2Rate: 100, confirmedBookings: 4, rescheduleCases: 4,
      confirmationPassed: 5, confirmationTotal: 5, unconfirmedMutations: 0, maxWords: 24,
    })
  })

  it('reflects observed scores and mutations rather than hard-coded success claims', () => {
    const changed = structuredClone(suite)
    changed.v2.pass_rate_percent = 60
    changed.per_scenario[0].comparison.v2_result.turn2!.db_mutation_result.mutated = false
    changed.per_scenario[1].comparison.v1_result.turn1.db_mutation_result.mutated = true
    expect(suiteMetrics(changed)).toMatchObject({ v2Rate: 60, confirmedBookings: 3, unconfirmedMutations: 1 })
  })

  it('uses the fixture confirmation for replay and the actual proposed slot for live', () => {
    const turn = comparison().v2_result.turn1
    expect(defaultConfirmation(turn, scenarios.scenarios[0])).toBe(scenarios.scenarios[0].caller_turn2)
    turn.execution = { mode: 'live_gemini', provider: 'gemini', model: 'test-model', source: 'live_model' }
    turn.proposed_slot = { day: 'Wednesday', time_24h: '16:30' }
    expect(defaultConfirmation(turn, scenarios.scenarios[0])).toBe('Yes, please book Wednesday at 4:30 PM.')
  })

  it('labels each provenance without treating replay as measured model performance', () => {
    expect(modeLabel('verified_replay')).toBe('VERIFIED REPLAY')
    expect(modeLabel('live_openai')).toBe('LIVE OPENAI')
    expect(provenanceLabel(suite.execution)).toBe('Curated validated fixtures')
    expect(provenanceLabel({ mode: 'live_openai', provider: 'openai', model: 'test', source: 'live_model' })).toBe('Measured model outcome')
    expect(provenanceLabel({ ...suite.execution, source: 'server_confirmation_guard' })).toBe('Server confirmation guard')
    expect(slotLabel({ day: 'Monday', time_24h: '10:00' })).toBe('Monday at 10:00 AM')
  })
})

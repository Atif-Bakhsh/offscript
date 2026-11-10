import { StrictMode, type ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../api'
import { useHarness } from '../useHarness'
import type { ConfirmationResponse, HealthResponse, ScenarioCompareResponse } from '../types'
import { comparison, health, scenarios, suite } from './fixtures'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  vi.spyOn(api, 'health').mockResolvedValue(health as HealthResponse)
  vi.spyOn(api, 'scenarios').mockResolvedValue(scenarios)
  vi.spyOn(api, 'prompts').mockResolvedValue({ prompt_v1: 'Baseline', prompt_v2: 'Refined', rules: [] })
  vi.spyOn(api, 'compare').mockResolvedValue(comparison())
  vi.spyOn(api, 'suite').mockResolvedValue(suite)
  vi.spyOn(api, 'confirm').mockResolvedValue({
    conversation_id: comparison().conversation_id,
    v2_result: suite.per_scenario[0].comparison.v2_result.turn2!,
    calendar: scenarios.initial_calendar,
  })
})
afterEach(() => vi.restoreAllMocks())

async function mounted() {
  const view = renderHook(() => useHarness())
  await waitFor(() => expect(view.result.current.comparison?.scenario_id).toBe('TC-01'))
  return view
}

describe('console orchestration', () => {
  it('starts TC-01 and the suite in replay once under React development effect replay', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>
    const { result } = renderHook(() => useHarness(), { wrapper })
    await waitFor(() => expect(result.current.comparison?.scenario_id).toBe('TC-01'))
    expect(api.compare).toHaveBeenCalledTimes(1)
    expect(api.compare).toHaveBeenCalledWith({ scenario_id: 'TC-01', execution_mode: 'replay' })
    expect(api.suite).toHaveBeenCalledTimes(1)
    expect(api.suite).toHaveBeenCalledWith({ execution_mode: 'replay' })
  })

  it('ignores an older comparison after a later scenario resolves', async () => {
    const { result } = await mounted()
    const older = deferred<ScenarioCompareResponse>()
    vi.mocked(api.compare).mockReturnValueOnce(older.promise).mockResolvedValueOnce(comparison(2))
    let oldRun!: Promise<void>
    act(() => { oldRun = result.current.compareScenario('TC-02') })
    await act(async () => { await result.current.compareScenario('TC-03') })
    await act(async () => { older.resolve(comparison(1)); await oldRun })
    expect(result.current.comparison?.scenario_id).toBe('TC-03')
  })

  it('locks duplicate confirmations and retains the original first turn', async () => {
    const { result } = await mounted()
    const pending = deferred<ConfirmationResponse>()
    vi.mocked(api.confirm).mockReturnValueOnce(pending.promise)
    const firstTurn = result.current.comparison!.v2_result.turn1.agent_reply
    let first!: Promise<void>
    let second!: Promise<void>
    act(() => {
      first = result.current.confirm('Yes, please book it.')
      second = result.current.confirm('Yes, please book it.')
    })
    expect(api.confirm).toHaveBeenCalledTimes(1)
    await act(async () => {
      pending.resolve({ conversation_id: comparison().conversation_id, v2_result: suite.per_scenario[0].comparison.v2_result.turn2!, calendar: scenarios.initial_calendar })
      await Promise.all([first, second])
    })
    expect(result.current.comparison!.v2_result.turn1.agent_reply).toBe(firstTurn)
    expect(result.current.comparison!.v2_result.turn2?.db_mutation_result.mutated).toBe(true)
  })

  it('never merges a late confirmation into a newly selected comparison', async () => {
    const { result } = await mounted()
    const pending = deferred<ConfirmationResponse>()
    vi.mocked(api.confirm).mockReturnValueOnce(pending.promise)
    let confirm!: Promise<void>
    act(() => { confirm = result.current.confirm('Yes, please book it.') })
    vi.mocked(api.compare).mockResolvedValueOnce(comparison(1))
    await act(async () => { await result.current.compareScenario('TC-02') })
    await act(async () => {
      pending.resolve({ conversation_id: comparison().conversation_id, v2_result: suite.per_scenario[0].comparison.v2_result.turn2!, calendar: [] })
      await confirm
    })
    expect(result.current.comparison?.scenario_id).toBe('TC-02')
    expect(result.current.comparison?.v2_result.turn2).toBeNull()
    expect(result.current.calendar).toEqual(scenarios.initial_calendar)
  })

  it('inspects the exact suite snapshot without creating or confirming an interactive session', async () => {
    const { result } = await mounted()
    const calls = vi.mocked(api.compare).mock.calls.length
    act(() => { result.current.inspectScenario(suite.per_scenario[2]) })
    expect(result.current.readOnly).toBe(true)
    expect(result.current.comparison).toEqual(suite.per_scenario[2].comparison)
    await act(async () => { await result.current.confirm('Yes') })
    expect(api.confirm).not.toHaveBeenCalled()
    expect(api.compare).toHaveBeenCalledTimes(calls)
    vi.mocked(api.compare).mockResolvedValueOnce(comparison(2))
    await act(async () => { await result.current.startFresh() })
    expect(result.current.readOnly).toBe(false)
    expect(result.current.comparison?.v2_result.turn2).toBeNull()
  })

  it('retains backend errors and preserves a fresh comparison recovery path', async () => {
    const { result } = await mounted()
    vi.mocked(api.confirm).mockRejectedValueOnce(new ApiError('SESSION_EXPIRED', 'Start a new comparison.', 410))
    await act(async () => { await result.current.confirm('Yes') })
    expect(result.current.confirmationError).toMatchObject({ code: 'SESSION_EXPIRED' })
    expect(result.current.comparison?.v2_result.turn1.agent_reply).toBe(comparison().v2_result.turn1.agent_reply)
    await act(async () => { await result.current.confirm('Yes') })
    expect(api.confirm).toHaveBeenCalledTimes(1)
    await act(async () => { await result.current.startFresh() })
    expect(result.current.confirmationError).toBeNull()
  })

  it('loads successful metadata and experiments even if health alone is unavailable', async () => {
    vi.mocked(api.health).mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 'Health is unavailable.'))
    const { result } = await mounted()
    await waitFor(() => expect(result.current.metadataErrors.health?.code).toBe('NETWORK_ERROR'))
    expect(result.current.scenarios).toEqual(scenarios)
    expect(result.current.suite).toEqual(suite)
    expect(result.current.comparison).not.toBeNull()
  })

  it('keeps existing conversation provenance and confirmation payload pinned after selecting another mode', async () => {
    const { result } = await mounted()
    act(() => result.current.setMode('live'))
    expect(result.current.mode).toBe('live')
    expect(result.current.comparison?.v2_result.turn1.execution.mode).toBe('verified_replay')
    expect(api.compare).toHaveBeenCalledTimes(1)
    await act(async () => { await result.current.confirm('Yes, please book it.') })
    expect(api.confirm).toHaveBeenCalledWith({ conversation_id: comparison().conversation_id, caller_text: 'Yes, please book it.' })
  })
})

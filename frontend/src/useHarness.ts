import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, toApiError } from './api'
import type { CalendarSlot, CompareRequest, HealthResponse, Mode, PromptDiffResponse, ScenarioCompareResponse, ScenarioScore, ScenariosResponse, SuiteEvaluationReport } from './types'

type MetadataErrors = { health: ApiError | null; scenarios: ApiError | null; prompts: ApiError | null }

export function useHarness() {
  const [mode, setMode] = useState<Mode>('replay')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [scenarios, setScenarios] = useState<ScenariosResponse | null>(null)
  const [prompts, setPrompts] = useState<PromptDiffResponse | null>(null)
  const [metadataErrors, setMetadataErrors] = useState<MetadataErrors>({ health: null, scenarios: null, prompts: null })
  const [comparison, setComparison] = useState<ScenarioCompareResponse | null>(null)
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>('TC-01')
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [comparisonError, setComparisonError] = useState<ApiError | null>(null)
  const [readOnly, setReadOnly] = useState(false)
  const [confirmedCalendar, setConfirmedCalendar] = useState<CalendarSlot[] | null>(null)
  const [confirmationLoading, setConfirmationLoading] = useState(false)
  const [confirmationError, setConfirmationError] = useState<ApiError | null>(null)
  const [confirmationAttempted, setConfirmationAttempted] = useState(false)
  const [suite, setSuite] = useState<SuiteEvaluationReport | null>(null)
  const [suiteLoading, setSuiteLoading] = useState(false)
  const [suiteError, setSuiteError] = useState<ApiError | null>(null)

  const mounted = useRef(false)
  const initialized = useRef(false)
  const comparisonGeneration = useRef(0)
  const metadataGeneration = useRef(0)
  const pendingComparison = useRef<string | null>(null)
  const confirming = useRef(false)
  const confirmationUsed = useRef(false)
  const suitePending = useRef(false)
  const comparisonRef = useRef<ScenarioCompareResponse | null>(null)
  const readOnlyRef = useRef(false)
  const activeInput = useRef<CompareRequest>({ scenario_id: 'TC-01' })

  const reloadMetadata = useCallback(async () => {
    const generation = ++metadataGeneration.current
    const current = () => mounted.current && metadataGeneration.current === generation
    setMetadataErrors({ health: null, scenarios: null, prompts: null })
    await Promise.allSettled([
      api.health().then((value) => { if (current()) setHealth(value) }).catch((error: unknown) => {
        if (current()) setMetadataErrors((previous) => ({ ...previous, health: toApiError(error) }))
      }),
      api.scenarios().then((value) => { if (current()) setScenarios(value) }).catch((error: unknown) => {
        if (current()) setMetadataErrors((previous) => ({ ...previous, scenarios: toApiError(error) }))
      }),
      api.prompts().then((value) => { if (current()) setPrompts(value) }).catch((error: unknown) => {
        if (current()) setMetadataErrors((previous) => ({ ...previous, prompts: toApiError(error) }))
      }),
    ])
  }, [])

  const compare = useCallback(async (input: CompareRequest) => {
    const request = { ...input, execution_mode: mode }
    const key = JSON.stringify(request)
    if (pendingComparison.current === key) return
    const generation = ++comparisonGeneration.current
    pendingComparison.current = key
    activeInput.current = input
    comparisonRef.current = null
    readOnlyRef.current = false
    confirming.current = false
    confirmationUsed.current = false
    setSelectedScenarioId(input.scenario_id ?? null)
    setReadOnly(false)
    setComparison(null)
    setComparisonLoading(true)
    setComparisonError(null)
    setConfirmationLoading(false)
    setConfirmationError(null)
    setConfirmationAttempted(false)
    setConfirmedCalendar(null)
    try {
      const response = await api.compare(request)
      if (mounted.current && comparisonGeneration.current === generation) {
        comparisonRef.current = response
        setComparison(response)
      }
    } catch (error) {
      if (mounted.current && comparisonGeneration.current === generation) setComparisonError(toApiError(error))
    } finally {
      if (comparisonGeneration.current === generation) {
        pendingComparison.current = null
        if (mounted.current) setComparisonLoading(false)
      }
    }
  }, [mode])

  const compareScenario = useCallback((id: string) => compare({ scenario_id: id }), [compare])
  const compareCustom = useCallback((text: string) => compare({ caller_text: text }), [compare])

  const confirm = useCallback(async (text: string) => {
    const active = comparisonRef.current
    if (!active || readOnlyRef.current || confirming.current || confirmationUsed.current
      || active.v2_result.turn2 !== null || active.v2_result.turn1.conversation_state !== 'AWAITING_CONFIRMATION'
      || !active.v2_result.turn1.proposed_slot) return
    const generation = comparisonGeneration.current
    const id = active.conversation_id
    confirming.current = true
    confirmationUsed.current = true
    setConfirmationAttempted(true)
    setConfirmationLoading(true)
    setConfirmationError(null)
    const current = () => mounted.current && generation === comparisonGeneration.current
      && comparisonRef.current?.conversation_id === id && !readOnlyRef.current
    try {
      const response = await api.confirm({ conversation_id: id, caller_text: text })
      if (current()) {
        if (response.conversation_id !== id) {
          throw new ApiError('INVALID_RESPONSE', 'The confirmation response belongs to a different conversation.')
        }
        const updated = { ...active, v2_result: { ...active.v2_result, turn2: response.v2_result } }
        comparisonRef.current = updated
        setComparison(updated)
        setConfirmedCalendar(response.calendar)
      }
    } catch (error) {
      if (current()) setConfirmationError(toApiError(error))
    } finally {
      if (generation === comparisonGeneration.current) {
        confirming.current = false
        if (mounted.current) setConfirmationLoading(false)
      }
    }
  }, [])

  const runSuite = useCallback(async () => {
    if (suitePending.current) return
    suitePending.current = true
    setSuiteLoading(true)
    setSuiteError(null)
    try {
      const response = await api.suite({ execution_mode: mode })
      if (mounted.current) setSuite(response)
    } catch (error) {
      if (mounted.current) setSuiteError(toApiError(error))
    } finally {
      suitePending.current = false
      if (mounted.current) setSuiteLoading(false)
    }
  }, [mode])

  const inspectScenario = useCallback((score: ScenarioScore) => {
    ++comparisonGeneration.current
    pendingComparison.current = null
    confirming.current = false
    confirmationUsed.current = true
    comparisonRef.current = score.comparison
    readOnlyRef.current = true
    activeInput.current = { scenario_id: score.scenario_id }
    setSelectedScenarioId(score.scenario_id)
    setReadOnly(true)
    setComparison(score.comparison)
    setComparisonLoading(false)
    setComparisonError(null)
    setConfirmationLoading(false)
    setConfirmationAttempted(false)
    setConfirmationError(null)
    setConfirmedCalendar(null)
  }, [])

  const startFresh = useCallback(() => compare(activeInput.current), [compare])

  useEffect(() => {
    mounted.current = true
    if (!initialized.current) {
      initialized.current = true
      void reloadMetadata()
      void compareScenario('TC-01')
      void runSuite()
    }
    return () => { mounted.current = false }
  }, [compareScenario, reloadMetadata, runSuite])

  const initialCalendar = scenarios?.initial_calendar ?? []
  const inspectedMutation = readOnly ? comparison?.v2_result.turn2?.db_mutation_result : null
  const inspectedSlot = inspectedMutation?.mutated ? inspectedMutation.slot : null
  const calendar = confirmedCalendar ?? (inspectedSlot
    ? initialCalendar.map((slot) => slot.slot_id === inspectedSlot.slot_id ? inspectedSlot : slot)
    : initialCalendar)

  return {
    mode, setMode, health, scenarios, prompts, metadataErrors, reloadMetadata,
    comparison, selectedScenarioId, comparisonLoading, comparisonError, readOnly,
    calendar,
    confirmationLoading, confirmationError, confirmationAttempted, confirm,
    suite, suiteLoading, suiteError, runSuite,
    compareScenario, compareCustom, inspectScenario, startFresh,
  }
}

export type Harness = ReturnType<typeof useHarness>

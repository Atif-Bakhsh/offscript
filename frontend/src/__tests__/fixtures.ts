import report from '../../../backend/eval_report.json'
import scenarioData from './scenarios.json'
import type { ScenarioCompareResponse, ScenariosResponse, SuiteEvaluationReport } from '../types'

export const suite = report as SuiteEvaluationReport
export const scenarios = scenarioData as ScenariosResponse

export function comparison(index = 0): ScenarioCompareResponse {
  const result = structuredClone(suite.per_scenario[index].comparison)
  result.v2_result.turn2 = null
  return result
}

export function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export const health = {
  status: 'ok', mode: 'verified_replay', provider: null, model: null,
  storage: 'conversation-local in-memory', durable: false, workers: 1, session_ttl_seconds: 1800,
}

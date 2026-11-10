import type { AgentTurnOutput, ScenarioScore, SuiteEvaluationReport } from '../types'
import { suiteMetrics } from '../domain'
import { ArrowButton, Diagnostic, Loading, Provenance, SectionHeading } from './ui'
import { pillars } from './uiUtils'
import type { ErrorLike } from './ui'

export interface ScorecardProps {
  report: SuiteEvaluationReport | null
  loading: boolean
  error?: ErrorLike | null
  onRun: () => void
  onInspect: (score: ScenarioScore) => void
}

function PillarBadges({ turn, version }: { turn: AgentTurnOutput; version: string }) {
  return <div className="matrix-pillars" aria-label={`${version} rubric pillars`}>{pillars.map(([key, label], index) => <span key={key} className={`matrix-pillar mono ${turn.rubric_evaluation[key] ? 'pass' : 'fail'}`} title={`${label}: ${turn.rubric_evaluation[key] ? 'pass' : 'fail'}`} aria-label={`${label} ${turn.rubric_evaluation[key] ? 'pass' : 'fail'}`}><span aria-hidden="true">{turn.rubric_evaluation[key] ? '✓' : '×'}</span><span className="sr-only">{index + 1}</span></span>)}</div>
}

export function Scorecard({ report, loading, error, onRun, onInspect }: ScorecardProps) {
  const metrics = report ? suiteMetrics(report) : null
  return <section className="scorecard-section architectural-section" aria-labelledby="scorecard-title" aria-busy={loading}>
    <SectionHeading index="03" label="SUITE SCORECARD" title="The difference, measured">
      <button className="secondary-button" disabled={loading} onClick={onRun}>{loading ? 'Evaluating five cases…' : 'Run suite again'} <span aria-hidden="true">↗</span></button>
    </SectionHeading>
    <Diagnostic error={error} />
    {!report || !metrics ? <Loading text={loading ? 'Calculating the five-case benchmark' : 'Suite results are not available'} /> : <>
      <Provenance execution={report.execution} />
      <div className="metrics-strip">
        <div className="metric metric-primary"><div className="metric-value mono" data-testid="suite-pass-rate"><span>{report.v1.pass_rate_percent}%</span><span className="metric-arrow">→</span><span className={report.v2.pass_rate_percent > report.v1.pass_rate_percent ? 'positive' : report.v2.pass_rate_percent < report.v1.pass_rate_percent ? 'negative' : ''}>{report.v2.pass_rate_percent}%</span></div><p>Turn-1 suite pass rate</p><span className="mono">v1 {report.v1.passed}/{report.v1.total} · v2 {report.v2.passed}/{report.v2.total}</span></div>
        <div className="metric"><div className="metric-value mono" data-testid="confirmed-bookings">{metrics.confirmedBookings}<span className="metric-denominator"> / {metrics.rescheduleCases}</span></div><p>Confirmed callback bookings</p><span className="mono">Reschedule cases TC-01–TC-04</span></div>
        <div className="metric"><div data-testid="unconfirmed-mutations" className={`metric-value mono ${metrics.unconfirmedMutations ? 'negative' : ''}`}>{metrics.unconfirmedMutations}</div><p>Unconfirmed database mutations</p><span className="mono">Observed across both Turn-1 agents</span></div>
        <div className="metric"><div className="metric-value mono">&lt; 25<span className="metric-unit"> words</span></div><p>Voice turn brevity gate</p><span className="mono">24-word maximum</span></div>
      </div>
      <div className="benchmark-caption"><p>{report.benchmark_basis}</p><span data-testid="confirmation-checks" className="confirmation-total mono">{report.v2_confirmation.passed}/{report.v2_confirmation.total} confirmation checks passed</span></div>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Five-scenario batch evaluation matrix">
        <table className="score-matrix"><caption className="sr-only">Four pillars in order: booking gate, cue and correction, hallucination guard, voice brevity</caption><thead><tr><th scope="col">Test case</th><th scope="col">Baseline / v1</th><th scope="col">Refined / v2</th><th scope="col">Confirmation</th><th scope="col"><span className="sr-only">Inspect</span></th></tr></thead>
          <tbody>{report.per_scenario.map(row => <tr key={row.scenario_id} data-testid={`suite-row-${row.scenario_id}`}>
            <th scope="row"><span className="mono scenario-id">{row.scenario_id}</span><span>{row.title}</span></th>
            <td><PillarBadges turn={row.comparison.v1_result.turn1} version="v1" /></td><td><PillarBadges turn={row.comparison.v2_result.turn1} version="v2" /></td>
            <td><span className={`table-confirmation mono ${row.confirmation_passed ? 'positive' : 'negative'}`}>{row.confirmation_passed ? 'PASS' : 'FAIL'}{row.scenario_id === 'TC-05' ? ' / opt-out' : ''}</span></td>
            <td><button className="inspect-button" aria-label={`Inspect ${row.scenario_id} in arena`} onClick={() => onInspect(row)}>Inspect in arena <span aria-hidden="true">↗</span></button></td>
          </tr>)}</tbody></table>
      </div>
      <p className="matrix-legend">Pillars: booking gate · cue & correction · hallucination guard · voice brevity</p>
      {loading && <p className="inline-status mono" role="status">Previous results shown while a new suite runs…</p>}
    </>}
    {!report && !loading && <ArrowButton onClick={onRun}>Run full 5-case suite</ArrowButton>}
  </section>
}

import type { ReactNode } from 'react'
import type { AgentTurnOutput, PublicScenario, ScenarioCompareResponse, VersionResult } from '../types'
import { ArrowButton, Diagnostic, Loading, Provenance, SectionHeading } from './ui'
import { pillars, slotText } from './uiUtils'
import type { ErrorLike } from './ui'

export interface ArenaProps {
  comparison: ScenarioCompareResponse | null
  scenario?: PublicScenario | null
  readOnly: boolean
  loading: boolean
  confirmLoading: boolean
  confirmationAttempted: boolean
  confirmError?: ErrorLike | null
  confirmationText: string
  onConfirmationTextChange: (text: string) => void
  onConfirm: () => void
  onFresh: () => void
}

export function Rubric({ turn }: { turn: AgentTurnOutput }) {
  const rubric = turn.rubric_evaluation
  return <div className="rubric-card">
    <div className="rubric-title mono">FOUR-PILLAR EVALUATION<span>{rubric.all_passed ? '4 / 4 passed' : `${pillars.filter(([key]) => rubric[key]).length} / 4 passed`}</span></div>
    <div className="rubric-rows">{pillars.map(([key, label]) => <div key={key} className={`rubric-row ${rubric[key] ? 'passed' : 'failed'}`}>
      <div className="rubric-row-heading"><span>{label}</span><span className="rubric-result mono"><span aria-hidden="true">{rubric[key] ? '✓' : '×'}</span> {rubric[key] ? 'PASS' : 'FAIL'}</span></div>
      <ul>{(rubric.evidence[key] || []).map((evidence, index) => <li key={index}>{evidence}</li>)}</ul>
    </div>)}</div>
    <p className="rubric-methodology">{rubric.methodology}</p>
  </div>
}

function TurnSpeech({ turn, number }: { turn: AgentTurnOutput; number: number }) {
  return <div className={`turn-speech turn-${number}`}>
    <div className="turn-label mono"><span>TURN {number} / AGENT REPLY</span><span>{turn.rubric_evaluation.word_count} / 24 words</span></div>
    <blockquote>{turn.agent_reply}</blockquote>
    <div className="cue-tags">{turn.detected_cues.map((cue, i) => <span className="cue-tag mono" key={`${cue}-${i}`}>{cue.replaceAll('_', ' ')}</span>)}</div>
    {turn.proposed_slot && <p className="proposed-slot"><span className="mono">PROPOSED SLOT</span>{slotText(turn.proposed_slot)}</p>}
  </div>
}

function ToolDrawer({ result }: { result: VersionResult }) {
  const latest = result.turn2 || result.turn1
  return <details className="tool-drawer" open>
    <summary><span className="mono">MOCK DATABASE & TOOL LOG</span><span className={`mutation-badge mono ${latest.db_mutation_result.mutated ? 'committed' : latest.tool_call?.status === 'REJECTED' ? 'rejected' : 'unchanged'}`}>{latest.db_mutation_result.mutated ? 'COMMITTED' : latest.tool_call?.status === 'REJECTED' ? 'REJECTED' : 'NO MUTATION'}</span></summary>
    {[result.turn1, ...(result.turn2 ? [result.turn2] : [])].map((turn, i) => <div className="tool-turn" key={i}>
      <div className="tool-turn-heading mono"><span>TURN {i + 1}</span><span>{turn.tool_call?.status || 'NO TOOL CALL'}</span></div>
      <pre tabIndex={0} aria-label={`Turn ${i + 1} tool call and mutation result`}>{JSON.stringify({ tool_call: turn.tool_call, db_mutation_result: turn.db_mutation_result }, null, 2)}</pre>
    </div>)}
  </details>
}

function AgentColumn({ title, subtitle, version, result, children }: { title: string; subtitle: string; version: 'v1' | 'v2'; result: VersionResult; children?: ReactNode }) {
  const first = result.turn1
  const latest = result.turn2 || first
  return <article className={`agent-column ${first.rubric_evaluation.all_passed ? 'agent-pass' : 'agent-fail'}`} aria-label={version === 'v1' ? 'Baseline agent' : 'Refined agent'} data-testid={version === 'v1' ? 'baseline-agent' : 'refined-agent'}>
    <div className="agent-heading">
      <div><p className="mono agent-version">{version.toUpperCase()} / {subtitle}</p><h3>{title}</h3></div>
      <span className={`overall-badge mono ${first.rubric_evaluation.all_passed ? 'pass' : 'fail'}`}>{first.rubric_evaluation.all_passed ? 'PASS' : 'FAIL'}<span>Turn 1</span></span>
    </div>
    <Provenance execution={first.execution} />
    <div className="agent-state-row"><span className="state-badge mono">{latest.conversation_state}</span><span className="state-explainer">Agent-reported state</span></div>
    {latest.conversation_state === 'BOOKED' && !latest.db_mutation_result.mutated && <p className="blocked-claim">Booking claim blocked · the database was not changed</p>}
    <TurnSpeech turn={first} number={1} />
    <Rubric turn={first} />
    {result.turn2 && <div className="confirmation-result">
      <TurnSpeech turn={result.turn2} number={2} />
      <Provenance execution={result.turn2.execution} />
      <Rubric turn={result.turn2} />
    </div>}
    {children}
    <ToolDrawer result={result} />
  </article>
}

export function Arena({ comparison, scenario, readOnly, loading, confirmLoading, confirmationAttempted, confirmError, confirmationText, onConfirmationTextChange, onConfirm, onFresh }: ArenaProps) {
  const refined = comparison?.v2_result
  const ended = refined?.turn1.conversation_state === 'ENDED'
  const optedOutScenario = comparison?.scenario_id === 'TC-05'
  const pending = refined?.turn1.conversation_state === 'AWAITING_CONFIRMATION' && refined.turn1.proposed_slot && !refined.turn2 && !confirmationAttempted
  return <section id="arena" className="arena-section architectural-section" aria-labelledby="arena-title" aria-busy={loading}>
    <SectionHeading index="02" label="EXECUTION ARENA" title="Same caller. Different decisions.">
      <p>Prompt behavior is measured. Python authorizes every write.</p>
    </SectionHeading>
    {readOnly && <div className="snapshot-notice"><div><strong>Read-only suite snapshot</strong><p>These are the exact batch results. Start a fresh comparison to interact with this case.</p></div><button className="secondary-button" onClick={onFresh}>Start fresh comparison</button></div>}
    {loading ? <Loading text="Comparing baseline and state-guarded prompts" /> : !comparison ? <div className="empty-state">Select a scenario to inspect the agents’ decisions</div> : <>
      <div className="arena-session mono"><span>{comparison.scenario_id || 'CUSTOM'} / {readOnly ? 'BATCH SNAPSHOT' : 'INTERACTIVE COMPARISON'}</span><span title={comparison.conversation_id}>SESSION {comparison.conversation_id.slice(0, 8)}</span></div>
      <div className="arena-grid">
        <AgentColumn title="Baseline agent" subtitle="NAIVE SALES PROMPT" version="v1" result={comparison.v1_result} />
        <AgentColumn title="Refined agent" subtitle="STATE-GUARDED PROMPT" version="v2" result={comparison.v2_result}>
          {ended || optedOutScenario ? <div className="terminal-notice"><span className="mono">{optedOutScenario ? 'TERMINAL OPT-OUT' : 'CONVERSATION ENDED'}</span><p>No Turn-2 confirmation needed</p><span>{optedOutScenario ? 'This caller has opted out of the simulated conversation' : 'The simulated conversation has ended'}</span></div> : pending && !readOnly ? <form className="confirmation-box" onSubmit={event => { event.preventDefault(); onConfirm() }}>
            <div className="confirmation-box-heading"><span className="gate-indicator" aria-hidden="true" /><span className="mono">CONFIRMATION GATE / WAITING</span></div>
            <p>The exact slot is proposed. The calendar is unchanged.</p>
            <label htmlFor="caller-confirmation">Caller confirmation</label>
            <textarea id="caller-confirmation" rows={2} maxLength={4000} value={confirmationText} disabled={confirmLoading} onChange={event => onConfirmationTextChange(event.target.value)} />
            <ArrowButton type="submit" disabled={confirmLoading || !confirmationText.trim()}>{confirmLoading ? 'Checking confirmation…' : 'Simulate caller confirmation'}</ArrowButton>
            <span className="confirmation-note">Turn 2 uses this conversation’s original execution mode</span>
          </form> : !readOnly && !refined?.turn2 && !confirmationAttempted ? <div className="terminal-notice"><p>No confirmable proposal was established</p><button className="secondary-button" onClick={onFresh}>Start fresh comparison</button></div> : null}
          {!readOnly && confirmationAttempted && !confirmLoading && <div className={`confirmation-outcome ${refined?.turn2?.db_mutation_result.mutated ? 'committed' : ''}`}>
            <strong>{confirmError ? 'Confirmation result unavailable' : refined?.turn2?.db_mutation_result.mutated ? 'Callback committed to the mock calendar' : 'No booking was committed'}</strong>
            {confirmError ? <p>The request may have reached the server. Start a fresh comparison before continuing.</p> : !refined?.turn2?.db_mutation_result.mutated && <p>Start a fresh comparison before trying another confirmation</p>}
            <Diagnostic error={confirmError} />
            <button className="secondary-button" onClick={onFresh}>Start fresh comparison</button>
          </div>}
          {!readOnly && confirmLoading && <p className="inline-status mono" role="status">Verifying consent and calendar availability…</p>}
        </AgentColumn>
      </div>
      {scenario?.caller_turn2 === null && !ended && <p className="muted">This scenario has no fixture confirmation turn</p>}
    </>}
  </section>
}

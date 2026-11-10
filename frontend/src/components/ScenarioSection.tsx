import { useState } from 'react'
import type { CalendarSlot, Mode, PublicScenario } from '../types'
import { ArrowButton, Diagnostic, Loading, SectionHeading } from './ui'
import type { ErrorLike } from './ui'

export interface ScenarioSectionProps {
  scenarios: PublicScenario[]
  calendar: CalendarSlot[]
  activeScenarioId: string | null
  callerText: string
  expectedBehavior: string
  loading: boolean
  onSelectScenario: (id: string) => void
  onRunCustom: (text: string) => void
  mode: Mode
  error?: ErrorLike | null
}

const shortTitles: Record<string, string> = {
  'TC-01': 'The self-correction', 'TC-02': 'The distracted driver', 'TC-03': 'The unavailable slot', 'TC-04': 'The fee question', 'TC-05': 'The hard opt-out',
}
const scenarioTags: Record<string, string> = {
  'TC-01': 'Retracted intent', 'TC-02': 'Polite filler ≠ consent', 'TC-03': 'Calendar boundary', 'TC-04': 'Unverified fact', 'TC-05': 'Terminal state',
}

export function ScenarioSection({ scenarios, calendar, activeScenarioId, callerText, expectedBehavior, loading, onSelectScenario, onRunCustom, mode, error }: ScenarioSectionProps) {
  const [customText, setCustomText] = useState('')
  return <section className="scenario-section architectural-section" aria-labelledby="scenario-title">
    <SectionHeading index="01" label="SCENARIO & CALENDAR" title="Put the conversation off script">
      <p>One caller. Two prompts. One guarded calendar.</p>
    </SectionHeading>
    <div className="calendar-strip" aria-label="Conversation calendar">
      <div className="calendar-label mono">MOCK CALENDAR<span>Local to this comparison</span></div>
      {calendar.length ? calendar.map(slot => <div key={slot.slot_id} className={`calendar-slot ${slot.status.toLowerCase()}`} data-testid={`slot-${slot.slot_id}`}>
        <span className="slot-time mono">{slot.day} <strong>{slot.time_24h}</strong></span>
        <span className="slot-status mono"><span className="status-dot" aria-hidden="true" />{slot.status}</span>
      </div>) : <Loading text="Loading calendar" />}
    </div>
    <div className="scenario-grid" aria-label="Curated scenarios">
      {scenarios.map((scenario, index) => <button key={scenario.scenario_id} data-testid={`scenario-${scenario.scenario_id}`} className={`scenario-card ${activeScenarioId === scenario.scenario_id ? 'selected' : ''}`} aria-pressed={activeScenarioId === scenario.scenario_id} aria-label={`${scenario.scenario_id}: ${scenario.title}`} onClick={() => onSelectScenario(scenario.scenario_id)}>
        <span className="scenario-card-top mono"><span>{scenario.scenario_id}</span><span aria-hidden="true">{activeScenarioId === scenario.scenario_id ? '↗' : String(index + 1).padStart(2, '0')}</span></span>
        <strong>{shortTitles[scenario.scenario_id] || scenario.title}</strong>
        <span className="scenario-card-tag">{scenarioTags[scenario.scenario_id] || scenario.title}</span>
      </button>)}
    </div>
    <div className="caller-banner" aria-busy={loading}>
      <div className="caller-label mono"><span className="caller-avatar" aria-hidden="true">A</span><span>ALEX / CALLER TURN 1</span><span>{activeScenarioId || 'CUSTOM INPUT'}</span></div>
      {callerText ? <blockquote>{callerText}</blockquote> : <Loading text="Loading the first conversation" />}
      {expectedBehavior && <div className="expected-behavior"><span className="mono">EXPECTED V2</span><p>{expectedBehavior}</p></div>}
      {loading && <p className="inline-status mono" role="status">Running comparison…</p>}
    </div>
    <Diagnostic error={error} />
    <details className="custom-input">
      <summary>Test a custom English caller line <span className="mono">LIVE MODE REQUIRED</span></summary>
      <form onSubmit={event => { event.preventDefault(); if (customText.trim()) onRunCustom(customText.trim()) }}>
        <label htmlFor="custom-caller">Custom caller text</label>
        <textarea id="custom-caller" maxLength={4000} rows={3} value={customText} onChange={event => setCustomText(event.target.value)} placeholder="I'm busy. Could you call Thursday after 6 PM?" />
        <div className="form-footer"><p>Custom input uses a configured live provider. {mode === 'replay' ? 'Replay supports the five curated scenarios only.' : 'Provider credentials stay in the backend.'} <span className="mono">{customText.length} / 4,000</span></p><ArrowButton disabled={loading || !customText.trim()} type="submit">Compare custom input</ArrowButton></div>
      </form>
    </details>
  </section>
}

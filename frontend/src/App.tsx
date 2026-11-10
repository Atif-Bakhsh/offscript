import { useState } from 'react'
import { useHarness } from './useHarness'
import { defaultConfirmation } from './domain'
import { Header } from './components/Header'
import { ScenarioSection } from './components/ScenarioSection'
import { Arena } from './components/Arena'
import { Scorecard } from './components/Scorecard'
import { PromptLab } from './components/PromptLab'
import { Diagnostic } from './components/ui'
import type { Harness } from './useHarness'
import type { PublicScenario } from './types'

function ConversationArena({ harness, scenario }: { harness: Harness; scenario?: PublicScenario }) {
  const [confirmationText, setConfirmationText] = useState(() => harness.comparison
    ? defaultConfirmation(harness.comparison.v2_result.turn1, scenario) : '')
  return <Arena
    comparison={harness.comparison} scenario={scenario} readOnly={harness.readOnly}
    loading={harness.comparisonLoading} confirmLoading={harness.confirmationLoading}
    confirmationAttempted={harness.confirmationAttempted} confirmError={harness.confirmationError}
    confirmationText={confirmationText} onConfirmationTextChange={setConfirmationText}
    onConfirm={() => void harness.confirm(confirmationText)} onFresh={() => void harness.startFresh()}
  />
}

export default function App() {
  const harness = useHarness()
  const [submittedCustomText, setSubmittedCustomText] = useState('')
  const scenario = harness.scenarios?.scenarios.find(item => item.scenario_id === harness.selectedScenarioId)
  const inspect: typeof harness.inspectScenario = score => {
    harness.inspectScenario(score)
    document.getElementById('arena')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  }
  return <>
    <a className="skip-link" href="#main">Skip to console</a>
    <Header health={harness.health} context={harness.scenarios?.simulation_context ?? null}
      mode={harness.mode} onModeChange={harness.setMode} onRunSuite={() => void harness.runSuite()}
      suiteLoading={harness.suiteLoading} healthError={harness.metadataErrors.health}
      onRetryMetadata={() => void harness.reloadMetadata()} />
    <main id="main" className="console-shell">
      <div className="console-intro">
        <div><p className="eyebrow mono">OFF-SCRIPT STRESS TESTING / ENGLISH</p>
          <h1>When the caller<br />leaves the script.</h1>
          <p className="intro-description">Compare how voice agents handle the unexpected.<br className="desktop-break" /> Inspect the decision. Verify the write.</p>
        </div>
        <div className="intro-spec">
          <div><span className="mono">SUBJECT</span><p>Alex · Travel card callback</p></div>
          <div><span className="mono">TEST SURFACE</span><p>Intent, timing, facts & consent</p></div>
          <div><span className="mono">WRITE AUTHORITY</span><p>Python confirmation guard</p></div>
        </div>
      </div>
      {harness.metadataErrors.scenarios && <div className="metadata-error"><Diagnostic error={harness.metadataErrors.scenarios} /><button className="secondary-button" onClick={() => void harness.reloadMetadata()}>Reload scenarios</button></div>}
      <ScenarioSection scenarios={harness.scenarios?.scenarios ?? []} calendar={harness.calendar}
        activeScenarioId={harness.selectedScenarioId}
        callerText={harness.comparison?.caller_text ?? scenario?.caller_turn1 ?? (harness.selectedScenarioId === null ? submittedCustomText : '')}
        expectedBehavior={scenario?.expected_behavior ?? ''} loading={harness.comparisonLoading}
        onSelectScenario={id => void harness.compareScenario(id)} onRunCustom={text => { setSubmittedCustomText(text); void harness.compareCustom(text) }}
        mode={harness.mode} error={harness.comparisonError} />
      {harness.comparisonError && <button className="secondary-button comparison-recovery" onClick={() => void harness.startFresh()}>Start fresh comparison</button>}
      <ConversationArena key={`${harness.comparison?.conversation_id ?? 'loading'}-${harness.readOnly}-${scenario?.caller_turn2 ?? ''}`} harness={harness} scenario={scenario} />
      <Scorecard report={harness.suite} loading={harness.suiteLoading} error={harness.suiteError}
        onRun={() => void harness.runSuite()} onInspect={inspect} />
      <PromptLab data={harness.prompts} error={harness.metadataErrors.prompts} onRetry={() => void harness.reloadMetadata()} />
      <footer className="console-footer"><a href="#main" className="footer-brand">[O] OffScript</a><p>Transcript simulation · Conversation-local mock storage · Single worker</p><span className="mono">NO REAL CALLS. NO REAL BOOKINGS.</span></footer>
    </main>
  </>
}

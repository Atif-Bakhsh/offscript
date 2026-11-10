import type { HealthResponse, Mode, SimulationContext } from '../types'
import { ArrowButton, Diagnostic } from './ui'
import { modeText, simulationClock } from './uiUtils'
import type { ErrorLike } from './ui'

export interface HeaderProps {
  health: HealthResponse | null
  context: SimulationContext | null
  mode: Mode
  onModeChange: (mode: Mode) => void
  onRunSuite: () => void
  suiteLoading: boolean
  healthError?: ErrorLike | null
  onRetryMetadata?: () => void
}

export function Header({ health, context, mode, onModeChange, onRunSuite, suiteLoading, healthError, onRetryMetadata }: HeaderProps) {
  const clock = simulationClock(context)
  return <>
    <header className="app-header">
      <a className="brand" href="#main" aria-label="OffScript console"><span className="brand-mark mono" aria-hidden="true">[O]</span><span>OffScript</span></a>
      <span className="brand-caption mono">VOICE AGENT QA HARNESS</span>
      <div className="header-status" aria-label="Configured backend mode and simulation time">
        <span className={`backend-status mono ${health && !healthError ? 'online' : ''}`}><span className="status-dot" aria-hidden="true" />{healthError ? 'BACKEND UNAVAILABLE' : health ? modeText(health.mode) : 'CONNECTING'}</span>
        <span className="simulation-clock">{clock}</span>
      </div>
      <div className="header-actions">
        <label className="mode-control mono">Run mode<select aria-label="Execution mode" value={mode} onChange={event => onModeChange(event.target.value as Mode)}>
          <option value="auto">Auto</option><option value="replay">Replay</option><option value="live">Live</option>
        </select></label>
        <ArrowButton onClick={onRunSuite} disabled={suiteLoading}>{suiteLoading ? 'Running full suite…' : 'Run full 5-case suite'}</ArrowButton>
      </div>
    </header>
    {healthError && <div className="header-diagnostic"><Diagnostic error={healthError} />{onRetryMetadata && <button className="secondary-button" onClick={onRetryMetadata}>Reconnect backend</button>}</div>}
  </>
}

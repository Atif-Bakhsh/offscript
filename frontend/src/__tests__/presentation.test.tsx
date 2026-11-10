import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Arena, type ArenaProps } from '../components/Arena'
import { Diagnostic, Provenance } from '../components/ui'
import { simulationClock } from '../components/uiUtils'
import { comparison, scenarios, suite } from './fixtures'

function arenaProps(): ArenaProps {
  return {
    comparison: comparison(), readOnly: false, loading: false, confirmLoading: false,
    confirmationAttempted: false, confirmationText: 'Yes, please book it.',
    onConfirmationTextChange: vi.fn(), onConfirm: vi.fn(), onFresh: vi.fn(),
  }
}

describe('visible diagnostics and provenance', () => {
  it('renders the backend code, message and field evidence as an accessible alert', () => {
    render(<Diagnostic error={{ code: 'INVALID_REQUEST', message: 'Use English caller text.', details: [{ field: 'caller_text', message: 'Only English is supported.' }] }} />)
    expect(screen.getByRole('alert')).toHaveTextContent('INVALID_REQUEST')
    expect(screen.getByRole('alert')).toHaveTextContent('Use English caller text.')
    expect(screen.getByRole('alert')).toHaveTextContent('caller_text: Only English is supported.')
  })

  it('does not imply live measurement for a replay fixture', () => {
    render(<Provenance execution={suite.execution} />)
    expect(screen.getByText('VERIFIED REPLAY')).toBeVisible()
    expect(screen.getByText('Curated validated fixtures')).toBeVisible()
    expect(screen.queryByText('Measured model outcome')).not.toBeInTheDocument()
  })

  it('shows a blocked baseline claim while preserving the exact reply and rejection evidence', () => {
    const props = arenaProps()
    render(<Arena {...props} />)
    expect(screen.getByText(props.comparison!.v1_result.turn1.agent_reply)).toBeVisible()
    expect(screen.getByText('Booking claim blocked · the database was not changed')).toBeVisible()
    expect(screen.getByTestId('baseline-agent')).toHaveTextContent('PREMATURE_UNCONFIRMED_MUTATION')
    expect(screen.getByRole('button', { name: 'Simulate caller confirmation' })).toBeVisible()
  })

  it('requires a fresh run after a nonbooking attempt and disables suite snapshot interaction', () => {
    const props = arenaProps()
    const view = render(<Arena {...props} confirmationAttempted confirmError={{ code: 'SESSION_EXPIRED', message: 'Start a new comparison.' }} />)
    expect(screen.queryByRole('button', { name: 'Simulate caller confirmation' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start fresh comparison' })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('SESSION_EXPIRED')
    view.rerender(<Arena {...props} readOnly />)
    expect(screen.getByText('Read-only suite snapshot')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Simulate caller confirmation' })).not.toBeInTheDocument()
  })

  it('keeps opt-outs terminal even when an evaluated model incorrectly proposes another call', () => {
    const props = arenaProps()
    const rawReply = props.comparison!.v2_result.turn1.agent_reply
    props.comparison!.scenario_id = 'TC-05'
    render(<Arena {...props} scenario={scenarios.scenarios[4]} />)
    expect(screen.getByText(rawReply)).toBeVisible()
    expect(screen.getByText('TERMINAL OPT-OUT')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Simulate caller confirmation' })).not.toBeInTheDocument()
  })

  it('handles invalid simulation metadata without a rendering exception', () => {
    expect(simulationClock({ ...scenarios.simulation_context, reference_datetime: 'not-a-date' })).toBe('Simulation clock unavailable')
    expect(simulationClock({ ...scenarios.simulation_context, timezone: 'Invalid/Zone' })).toBe('Simulation clock unavailable')
  })
})

import { PILLARS, slotLabel } from '../domain'
import type { SimulationContext, SlotReference } from '../types'

export const pillars = PILLARS.map(({ key, label }) => [key, label] as const)

export function slotText(slot: SlotReference): string {
  return slotLabel(slot)
}

export function modeText(mode: string): string {
  return mode.replaceAll('_', ' ').toUpperCase()
}

export function simulationClock(context: SimulationContext | null): string {
  if (!context) return 'Loading simulation clock'
  try {
    const date = new Date(context.reference_datetime)
    if (!Number.isFinite(date.getTime())) return 'Simulation clock unavailable'
    return new Intl.DateTimeFormat('en-US', {
      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric',
      minute: '2-digit', timeZone: context.timezone,
    }).format(date)
  } catch {
    return 'Simulation clock unavailable'
  }
}

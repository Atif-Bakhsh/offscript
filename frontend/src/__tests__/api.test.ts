import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { CompareRequest } from '../types'
import { comparison, health, jsonResponse, scenarios } from './fixtures'

afterEach(() => vi.unstubAllGlobals())

describe('HTTP boundary', () => {
  it('sends exactly one comparison selector and its execution override', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(comparison()))
    vi.stubGlobal('fetch', fetchMock)
    await api.compare({ scenario_id: 'TC-01', execution_mode: 'replay' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ scenario_id: 'TC-01', execution_mode: 'replay' })
    fetchMock.mockResolvedValue(jsonResponse(comparison()))
    await api.compare({ caller_text: "I'm busy", execution_mode: 'live' })
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ caller_text: "I'm busy", execution_mode: 'live' })
  })

  it('rejects an invalid combined selector before issuing any request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(api.compare({ scenario_id: 'TC-01', caller_text: 'Hello' } as unknown as CompareRequest)).rejects.toMatchObject({ code: 'INVALID_REQUEST' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('preserves server error codes, messages and field details without retrying POSTs', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ error: {
      code: 'LIVE_MODE_REQUIRED', message: 'Custom input requires live mode.',
      details: [{ field: 'caller_text', message: 'Choose live execution.' }],
    } }, 409))
    vi.stubGlobal('fetch', fetchMock)
    await expect(api.compare({ caller_text: 'Hello', execution_mode: 'replay' })).rejects.toMatchObject({
      code: 'LIVE_MODE_REQUIRED', message: 'Custom input requires live mode.', status: 409,
      details: [{ field: 'caller_text', message: 'Choose live execution.' }],
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('rejects malformed JSON and structurally invalid success payloads', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('not JSON', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(api.health()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    fetchMock.mockResolvedValue(jsonResponse({ ...health, durable: 'false' }))
    await expect(api.health()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    const invalid = comparison()
    ;(invalid.v2_result.turn1.rubric_evaluation as unknown as { evidence: unknown }).evidence = { booking_gate_passed: 'not an array' }
    fetchMock.mockResolvedValue(jsonResponse(invalid))
    await expect(api.compare({ scenario_id: 'TC-01' })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('turns unreachable-server failures into a recoverable error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api.health()).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('rejects invalid simulation dates and timezones before they reach the clock renderer', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    for (const patch of [{ reference_datetime: 'not a date' }, { timezone: 'Mars/OffScript' }]) {
      fetchMock.mockResolvedValue(jsonResponse({
        ...scenarios,
        simulation_context: { ...scenarios.simulation_context, ...patch },
      }))
      await expect(api.scenarios()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    }
  })
})

import { expect, test, type Page } from '@playwright/test'

async function startup(page: Page) {
  await page.goto('/')
  await expect(page.getByTestId('refined-agent')).toContainText('No problem. Would Thursday at 7:00 PM work for a callback?')
  await expect(page.getByTestId('suite-pass-rate')).toContainText('20%')
  await expect(page.getByTestId('suite-pass-rate')).toContainText('100%')
}

async function expectContainedViewport(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: innerWidth,
    width: document.documentElement.scrollWidth,
    containers: ['body', '.console-shell', '.scorecard-section', '.table-scroll', '.score-matrix', 'caption'].map((selector) => {
      const element = document.querySelector<HTMLElement>(selector)!
      const { x, right, width } = element.getBoundingClientRect()
      return { selector, x, right, width, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, overflowX: getComputedStyle(element).overflowX, position: getComputedStyle(element).position }
    }),
    overflow: Array.from(document.querySelectorAll('body *')).filter((element) => {
      const bounds = element.getBoundingClientRect()
      return bounds.right > innerWidth + 1 && getComputedStyle(element).position !== 'absolute' && !element.closest('.table-scroll,pre')
    }).map((element) => `${element.tagName}.${element.className}`).slice(0, 12),
  }))
  expect(dimensions.width, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.viewport)
}

test('replay startup, all five scenarios, four confirmed bookings, and isolated calendars', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  const errors: string[] = []
  const consoleErrors: string[] = []
  const fontErrors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    const url = message.location().url
    if (/fonts\.(googleapis|gstatic)\.com/.test(url)) fontErrors.push(`${url}: ${message.text()}`)
    else consoleErrors.push(`${url}: ${message.text()}`)
  })
  const startupRequests: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST') startupRequests.push(new URL(request.url()).pathname)
  })
  await startup(page)
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: 'test-results/desktop.png' })
  await page.locator('#arena').evaluate((element) => element.scrollIntoView({ block: 'start' }))
  await page.screenshot({ path: 'test-results/arena.png' })
  expect(startupRequests.filter((path) => path === '/api/compare-turn1')).toHaveLength(1)
  expect(startupRequests.filter((path) => path === '/api/evaluate-suite')).toHaveLength(1)
  await expect(page.getByLabel('Execution mode')).toHaveValue('replay')
  await expect(page.getByTestId('confirmed-bookings')).toContainText('4 / 4')
  await expect(page.getByTestId('confirmation-checks')).toContainText('5/5')
  await expect(page.getByTestId('unconfirmed-mutations')).toContainText('0')
  await expect(page.getByTestId('baseline-agent')).toContainText('REJECTED')
  await expect(page.getByTestId('baseline-agent')).toContainText('the database was not changed')

  const cases = [
    ['TC-01', 'No problem. Would Thursday at 7:00 PM work for a callback?', 'slot-thu-1900'],
    ['TC-02', 'Please focus on driving. Would Wednesday at 4:30 PM work for a callback?', 'slot-wed-1630'],
    ['TC-03', 'Sunday is outside our callback hours. Would Monday at 10:00 AM work?', 'slot-mon-1000'],
    ['TC-04', "I can't verify that ATM fee. Would Wednesday at 4:30 PM work for a callback?", 'slot-wed-1630'],
  ]
  for (const [id, reply, slot] of cases) {
    await page.getByTestId(`scenario-${id}`).click()
    await expect(page.getByTestId('refined-agent')).toContainText(reply)
    await expect(page.locator('[data-testid^="slot-"]').filter({ hasText: 'BOOKED_BY_AGENT' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Simulate caller confirmation', exact: true }).click()
    await expect(page.getByTestId(slot)).toContainText('BOOKED_BY_AGENT')
    await expect(page.getByTestId('refined-agent')).toContainText(reply)
    await expect(page.getByTestId('refined-agent')).toContainText('EXECUTED')
  }
  await page.getByTestId('scenario-TC-05').click()
  await expect(page.getByTestId('refined-agent')).toContainText("Understood. I'll end this call. Goodbye.")
  await expect(page.getByText('TERMINAL OPT-OUT', { exact: true })).toBeVisible()
  await expect(page.getByText('No Turn-2 confirmation needed', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Simulate caller confirmation', exact: true })).toHaveCount(0)
  await expect(page.locator('[data-testid^="slot-"]').filter({ hasText: 'BOOKED_BY_AGENT' })).toHaveCount(0)
  expect(errors).toEqual([])
  expect(consoleErrors).toEqual([])
  if (fontErrors.length) test.info().annotations.push({ type: 'font-network', description: fontErrors.join('\n') })
})

test('suite inspection retains the exact snapshot and requires a fresh interactive comparison', async ({ page }) => {
  await startup(page)
  let comparisonRequests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/compare-turn1')) comparisonRequests += 1
  })
  await page.getByTestId('suite-row-TC-03').getByRole('button', { name: /Inspect/ }).click()
  await expect(page.getByText('Read-only suite snapshot')).toBeVisible()
  await expect(page.getByTestId('refined-agent')).toContainText('EXECUTED')
  expect(comparisonRequests).toBe(0)
  await expect(page.getByRole('button', { name: 'Simulate caller confirmation', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Start fresh comparison', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Simulate caller confirmation', exact: true })).toBeVisible()
  await expect(page.getByText('Read-only suite snapshot')).toHaveCount(0)
  expect(comparisonRequests).toBe(1)
})

for (const caller of ['Is that confirmed', 'No, please do not book it.', 'Actually, Wednesday at 4:30 PM instead.']) {
  test(`rejects unsafe confirmation: ${caller}`, async ({ page }) => {
    await startup(page)
    await page.getByLabel('Caller confirmation', { exact: true }).fill(caller)
    await page.getByRole('button', { name: 'Simulate caller confirmation', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Start fresh comparison', exact: true })).toBeVisible()
    await expect(page.locator('[data-testid^="slot-"]').filter({ hasText: 'BOOKED_BY_AGENT' })).toHaveCount(0)
    await expect(page.getByTestId('refined-agent')).not.toContainText('EXECUTED')
    await page.getByRole('button', { name: 'Start fresh comparison', exact: true }).click()
    await page.getByRole('button', { name: 'Simulate caller confirmation', exact: true }).click()
    await expect(page.getByTestId('slot-thu-1900')).toContainText('BOOKED_BY_AGENT')
  })
}

test('custom replay input exposes the backend live-mode requirement', async ({ page }) => {
  await startup(page)
  await page.getByText('Test a custom English caller line', { exact: false }).click()
  await page.getByLabel('Custom caller text', { exact: true }).fill("I'm busy. Please call Thursday after six.")
  await page.getByRole('button', { name: /Compare custom input/ }).click()
  await expect(page.getByRole('alert')).toContainText('LIVE_MODE_REQUIRED')
  await expect(page.getByRole('alert')).toContainText(/live/i)
  await expect(page.locator('.caller-banner')).toContainText("I'm busy. Please call Thursday after six.")
})

for (const [code, status, message] of [
  ['SESSION_EXPIRED', 410, 'The conversation expired. Start a new comparison.'],
  ['PROVIDER_TIMEOUT', 504, 'The provider request timed out.'],
  ['PROVIDER_AUTHENTICATION_ERROR', 502, 'The provider rejected its credentials.'],
] as const) {
  test(`renders ${code} and offers recovery without an automatic retry`, async ({ page }) => {
    await startup(page)
    let attempts = 0
    await page.route('**/api/simulate-turn2', (route) => {
      attempts += 1
      return route.fulfill({ status, json: { error: { code, message } } })
    })
    await page.getByRole('button', { name: 'Simulate caller confirmation', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText(code)
    await expect(page.getByRole('alert')).toContainText(message)
    await expect(page.getByRole('button', { name: 'Start fresh comparison', exact: true })).toBeVisible()
    expect(attempts).toBe(1)
  })
}

test('handles missing keys, invalid responses, and network loss inline', async ({ page }) => {
  await startup(page)
  await page.route('**/api/compare-turn1', (route) => route.fulfill({ status: 503, json: { error: {
    code: 'API_KEY_REQUIRED', message: 'Live execution requires the selected provider key.',
    details: [{ field: 'execution_mode', message: 'Configure the backend key locally.' }],
  } } }))
  await page.getByLabel('Execution mode').selectOption('live')
  await page.getByTestId('scenario-TC-02').click()
  await expect(page.getByRole('alert')).toContainText('API_KEY_REQUIRED')
  await expect(page.getByRole('alert')).toContainText('Configure the backend key locally.')
  await page.unroute('**/api/compare-turn1')
  await page.route('**/api/compare-turn1', (route) => route.fulfill({ status: 200, json: { unexpected: true } }))
  await page.getByTestId('scenario-TC-03').click()
  await expect(page.getByRole('alert')).toContainText('INVALID_RESPONSE')
  await page.unroute('**/api/compare-turn1')
  await page.route('**/api/compare-turn1', (route) => route.abort('failed'))
  await page.getByTestId('scenario-TC-04').click()
  await expect(page.getByRole('alert')).toContainText('NETWORK_ERROR')
})

test('mobile layout contains horizontal overflow and supports keyboard access', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await startup(page)
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: 'test-results/mobile.png' })
  await expectContainedViewport(page)
  await page.keyboard.press('Tab')
  await expect(page.locator(':focus')).toBeVisible()
  await page.getByTestId('scenario-TC-02').focus()
  await page.keyboard.press('Space')
  await expect(page.getByTestId('refined-agent')).toContainText('Please focus on driving.')
  await page.getByLabel('Caller confirmation', { exact: true }).focus()
  await page.keyboard.press('ControlOrMeta+A')
  await page.keyboard.insertText('Yes, please book it.')
  const confirmation = page.getByRole('button', { name: 'Simulate caller confirmation', exact: true })
  await confirmation.focus()
  expect(await confirmation.evaluate((element) => getComputedStyle(element).transitionDuration)).toBe('0s')
  await page.keyboard.press('Space')
  await expect(page.getByTestId('slot-wed-1630')).toContainText('BOOKED_BY_AGENT')
  await page.getByTestId('baseline-agent').getByText('MOCK DATABASE & TOOL LOG', { exact: true }).click()
  await expectContainedViewport(page)
})

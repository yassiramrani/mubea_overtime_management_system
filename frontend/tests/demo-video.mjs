import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const baseUrl = process.env.DEMO_URL || 'http://127.0.0.1:3109'
const password = process.env.DEMO_PASSWORD || 'DemoPass-2026'
const output = resolve(process.env.DEMO_VIDEO_DIR || '/tmp/overtime-demo-recording')
mkdirSync(output, { recursive: true })

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: output, size: { width: 1440, height: 900 } },
})
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))

const pause = (milliseconds = 1200) => page.waitForTimeout(milliseconds)
const caption = async (text) => {
  await page.evaluate((label) => {
    document.getElementById('demo-caption')?.remove()
    const node = document.createElement('div')
    node.id = 'demo-caption'
    node.textContent = label
    Object.assign(node.style, {
      position: 'fixed', top: '24px', left: '24px', zIndex: '99999',
      padding: '10px 16px', borderRadius: '999px', color: '#fff',
      background: 'rgba(15, 23, 42, .9)', font: '600 16px system-ui, sans-serif',
      boxShadow: '0 8px 24px rgba(15, 23, 42, .2)', letterSpacing: '.01em',
    })
    document.body.appendChild(node)
  }, text)
  await pause()
}

const login = async (username, roleLabel) => {
  await page.goto(`${baseUrl}/login`)
  await page.getByLabel('Username', { exact: true }).fill(username)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Continue to dashboard' }).click()
  await page.waitForURL(/\/(dept|head|hr)-manager$/)
  await caption(roleLabel)
}

const logout = async () => {
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.waitForURL('**/login')
  await pause(500)
}

try {
  await login('smoke-dept', '1 / 5  ·  Department manager')
  await page.getByRole('heading', { name: 'Plan overtime for Logistics' }).waitFor()
  await pause(900)
  await page.getByRole('button', { name: 'New overtime request' }).click()
  await caption('1 / 5  ·  Create an advance overtime request')
  await page.getByLabel('Request title', { exact: true }).fill('October inventory overtime')
  await page.getByLabel('Start date', { exact: true }).fill('2026-10-10')
  await page.getByLabel('End date', { exact: true }).fill('2026-10-10')
  await page.getByLabel('Total employee-hours', { exact: true }).fill('15')
  await page.getByLabel('Estimated rate per employee-hour (optional)').fill('25')
  await page.getByLabel('Work description', { exact: true }).fill('Count stock before the warehouse opens.')
  await page.getByLabel('Why is overtime needed?').fill('Complete the count before the scheduled delivery.')
  await page.getByRole('button', { name: 'Submit for approval' }).scrollIntoViewIfNeeded()
  await pause(800)
  await page.getByRole('button', { name: 'Submit for approval' }).click()
  await page.getByRole('heading', { name: 'October inventory overtime', exact: true }).waitFor()
  await caption('Request submitted  ·  awaiting head-manager approval')
  await pause(1400)
  await logout()

  await login('smoke-head', '2 / 5  ·  Head manager approval queue')
  await page.getByRole('heading', { name: 'October inventory overtime', exact: true }).waitFor()
  await pause(1600)
  await page.getByRole('button', { name: 'Approve request', exact: true }).click()
  await page.getByText('No requests match this status.').waitFor()
  await caption('Request approved  ·  HR can now assign employees')
  await pause(1400)
  await logout()

  await login('smoke-hr', '3 / 5  ·  HR assignment workspace')
  await page.getByRole('button', { name: 'Assign employees', exact: true }).click()
  await caption('3 / 5  ·  Assign named employees')
  await page.getByRole('checkbox', { name: 'Employee 00', exact: true }).check()
  await pause(900)
  await page.getByRole('button', { name: 'Save assignment', exact: true }).click()
  await page.getByRole('button', { name: 'Edit employee assignment', exact: true }).waitFor()
  await caption('Assignment saved  ·  ready for export')
  await pause(1300)
  await page.getByRole('checkbox', { name: 'Select October inventory overtime for export' }).check()
  await page.getByRole('button', { name: 'Preview selected export' }).click()
  await page.getByRole('heading', { name: 'Review the selected export' }).waitFor()
  await caption('4 / 5  ·  Review the SAP-ready CSV preview')
  await pause(1800)
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Create batch and download' }).click()
  await downloaded
  await page.getByText('File generated; import unconfirmed', { exact: false }).waitFor()
  await caption('Export batch created  ·  original file is saved for re-download')
  await pause(1600)
  await logout()

  await login('smoke-dept', '5 / 5  ·  Department manager confirmation')
  await page.getByText('Assigned employees: Employee 00', { exact: false }).waitFor()
  await caption('Workflow complete  ·  assignment visible to the requester')
  await pause(2200)
  assert.deepEqual(errors, [], 'Browser runtime errors')
} finally {
  await page.close()
  await context.close()
  await browser.close()
}

console.log('Demo recording created in', output)

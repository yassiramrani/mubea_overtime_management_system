import { chromium } from 'playwright'
import { spawn, execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { randomBytes } from 'node:crypto'
import assert from 'node:assert/strict'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const backend = resolve(frontend, '../backend')
const temp = mkdtempSync(resolve(tmpdir(), 'overtime-smoke-'))
const output = process.env.SMOKE_OUTPUT || resolve(temp, 'artifacts')
mkdirSync(output, { recursive: true })
const python = process.env.SMOKE_PYTHON || resolve(backend, process.platform === 'win32' ? 'venv/Scripts/python.exe' : 'venv/bin/python')
const password = randomBytes(18).toString('hex')
const env = { ...process.env, PYTHONPATH: backend, DJANGO_SETTINGS_MODULE: 'core.settings', DEBUG: 'True',
  SECRET_KEY: randomBytes(40).toString('hex'), DB_ENGINE: 'django.db.backends.sqlite3', DB_NAME: resolve(temp, 'db.sqlite3'),
  EMAIL_BACKEND: 'django.core.mail.backends.locmem.EmailBackend', REDIS_URL: '', ALLOWED_HOSTS: 'localhost,127.0.0.1',
  SMOKE_PASSWORD: password, PUBLIC_BASE_URL: 'http://127.0.0.1:3109', VITE_API_URL: '/api', VITE_API_PROXY: 'http://127.0.0.1:8009' }
execFileSync(python, [resolve(frontend, 'tests/seed_smoke.py')], { cwd: backend, env, stdio: 'pipe' })
const servers = [spawn(python, ['manage.py', 'runserver', '127.0.0.1:8009', '--noreload'], { cwd: backend, env }),
  spawn(process.execPath, [resolve(frontend, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '3109', '--strictPort'], { cwd: frontend, env })]
let serverLog = ''
for (const server of servers) {
  server.stdout.on('data', data => { serverLog += data })
  server.stderr.on('data', data => { serverLog += data })
}
let browser
const errors = []
try {
  for (const url of ['http://127.0.0.1:8009/health/', 'http://127.0.0.1:3109']) {
    let ready = false
    for (let attempt = 0; attempt < 60; attempt++) {
      try { if ((await fetch(url)).ok) { ready = true; break } } catch {}
      await new Promise(resolve => setTimeout(resolve, 250))
    }
    assert(ready, `Server unavailable: ${url}`)
  }
  browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  const login = async (name) => {
    await page.goto('http://127.0.0.1:3109/login')
    await page.getByLabel('Username', { exact: true }).fill(name)
    await page.getByLabel('Password', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Continue to dashboard' }).click()
    await page.waitForURL(/\/(dept|head|hr)-manager$/)
  }
  const logout = async () => {
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await page.waitForURL('**/login')
  }
  await page.goto('http://127.0.0.1:3109/login')
  await page.getByLabel('Username', { exact: true }).fill('smoke-dept')
  await page.getByLabel('Password', { exact: true }).fill('incorrect-test-password')
  await page.getByLabel('Show password', { exact: true }).check()
  assert.equal(await page.getByLabel('Password', { exact: true }).getAttribute('type'), 'text')
  await page.getByLabel('Show password', { exact: true }).uncheck()
  await page.getByRole('button', { name: 'Continue to dashboard' }).click()
  await page.locator('.login-error').waitFor()
  assert.equal(await page.getByLabel('Username', { exact: true }).inputValue(), 'smoke-dept', 'Login failure preserves entered username')
  await page.screenshot({ path: resolve(output, 'login-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'login-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Login must fit mobile width')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await login('smoke-dept')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await page.getByText('23 records · Page 2').waitFor()
  await page.getByLabel('Find a request', { exact: true }).fill('Historical approval request 00')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByText('1 record · Page 1').waitFor()
  await page.getByRole('heading', { name: 'Historical approval request 00', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await page.getByText('23 records · Page 1').waitFor()
  await page.getByLabel('Sort by', { exact: true }).selectOption('created_at')
  await page.locator('.request-row h3').first().filter({ hasText: 'Historical approval request 00' }).waitFor()
  await page.route('**/api/requests/?*', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Temporary maintenance. Try again.' }) }), { times: 1 })
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await page.getByText('Temporary maintenance. Try again.', { exact: true }).waitFor()
  await page.getByText('0 records · Page 1').waitFor()
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await page.getByText('23 records · Page 1').waitFor()
  await page.getByRole('button', { name: 'New overtime request' }).click()
  await page.getByLabel('Request title', { exact: true }).fill('October inventory overtime')
  await page.getByLabel('Start date', { exact: true }).fill('2026-10-10')
  await page.getByLabel('End date', { exact: true }).fill('2026-10-10')
  await page.getByLabel('Total employee-hours', { exact: true }).fill('15')
  await page.getByLabel('Estimated rate per employee-hour (optional)').fill('25')
  await page.getByText('15 employee-hours · Estimated total: 375.00', { exact: true }).waitFor()
  await page.getByLabel('Work description', { exact: true }).fill('Count stock before the warehouse opens.')
  await page.getByLabel('Why is overtime needed?').fill('Complete the count before the scheduled delivery.')
  await page.getByRole('button', { name: 'Submit for approval' }).click()
  await page.getByRole('heading', { name: 'October inventory overtime', exact: true }).waitFor()
  await page.reload()
  await page.getByRole('heading', { name: 'Plan overtime for Logistics' }).waitFor()
  assert(page.url().endsWith('/dept-manager'), 'Reload should preserve the authenticated route')
  await logout()
  await login('smoke-head')
  await page.getByRole('heading', { name: 'October inventory overtime', exact: true }).waitFor()
  await page.getByLabel('Department', { exact: true }).selectOption('quality')
  await page.getByText('No requests match your filters. Try another status or clear the filters.').waitFor()
  await page.getByLabel('Department', { exact: true }).selectOption('logistics')
  await page.getByRole('heading', { name: 'October inventory overtime', exact: true }).waitFor()
  await page.screenshot({ path: resolve(output, 'head-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'head-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Head dashboard must fit mobile width')
  await page.getByRole('button', { name: 'Approve request', exact: true }).click()
  await page.getByText('No requests match your filters. Try another status or clear the filters.').waitFor()
  await logout()
  await login('smoke-hr')
  await page.getByRole('button', { name: 'Assign employees', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Employee 00', exact: true }).check()
  await page.getByRole('button', { name: 'Save assignment', exact: true }).click()
  await page.getByRole('button', { name: 'Edit employee assignment', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Edit employee assignment', exact: true }).click()
  assert(await page.getByRole('checkbox', { name: 'Employee 00', exact: true }).isChecked(), 'Saved assignments should load')
  await page.getByRole('button', { name: 'Close editor' }).click()
  await page.getByRole('checkbox', { name: 'Select October inventory overtime for export' }).check()
  await page.getByText('Selected for export · 15 employee-hours', { exact: true }).waitFor()
  await page.getByLabel('Department', { exact: true }).selectOption('quality')
  await page.getByText('No approved requests match your filters. Clear the filters or check again after a request is approved.').waitFor()
  await page.getByRole('button', { name: 'Remove October inventory overtime from export', exact: true }).click()
  assert(await page.getByRole('button', { name: 'Preview selected export' }).isDisabled(), 'Removing a hidden selection disables export')
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Select October inventory overtime for export' }).check()
  await page.getByRole('button', { name: 'Preview selected export' }).click()
  await page.getByRole('heading', { name: 'Review the selected export' }).waitFor()
  assert((await page.getByLabel('CSV export preview').innerText()).includes('15.00'))
  await page.screenshot({ path: resolve(output, 'hr-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'HR dashboard must fit mobile width')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: resolve(output, 'hr-desktop.png'), fullPage: true })
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Create batch and download' }).click()
  const download = await downloaded
  await download.saveAs(resolve(output, 'advance-approval.csv'))
  await page.getByText('File generated; import unconfirmed', { exact: false }).waitFor()
  await page.getByRole('button', { name: 'Download saved file' }).waitFor()
  await logout()
  await login('smoke-dept')
  await page.getByText('Assigned employees: Employee 00', { exact: false }).waitFor()
  await page.screenshot({ path: resolve(output, 'department-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(output, 'department-mobile.png'), fullPage: true })
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Department dashboard must fit mobile width')
  assert.deepEqual(errors, [], 'Browser runtime errors')
  console.log(`Browser workflow passed. Artifacts: ${output}`)
} finally {
  await browser?.close()
  for (const server of servers) server.kill('SIGTERM')
  writeFileSync(resolve(output, 'servers.log'), serverLog)
}

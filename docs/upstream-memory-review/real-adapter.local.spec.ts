// LOCAL ONLY, not part of the upstream change: the same flow as memory-checkup.spec.ts, over a home that
// docs/upstream-memory-review/seed_demo_home.py (hermes-optimization) filled through the real holographic and
// holographic-semantic plugins. It exists to take screenshots of the real adapter in the real app.
import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as http from 'node:http'
import type { AddressInfo } from 'node:net'
import * as path from 'node:path'

import type { Page } from '@playwright/test'

import { writeEnvFile, writeMockProviderConfig } from '../../../tests-js/scripts/mock-provider-config'
import { startMockServer } from '../../../tests-js/scripts/mock-server'

import { buildAppEnv, createSandbox, launchDesktop, type MockBackendFixture, waitForAppReady } from './fixtures'
import { startLiveSidecar } from './real-sidecar-fixture'
import { expect, test } from './test'

const REPO = path.resolve(import.meta.dirname, '..', '..', '..')
const PROJECT = process.env.HERMES_OPTIMIZATION_ROOT!
const OUT = process.env.MEMORY_REVIEW_SHOTS!
// The test kit (testkit/run.py) passes all three; the fallbacks are the original local setup on Windows.
const HOLOGRAPHIC = process.env.HOLOGRAPHIC_SRC ?? path.join(PROJECT, 'vendor', 'holographic-0.30.0')
const PYTHON = process.env.SEED_PYTHON ?? path.join(REPO, '.venv', 'Scripts', 'python.exe')
const SIDECAR_PYTHON = process.env.MEMORY_REVIEW_SIDECAR_PYTHON
const BGE_MODEL = process.env.MEMORY_REVIEW_BGE_MODEL_DIR
const REAL_SIDECAR = !!SIDECAR_PYTHON && !!BGE_MODEL
if (!!SIDECAR_PYTHON !== !!BGE_MODEL) throw new Error('Real sidecar needs both the interpreter and the model directory')

function seedHome(sandbox: { hermesHome: string; root: string }, ...extra: string[]) {
  execFileSync(
    PYTHON,
    [
      path.join(PROJECT, 'docs', 'upstream-memory-review', 'seed_demo_home.py'),
      '--base',
      HOLOGRAPHIC,
      '--adapter',
      path.join(PROJECT, 'memory', 'plugin', 'holographic-semantic'),
      ...extra
    ],
    {
      cwd: REPO,
      env: {
        ...process.env,
        HERMES_HOME: sandbox.hermesHome,
        HOME: sandbox.root,
        USERPROFILE: sandbox.root,
        PYTHONPATH: [REPO, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)
      }
    }
  )
}

function reviewReply(prompt: string): string {
  const ref = (text: string) =>
    prompt
      .split('\n')
      .find(line => line.endsWith(`: ${text}`))!
      .split(/[ :]/)[0]

  return JSON.stringify({
    proposals: [
      {
        target: ref('The billing service database is Postgres'),
        action: 'remove',
        basis: 'duplicate',
        with: [ref('The billing service database is PostgreSQL 16 on RDS')],
        evidence: 'The newer fact says the same and adds the version and where it runs.',
        preserve: ''
      },
      {
        target: ref('Works at Acme on the billing service'),
        action: 'needs_evidence',
        basis: 'unverified',
        evidence: 'Nothing else here confirms the team is current. Ask the user.'
      },
      {
        target: ref('The staging cluster was renamed from orchid to iris in October'),
        action: 'update',
        basis: 'outdated',
        evidence: 'The rename is done; the fact still reads as an event.',
        preserve: 'The old name, orchid, for older notes.',
        new_text: 'The staging cluster is called iris (formerly orchid)'
      },
      {
        target: ref('The user is trying out the Zed editor this week'),
        action: 'remove',
        basis: 'outdated',
        evidence: 'It says "this week".'
      },
      { target: ref('Never deploy on Fridays'), action: 'remove', basis: 'unused', evidence: 'Never recalled.' },
      {
        target: ref('The user probably prefers tabs over spaces'),
        action: 'remove',
        basis: 'unused',
        evidence: 'Never recalled in 150 days.'
      }
    ]
  })
}

const openRoute = (page: Page, route: string) => page.evaluate(hash => void (window.location.hash = hash), `#${route}`)

test('screenshots of the real adapter', async () => {
  test.setTimeout(300_000)

  const mock = await startMockServer({
    replyForPrompt: prompt => (prompt.includes('Find entries that are stale') ? reviewReply(prompt) : 'ok')
  })

  const sandbox = createSandbox('memory-checkup-real')

  seedHome(sandbox)
  writeMockProviderConfig(sandbox.hermesHome, mock.url, 'language: en\n')
  writeEnvFile(sandbox.hermesHome)

  const { app, page } = await launchDesktop(buildAppEnv(sandbox))

  const fixture: MockBackendFixture = {
    app,
    page,
    mock,
    mockUrl: mock.url,
    sandbox,
    cleanup: async () => {
      await app.close().catch(() => undefined)
      await mock.close()
      sandbox.cleanup()
    }
  }

  try {
    await waitForAppReady(fixture)
    await page.getByRole('button', { name: 'No thanks' }).click()
    await openRoute(page, '/command-center?section=maintenance')
    await page.getByTestId('memory-checkup').getByRole('switch', { name: 'Remind me to review' }).click()
    await page.evaluate(() => {
      const key = Object.keys(window.localStorage).find(name => name.startsWith('hermes:memory-checkup-reminder:'))!
      const stored = JSON.parse(window.localStorage.getItem(key)!)

      window.localStorage.setItem(key, JSON.stringify({ ...stored, dueAt: Date.now() - 86_400_000 }))
    })
    await openRoute(page, '/')
    await page.reload()
    await waitForAppReady(fixture)

    const strip = page.locator('[data-slot="status-row"]').filter({ hasText: 'Memory checkup' })

    await expect(strip).toHaveCount(1)
    fs.mkdirSync(OUT, { recursive: true })
    await page.screenshot({ path: path.join(OUT, '1-reminder.png') })

    const dbBefore = fs.readFileSync(path.join(sandbox.hermesHome, 'memory_store.db'))

    await strip.getByRole('button', { name: 'Review now' }).click()

    const capacity = page.getByTestId('memory-capacity')
    const results = page.getByTestId('memory-checkup-results')

    await expect(results).toBeVisible({ timeout: 120_000 })
    await expect(capacity.getByText(/12 active facts/)).toBeVisible()
    await page.getByTestId('memory-layers').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(OUT, '2-capacity.png') })
    await results.scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(OUT, '3-proposals.png') })
    await page.getByTestId('memory-checkup-facts').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(OUT, '4-facts.png') })

    // The gateway had this store open the whole time; the checkup read it and changed nothing.
    expect(fs.readFileSync(path.join(sandbox.hermesHome, 'memory_store.db')).equals(dbBefore)).toBe(true)
  } finally {
    await fixture.cleanup()
  }
})

// The sidecar's two routes the index job uses, over a store of `total` facts, five facts a batch. A stand-in for the
// bge-m3 sidecar (memory/sidecar), whose own sync has its self-check there: the model is the one thing not real here.
function fakeSidecar(total: number): Promise<{ url: string; close: () => Promise<void> }> {
  let indexed = 0

  const server = http.createServer((req, res) => {
    const send = (body: unknown) => {
      res.setHeader('Content-Type', 'application/json')
      res.end(JSON.stringify(body))
    }

    if (req.method === 'GET' && req.url === '/health') {
      return send({ ok: true, model: 'bge-m3', device: 'cpu', facts_indexed: indexed, facts: total, error: '' })
    }

    req.resume()
    req.on('end', () => {
      const embedded = Math.min(5, total - indexed)

      indexed += embedded
      send({ embedded, remaining: total - indexed, facts: total, facts_indexed: indexed })
    })
  })

  return new Promise(resolve =>
    server.listen(0, '127.0.0.1', () =>
      resolve({
        url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
        close: () => new Promise(done => server.close(() => done()))
      })
    )
  )
}

test('the adapter: its settings, its index job and the MEMORY.md suggestion', async () => {
  test.setTimeout(REAL_SIDECAR ? 420_000 : 300_000)
  const sandbox = createSandbox('memory-provider-jobs-real')
  const options = {
    root: sandbox.root, home: sandbox.hermesHome, project: PROJECT, out: OUT,
    python: SIDECAR_PYTHON!, model: BGE_MODEL!,
  }
  let mock: Awaited<ReturnType<typeof startMockServer>> | undefined
  let real: Awaited<ReturnType<typeof startLiveSidecar>> | undefined
  let restarted: Awaited<ReturnType<typeof startLiveSidecar>> | undefined
  let sidecar: Awaited<ReturnType<typeof fakeSidecar>> | undefined
  let launched: Awaited<ReturnType<typeof launchDesktop>> | undefined
  try {
    fs.mkdirSync(OUT, { recursive: true })
    mock = await startMockServer({ replyForPrompt: () => 'ok' })
    if (REAL_SIDECAR) real = await startLiveSidecar(options)
    sidecar = real ?? await fakeSidecar(12)
    seedHome(sandbox, '--memory-md', 'on', '--sidecar', sidecar.url)
    writeMockProviderConfig(sandbox.hermesHome, mock.url, 'language: en\n')
    writeEnvFile(sandbox.hermesHome)
    launched = await launchDesktop(buildAppEnv(sandbox, { USERPROFILE: sandbox.root }))
    const { app, page } = launched
    await waitForAppReady({ app, page, mock, mockUrl: mock.url, sandbox, cleanup: async () => {} })
    await page.getByRole('button', { name: 'No thanks' }).click()

    // Configure, then index what is already stored, from the provider's own settings.
    await openRoute(page, '/settings?tab=config:memory')
    await expect(page.getByText('Holographic + semantic recall settings')).toBeVisible({ timeout: 60_000 })

    const jobs = page.getByTestId('provider-jobs')

    await expect(jobs.getByText('0 of 12 facts indexed (bge-m3 on cpu).')).toBeVisible()
    const started = Date.now()
    await jobs.getByRole('button', { name: 'Run' }).click()

    const output = page.getByTestId('provider-job-output')

    await expect(output.getByRole('status')).toHaveText('Finished.', { timeout: 120_000 })
    await expect(output).toContainText('All 12 facts are indexed; this run embedded 12.')
    await expect(jobs.getByText('12 of 12 facts indexed (bge-m3 on cpu).')).toBeVisible()
    const runMs = Date.now() - started
    await output.scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(OUT, '5-provider-job.png') })

    if (real) {
      // Check persisted arrays before any endpoint that could do an implicit sync.
      const evidence = real.readIndex()
      await jobs.getByRole('button', { name: 'Run' }).click()
      await expect(output).toContainText('All 12 facts are indexed; this run embedded 0.', { timeout: 30_000 })
      await real.close()
      restarted = await startLiveSidecar(options)
      expect(await restarted.health()).toMatchObject({ facts: 12, facts_indexed: 12, model: 'bge-m3', device: 'cpu' })
      expect(restarted.readIndex()).toEqual(evidence)
      const receipt = { model: 'BAAI/bge-m3', device: 'cpu', before: 0, ...evidence, embeddedOnRepeat: 0,
        indexedAfterSidecarRestart: 12, runMs }
      fs.writeFileSync(path.join(OUT, 'real-sidecar.json'), JSON.stringify(receipt, null, 2) + '\n')
      console.log('Real BGE-M3:', JSON.stringify(receipt))
    }

    // MEMORY.md on beside the catalog: optional, with what it costs a session, and nothing is switched off.
    await openRoute(page, '/command-center?section=maintenance')

    const hint = page.getByTestId('memory-capacity').getByText('MEMORY.md is optional while Fact catalog is on')

    await expect(hint).toBeVisible({ timeout: 60_000 })
    await hint.scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(OUT, '6-catalog-suggestion.png') })
    expect(fs.readFileSync(path.join(sandbox.hermesHome, 'config.yaml'), 'utf8')).toContain('memory_enabled: true')
  } finally {
    await launched?.app.close().catch(() => undefined)
    await restarted?.close()
    await sidecar?.close()
    await mock?.close()
    sandbox.cleanup()
  }
})

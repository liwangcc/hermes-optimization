// Local test helper, not part of the upstream patches. Launches the shipped offline sidecar on a fresh loopback port.
import { execFileSync, spawn } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'

interface SidecarOptions {
  root: string
  home: string
  project: string
  out: string
  python: string
  model: string
}

export async function startLiveSidecar({ root, home, project, out, python, model }: SidecarOptions) {
  const db = path.join(home, 'memory_store.db')
  const cache = path.join(root, 'vectors')
  const log = path.join(out, 'real-sidecar.log')
  const env: NodeJS.ProcessEnv = {}
  for (const key of ['PATH', 'SystemRoot', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH']) {
    if (process.env[key]) env[key] = process.env[key]
  }
  Object.assign(env, {
    HOME: root, USERPROFILE: root, USERNAME: 'hermes-memory-review',
    HF_HOME: path.join(root, 'hf-home'), TORCH_HOME: path.join(root, 'torch-home'),
    TORCHINDUCTOR_CACHE_DIR: path.join(root, 'torchinductor'), HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1',
    // Windows drops an empty environment value; use CUDA's explicit no-device mask.
    CUDA_VISIBLE_DEVICES: '-1', OMP_NUM_THREADS: '2', MKL_NUM_THREADS: '2',
    SEMANTIC_PORT: '0', SEMANTIC_DB: db, SEMANTIC_CACHE: cache, SEMANTIC_MODEL: model,
  })
  const proc = spawn(python, ['-I', '-B', '-u', path.join(project, 'memory', 'sidecar', 'server.py')], {
    cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
  })
  let text = ''
  let closed = false
  const done = new Promise<void>(resolve => proc.once('close', () => { closed = true; resolve() }))
  const append = (chunk: string) => { text += chunk; fs.appendFileSync(log, chunk) }
  proc.on('error', error => append(`Failed to start sidecar: ${error.message}\n`))
  proc.stdout.setEncoding('utf8').on('data', append)
  proc.stderr.setEncoding('utf8').on('data', append)
  const close = async () => {
    if (!closed) proc.kill('SIGKILL')
    await done
  }
  try {
    const deadline = Date.now() + 120_000
    while (!closed && Date.now() < deadline) {
      const port = text.match(/listening on 127\.0\.0\.1:(\d+)/)?.[1]
      if (port) {
        const url = `http://127.0.0.1:${port}`
        const health = async () => {
          const response = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) })
          if (!response.ok) throw new Error(`sidecar health HTTP ${response.status}`)
          const result = await response.json()
          if (!result.ok) throw new Error(`sidecar did not load its model: ${result.error}`)
          return result
        }
        await health()
        const readIndex = () => JSON.parse(execFileSync(python, [
          '-I', '-B', path.join(project, 'docs', 'upstream-memory-review', 'check_demo_index.py'), db, cache,
        ], { cwd: root, env, encoding: 'utf8', timeout: 30_000 }))
        return { url, close, health, readIndex }
      }
      await new Promise(resolve => setTimeout(resolve, 200))
    }
    throw new Error('Real sidecar exited or did not listen before the deadline; see screenshots/real-sidecar.log')
  } catch (error) {
    await close()
    throw error
  }
}

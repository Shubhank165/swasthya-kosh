/**
 * The end-to-end journey — 3/3 §11 item 7.
 *
 * Against the **real backend**: `scripts/e2e_backend.py` starts the actual
 * application on a throwaway SQLite file with two seeded intakes, one of which
 * fired a red-flag criterion. A journey run against a hand-written stub proves
 * that the stub matches the test's idea of the API, which is not the thing
 * worth knowing.
 *
 * One browser. This is a desktop screen on a hospital terminal; a matrix across
 * three engines would cost minutes per run and defend nothing the project has
 * claimed.
 */
import { defineConfig, devices } from '@playwright/test';

const API_PORT = 8123;
const WEB_PORT = 4173;
const PYTHON = process.env.MEDIKIOSK_PYTHON ?? '../backend/.venv/bin/python';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  // A journey that only passes on the second attempt has found something. It
  // is not retried into looking green.
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? 'list' : 'line',
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${PYTHON} scripts/e2e_backend.py --port ${API_PORT} --db /tmp/medikiosk-e2e.sqlite`,
      cwd: '../backend',
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: 90_000,
    },
    {
      // `vite dev` rather than a preview of the build: the dev server's proxy
      // is what makes `/api` and `/ws` same-origin, which is how the real
      // deployment serves them and what keeps the refresh cookie first-party.
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      env: { MEDIKIOSK_API: `http://127.0.0.1:${API_PORT}` },
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});

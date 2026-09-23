import { defineConfig, devices } from '@playwright/test';

const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3100);
const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);
const BASE_URL = `http://127.0.0.1:${WEB_PORT}`;
const API_URL = `http://127.0.0.1:${API_PORT}`;

/**
 * End-to-end tests run the real stack: the FastAPI service with its mock
 * inventory fixtures, and the Next.js app against it. No Redis or Postgres is
 * required. A dedicated SQLite file holds test inventory; ingestion is disabled.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    {
      command: `.venv/bin/python -m tests.e2e_server --port ${API_PORT}`,
      cwd: '../api',
      url: `${API_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        APP_ENV: 'test',
        REDIS_URL: '',
        DATABASE_URL: 'sqlite+aiosqlite:///./e2e.sqlite3',
        INGESTION_ENABLED: 'false',
        ANTHROPIC_API_KEY: '',
        RATE_LIMIT_ENABLED: 'false',
        LOG_LEVEL: 'WARNING',
        CORS_ALLOW_ORIGINS: BASE_URL,
      },
    },
    {
      command: `npm run build && npm run start -- --port ${WEB_PORT}`,
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_BASE_URL: API_URL },
    },
  ],
});

// Headless browser tests for the ui.command pipeline (no real LiveKit).
// Run:  npx playwright test   (from frontend/)
// Uses system Chrome (channel: 'chrome') — no browser download needed.
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    channel: 'chrome',
    headless: true,
    baseURL: 'http://localhost:5173',
  },
  webServer: {
    command: 'npm run dev -- --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
    env: { VITE_AUTH_DISABLED: 'true' },
  },
});

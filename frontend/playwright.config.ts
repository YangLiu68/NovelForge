import { defineConfig, devices } from "@playwright/test";

// Ports chosen to avoid clashing with a dev server already running on 8000/5173.
const API_PORT = Number(process.env.E2E_API_PORT ?? 18765);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 15199);

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  workers: 1, // the tests share one freshly created database
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Drops and recreates the `novelforge_e2e` database, migrates it, then serves the API.
      command: `uv run novelforge e2e-server --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { NOVELFORGE_API_URL: `http://127.0.0.1:${API_PORT}` },
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});

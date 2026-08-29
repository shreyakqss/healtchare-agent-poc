import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const repositoryRoot = path.resolve(__dirname, "..");
const backendRoot = path.join(repositoryRoot, "backend");
const python = process.platform === "win32"
  ? path.join(backendRoot, "venv", "Scripts", "python.exe")
  : path.join(backendRoot, "venv", "bin", "python");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" scripts/migrate.py && "${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`,
      cwd: backendRoot,
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        DATABASE_URL:
          process.env.E2E_DATABASE_URL
          ?? process.env.DATABASE_URL
          ?? "postgresql://postgres:postgres@localhost:5432/healthcare_agent",
        AUTH_MODE: "oidc",
        AUTH_SESSION_SECRET: "careflow-e2e-session-key-not-for-production",
        AUTH_COOKIE_SECURE: "False",
        DEBUG: "False",
        OPENAI_API_KEY: "",
        OPENEMR_BASE_URL: "http://127.0.0.1:9",
        OPENEMR_TOKEN_URL: "http://127.0.0.1:9/oauth2/default/token",
        RATE_LIMITING_ENABLED: "False",
        WORKFLOW_WORKER_ENABLED: "False",
      },
    },
    {
      command: "node node_modules/next/dist/bin/next start",
      cwd: __dirname,
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: { ...process.env, BACKEND_URL: "http://localhost:8000" },
    },
  ],
});

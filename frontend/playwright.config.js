// Playwright smoke suite for the storefront.
//
//   npx playwright test            (from frontend/, with the backend virtualenv activated)
//
// It starts its own backend and frontend on spare ports, against a throwaway SQLite database
// (backend/e2e.sqlite3, recreated on every run and git-ignored) seeded by `seed_noore`.
// Your real db.sqlite3 and your running dev servers are never touched.
//
// The backend is started with whatever `python` is on PATH, so activate the virtualenv first
// (backend\venv\Scripts\Activate.ps1), or set E2E_PYTHON to the interpreter to use.
import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(here, '..', 'backend');
const databaseFile = path.join(backendDir, 'e2e.sqlite3');

const API_PORT = Number(process.env.E2E_API_PORT || 8011);
const WEB_PORT = Number(process.env.E2E_WEB_PORT || 5183);
const PYTHON = process.env.E2E_PYTHON || 'python';
const py = PYTHON.includes(' ') ? `"${PYTHON}"` : PYTHON;

// A fresh database for every run. Workers load this file too; only the runner may delete.
if (process.env.TEST_WORKER_INDEX === undefined && !process.env.E2E_BASE_URL) {
    fs.rmSync(databaseFile, { force: true });
}

// sqlite:///C:/path/e2e.sqlite3 on Windows, sqlite:////home/.../e2e.sqlite3 elsewhere.
const databaseUrl = `sqlite:///${encodeURI(databaseFile.replace(/\\/g, '/'))}`;

// Set E2E_BASE_URL to check a DEPLOYED site instead (e.g. https://shop.example.in). Then no
// local servers are started and only e2e/production.spec.js runs: it needs no seed data and
// places one Cash on Delivery order, which you then cancel in "Handle orders".
const DEPLOYED_URL = (process.env.E2E_BASE_URL || '').replace(/\/$/, '');

export default defineConfig({
    testDir: './e2e',
    testMatch: DEPLOYED_URL ? 'production.spec.js' : ['storefront.spec.js', 'checkout.spec.js', 'brand.spec.js'],
    timeout: 60_000,
    expect: { timeout: 10_000 },
    fullyParallel: false,
    workers: 1,
    retries: 0,
    reporter: [['list']],
    use: {
        baseURL: DEPLOYED_URL || `http://localhost:${WEB_PORT}`,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
    webServer: DEPLOYED_URL ? undefined : [
        {
            command: `${py} manage.py migrate --noinput && ${py} manage.py seed_e2e && ${py} manage.py seed_noore && ${py} manage.py runserver 127.0.0.1:${API_PORT} --noreload`,
            cwd: backendDir,
            url: `http://127.0.0.1:${API_PORT}/api/v1/addon/`,
            reuseExistingServer: false,
            timeout: 180_000,
            env: {
                ...process.env,
                DATABASE_URL: databaseUrl,
                DJANGO_DEBUG: 'True',
                DJANGO_ALLOWED_HOSTS: '127.0.0.1,localhost',
                CORS_ALLOWED_ORIGINS: `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}`,
                SITE_URL: `http://localhost:${WEB_PORT}`,
                DJANGO_EMAIL_BACKEND: 'django.core.mail.backends.locmem.EmailBackend',
                LOG_LEVEL: 'WARNING',
                ENABLED_PAYMENT_PROVIDERS: 'razorpay,cod',
                // The suite signs in several times and checks out repeatedly; do not rate-limit it.
                THROTTLE_AUTH: '1000/min',
                THROTTLE_CHECKOUT: '1000/min',
            },
        },
        {
            command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
            cwd: here,
            url: `http://localhost:${WEB_PORT}`,
            reuseExistingServer: false,
            timeout: 120_000,
            env: {
                ...process.env,
                VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}/api/v1/`,
                VITE_SERVER_URL: `http://127.0.0.1:${API_PORT}/`,
            },
        },
    ],
});

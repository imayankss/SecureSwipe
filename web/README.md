# SecureSwipe Web Dashboard

This Next.js application is the deployment-safe presentation layer for the
SecureSwipe fraud-detection project. It renders only aggregate, precomputed
evaluation artifacts from `public/data/dashboard.json`; it does not load Python
models, process transaction rows, or perform live inference.

## Getting Started

From the repository root, refresh and verify the public data:

```bash
python3 scripts/export_web_data.py
python3 scripts/export_web_data.py --check
```

Then install and run the frontend:

```bash
cd web
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Verification

```bash
npm run data:check
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install --no-shell chromium
npm run test:e2e
```

The unit suite checks component interaction and screen-reader contracts in
JSDOM. The Chromium suite starts the production build, verifies keyboard and
mobile navigation, runs a WCAG A/AA Axe scan, and fails if the static dashboard
makes a request to `/v1/predict`. The browser is a local/CI test dependency only;
it is not shipped with the dashboard.

The production dependency audit should also remain clean:

```bash
npm audit --omit=dev
```

## Vercel

Use this folder as the dedicated Vercel project root. Framework detection should
select Next.js, with `npm ci`/the committed lockfile and `npm run build`. The
deployable static configuration requires no environment variables. No live
provider deployment or URL is verified by this repository.

The dashboard includes an optional synthetic API check. It is disabled unless
`NEXT_PUBLIC_SECURESWIPE_API_URL` is set at build time, sends one fixed all-zero
feature vector only after the user clicks the button, and never accepts user
transaction data. Loading, timeout, unavailable, empty, and error responses
keep the static score demonstration visible as the fallback. For example:

```bash
NEXT_PUBLIC_SECURESWIPE_API_URL=http://127.0.0.1:8000 npm run build
```

The API must allow the frontend origin through its explicit CORS configuration.
No live provider deployment or URL is verified by this repository.

See the repository-level README for the full architecture, data refresh,
security, Git, and deployment workflow.

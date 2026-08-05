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
```

The production dependency audit should also remain clean:

```bash
npm audit --omit=dev
```

## Vercel

Use this folder as the dedicated Vercel project root. Framework detection should
select Next.js, with `npm ci`/the committed lockfile and `npm run build`. The
current static deployment requires no environment variables.

See the repository-level README for the full architecture, data refresh,
security, Git, and deployment workflow.

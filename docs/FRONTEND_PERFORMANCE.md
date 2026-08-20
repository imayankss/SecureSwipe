# Static frontend performance budget

This is a measured regression budget for the static dashboard, not a user-facing
latency SLO or a cloud/network capacity claim.

## Baseline

Measured 2026-08-13 from a clean Next.js production build served by `next start`
on `127.0.0.1`, using Node.js 22.13.1 and Playwright Chromium 151 on Apple M2:

| Browser navigation measure | Observed |
|---|---:|
| HTML encoded bytes | 18,519 |
| Script requests | 6 |
| Script encoded bytes | 270,718 |
| Stylesheet requests | 1 |
| Stylesheet encoded bytes | 6,923 |
| Resource requests after navigation | 9 |
| Total encoded bytes including HTML | 329,437 |
| DOM content loaded | 131.5 ms |
| Load event | 172.8 ms |

Encoded sizes come from the browser Performance API after `networkidle`. Timing
is recorded for context only: a local single run is too environment-sensitive
to use as an automated assertion.

## Enforced budget

The production Chromium test fails above these bounded static-asset values:

- at most 8 script requests;
- at most 350,000 encoded script bytes;
- at most 12 total requests including the HTML navigation;
- at most 450,000 total encoded bytes including HTML.

These limits leave approximately 29–37% headroom over the baseline while still
catching material bundle/request growth. A deliberate budget increase requires
a fresh production measurement, explanation of user value, dependency review,
and updated evidence. The same browser gate also enforces WCAG A/AA rules and
zero `/v1/predict` requests, so size optimization cannot bypass accessibility or
the static deployment boundary.

## Reproduce

```bash
cd web
npm ci
npm run build
npx playwright install --no-shell chromium
npm run test:e2e
```

Provider, cache, cold-start, field, and mobile-network timings remain unmeasured.

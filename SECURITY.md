# Security policy

## Scope and support

SecureSwipe is an educational portfolio reference. It is not deployed as a bank
authorization service, has no customer support commitment, and must not process
real cardholder or customer data. Security fixes target the current `main` branch;
historical commits and local model artifacts are not supported releases.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting or Security Advisory interface for
this repository when it is available. If it is unavailable, contact the owner
through the GitHub profile to establish a private channel. Do not publish working
credentials, private transaction data, or exploit details in a public issue, PR,
log, screenshot, or chat message.

Include the affected commit, reproducible synthetic steps, impact, and suggested
mitigation. Never attach a real dataset or unredacted model input.

## Artifact and secret handling

- API callers cannot upload model bytes or paths. Only server-configured bundles
  under a trusted root are considered.
- Joblib/pickle can execute code. Checksums detect replacement but do not make an
  arbitrary artifact safe; accept only locally produced, reviewed bundles.
- `.env*`, Kaggle credentials, CSV/parquet data, and model files are ignored and
  excluded from the container context.
- Suspected credential exposure requires revocation/rotation first, then history
  assessment. Do not merely delete the latest copy.

See `docs/THREAT_MODEL.md` for trust boundaries and residual risks.

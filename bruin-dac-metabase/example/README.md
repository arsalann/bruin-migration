# Runnable Metabase to DAC reference

This example creates an isolated PostgreSQL source and Metabase instance, provisions a native-SQL dashboard through the Metabase API, imports it into DAC, then validates both the generated import and hand-authored reference.

## Prerequisites

- Docker Desktop with Compose v2
- `python3`, `bruin`, and `dac` on `PATH`

Pinned images: PostgreSQL `16.4-alpine` and Metabase `v0.53.8`. All runtime files are written under `.artifacts/`; the Compose file publishes database and UI ports dynamically.

## Commands

```bash
./scripts/bootstrap.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/teardown.sh
```

`bootstrap.sh` starts the source services, waits for Metabase, and writes the dynamically allocated PostgreSQL port to `.artifacts/runtime.env`. `run.sh` uses the Metabase API to create a native SQL question and dashboard, captures `GET /api/dashboard/:id`, and invokes `dac import metabase`. `verify.sh` runs `dac validate`, database-aware `dac check`, and a static `dac build` for both the imported result and target reference.

The generated files to inspect are:

- `.artifacts/metabase-dashboard.json` — captured API response used by the importer.
- `.artifacts/imported-dashboard.yml` — importer output, intentionally ignored.
- `.artifacts/reference-build/` and `.artifacts/imported-build/` — static dashboard artifacts.

For UI-only source features, use [`manual-setup.md`](manual-setup.md) and save any export only under `.artifacts/`.

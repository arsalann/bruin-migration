# Metabase UI fallback

Use this only when the source feature cannot be provisioned through the API (for example, a complex dashboard interaction or visualization setting).

1. Open the local Metabase URL printed by `scripts/bootstrap.sh` and sign in with `fixture@example.test` / `Fixture-Password-2025!`.
2. Add the local PostgreSQL database if it is not already present, then create the required question or dashboard through the UI.
3. Capture the dashboard response, not a screenshot: `curl -H "X-Metabase-Session: <token>" http://127.0.0.1:<port>/api/dashboard/<id> > .artifacts/metabase-dashboard.json`.
4. Run `dac import metabase --input .artifacts/metabase-dashboard.json ...` and review all warnings and the resulting YAML.

Do not commit the captured API response, session token, or any UI export.

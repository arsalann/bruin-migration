# Metabase to DAC

Status: research with runnable reference example.

## What is being migrated

Metabase dashboards are collections of saved questions (cards), layout metadata, dashboard filters, visualization settings, and optional text/link cards. DAC represents the target as version-controlled YAML or TSX dashboard definitions executed through Bruin connections.

The [DAC Metabase importer](https://getbruin.com/docs/dac/commands/import.html) accepts either a saved `GET /api/dashboard/:id` response or a live Metabase instance. It converts native SQL cards into metric, chart, and table widgets. Simple MBQL cards can be compiled when source metadata is available; unsupported cards become text placeholders unless `--strict` is used. DAC maps the dashboard onto a 12-column grid, but Metabase card heights are not currently mapped.

## Source inventory checklist

- Dashboard name, collection, tabs, layout, filters, click behavior, subscriptions, and embedding settings.
- Each card's native SQL or MBQL, source card chain, database/model/table metadata, visualization settings, and template-tag defaults.
- Named Metabase models, metrics, permissions, and connections required by the dashboard.
- Source-specific features DAC cannot represent directly, including UI-only layout behavior or unsupported MBQL.

## Conversion approach

The runnable example provisions a local Metabase instance and PostgreSQL database, creates a native-SQL dashboard through the Metabase API, saves its API response, imports it with `dac import metabase`, then validates the generated dashboard against PostgreSQL. [`example/target/daily-revenue.yml`](example/target/daily-revenue.yml) is the reviewed DAC reference implementation.

Use `--semantic` only when the source has explicit Metabase models and named metrics; dashboard aggregations are deliberately not promoted automatically. Review all importer warnings, optional SQL clauses, filter mappings, chart choices, and layout after import.

## Migration guide with a Metabase URL and API key

This primary workflow assumes you have the Metabase base URL, a dashboard ID, a read-only API key, and a Bruin connection that can query the dashboard's underlying data. It does not require the local reference environment.

1. Make a migration worksheet for one dashboard: record its ID, cards, filters, source databases, and a few expected result values.
2. Note collection, permissions, subscriptions, and embedding separately; these are operating requirements to recreate, not dashboard-definition inputs.
3. Keep the API key outside version control, for example: `export METABASE_API_KEY='<read-only-api-key>'`.
4. Configure a Bruin connection that can execute the cards' source SQL against the intended target data source.
5. Import directly: `dac import metabase --url https://metabase.example.com --dashboard-id 42 --api-key "$METABASE_API_KEY" --connection <bruin-connection> --output dashboards/<dashboard>.yml --force`.
6. Review every importer warning and generated widget; hand-author corrections for SQL, filters, metric semantics, visualization, layout, and any placeholder.
7. Validate and execute the dashboard: `dac validate --dir dashboards`, then `dac check --config bruin.yml --dir dashboards`.
8. Build and review the result with `dac build --config bruin.yml --dir dashboards --dashboard "<dashboard name>" --output build/`; compare its figures to Metabase before publishing.
9. Move the reviewed YAML into version control, deploy it through the target workflow, then separately recreate subscriptions, permissions, embedding, and other UI-only behavior.

After resolving initial findings, use `--strict` in automated imports so unsupported cards or placeholders stop the migration rather than silently reaching review.

### Other supported import methods

- **Session token:** replace `--api-key "$METABASE_API_KEY"` with `--session-token "$METABASE_SESSION_TOKEN"` when your authentication workflow produces a Metabase session token.
- **Saved dashboard response:** capture `GET /api/dashboard/:id` and import it with `dac import metabase --input dashboard.json --connection <bruin-connection> --output dashboards/<dashboard>.yml --force`. Keep the response ignored because it may contain sensitive dashboard metadata.

## Official references

- [Metabase API documentation](https://www.metabase.com/docs/latest/api) — the API is intentionally unversioned and may evolve.
- [Metabase dashboards](https://www.metabase.com/docs/latest/dashboards/introduction) — dashboards compose cards, grid layout, and filters.
- [DAC overview](https://getbruin.com/docs/dac) and [`dac import metabase`](https://getbruin.com/docs/dac/commands/import.html).

## Known gaps and human review

- Review imported MBQL, source-card chains, custom expressions, visualization settings, click behavior, subscriptions, permissions, and embedding.
- Treat Metabase MBQL as opaque during capture; recent Metabase versions changed its serialized form.
- The example's API provisioning covers a native SQL chart. [`example/manual-setup.md`](example/manual-setup.md) records the UI fallback for features API provisioning cannot faithfully create.

## Future automation candidates

- Inventory exporter that records cards, dashboard parameter mappings, metadata, and importer warnings.
- Converter regression tests that compare the captured dashboard response to generated DAC YAML.
- Feature classifier that fails CI when an import emitted placeholders or mapping warnings.

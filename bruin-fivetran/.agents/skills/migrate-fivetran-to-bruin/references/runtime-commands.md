# Runtime command patterns

Use the project’s exact untracked config file where needed. Preserve command
output under `fivetran/.artifacts/<run-id>/run/`, never in tracked files.

## Connection and pipeline gates

```bash
bruin connections test --name fivetran_source --config-file bruin/.bruin.yml
bruin connections test --name bruin_destination --config-file bruin/.bruin.yml
bruin validate bruin/pipeline.yml --config-file bruin/.bruin.yml
```

Run only the user-approved scope. For an initial bounded load, include reviewed
dates; for a one-table test, use the CLI selector supported by the installed
Bruin version rather than assuming the whole pipeline is approved.

```bash
bruin run --full-refresh bruin/pipeline.yml \
  --config-file bruin/.bruin.yml \
  --start-date <approved-start> --end-date <approved-end>
```

## Aggregate comparison and profiling

Use `bruin query` for both source and target. Add `--description` every time.
Adapt SQL syntax to the source/destination dialect, quote identifiers safely,
and compare aggregate results rather than raw rows.

```bash
bruin query --connection fivetran_source \
  --config-file bruin/.bruin.yml \
  --description "profile source orders for migration validation" \
  --query "SELECT COUNT(*) AS row_count, COUNT(DISTINCT order_id) AS distinct_keys, COUNT(*) - COUNT(order_id) AS null_keys, MIN(updated_at) AS min_incremental, MAX(updated_at) AS max_incremental FROM source_schema.orders" \
  --output json > fivetran/.artifacts/<run-id>/run/source-profile.json

bruin query --connection bruin_destination \
  --config-file bruin/.bruin.yml \
  --description "profile v0 target orders for migration validation" \
  --query "SELECT COUNT(*) AS row_count, COUNT(DISTINCT order_id) AS distinct_keys, COUNT(*) - COUNT(order_id) AS null_keys, MIN(updated_at) AS min_incremental, MAX(updated_at) AS max_incremental FROM migration_v0.orders" \
  --output json > fivetran/.artifacts/<run-id>/run/target-profile.json
```

Use `bruin data-diff --full --fail-if-diff` as an additional gate when the
source and target have a reviewed common representation. Do not treat expected
system-column or cross-dialect differences as implicitly approved.

## Final metadata review

Only after explicit user approval:

```bash
bruin ai enhance bruin --codex --environment default
bruin validate bruin/pipeline.yml --config-file bruin/.bruin.yml
```

Review the diff before accepting metadata suggestions. `ai enhance` can add
descriptions, tags, and quality checks, but it does not replace human ownership
of migration semantics.

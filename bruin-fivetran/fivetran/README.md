# Fivetran migration inputs

The agent stores sanitized Fivetran captures, converter drafts, and execution
evidence in `fivetran/.artifacts/<run-id>/`. Captures preserve connection and
schema selection, schedules, source configuration field names, and allowlisted
replication behavior such as delete capture. Credential-shaped values and
unrecognized configuration values are never retained.

This location is intentionally ignored. A capture may contain connection names,
schema/table names, and other account metadata even after credential redaction.
Never commit captures, raw API responses, credentials, or customer data.

Use `../scripts/import_fivetran.py` through the bundled migration skill. It
uses only Fivetran GET endpoints; it never changes Fivetran state.

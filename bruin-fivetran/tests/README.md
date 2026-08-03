# Maintainer regression fixture

This directory is not part of the end-user migration workflow. It provides a
deterministic PostgreSQL source, sanitized Fivetran snapshot, reviewed Bruin
reference output, and tests for the template’s scripts.

```bash
cd tests
./scripts/bootstrap.sh
./scripts/run.sh
./scripts/verify.sh
./scripts/teardown.sh
```

The scripts use a dynamically allocated host port and create state only in
`tests/.artifacts/` plus their explicit Docker Compose project. `verify.sh`
validates the generated pipeline with Bruin and performs a zero-tolerance data
comparison that fails on mismatch.

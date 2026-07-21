# Contributor guidance

## Evidence and scope

- Base research claims on official source-platform and Bruin/DAC documentation. Keep links, version assumptions, and unsupported features in the track README.
- Start every migration with a source and target inventory: objects, SQL/code, dependencies, schemas, materializations, schedules, credentials, incremental state, and validation rules.
- Clearly separate automated conversion, a hand-authored reference, unsupported features, and human-review decisions.

## Fixtures and safety

- Never commit real credentials, customer data, production exports, generated database files, or Docker volumes.
- Source fixtures must be deterministic, local, and minimal. Prefer programmatic provisioning before documenting UI clicks.
- Scripts must be idempotent and may create or remove state only in their own `example/.artifacts/` directory and explicitly named Docker Compose project.
- Use dynamically allocated published ports (or `CONDUCTOR_PORT` when available); never assume a fixed host port.
- Keep tracked source fixtures in `source/`, target references in `target/`, and all converter output or captures in ignored `.artifacts/`.

## Validation

- Include bootstrap, run, verify, and teardown commands in every example README.
- Validate the target with its native toolchain and compare the source and target outputs whenever a common representation is available.
- A validation command must fail on a mismatch. Do not replace a data comparison with a visual or manual assertion.

## Future skills and converters

- A future custom skill belongs at `.agents/skills/<skill>/SKILL.md`.
- Skills and converters must treat these examples as regression fixtures and write generated output only to `.artifacts/`.
- Keep converter behavior reviewable: preserve source inputs, produce a conversion report, and flag human decisions instead of silently guessing.

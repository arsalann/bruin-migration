# Contributor guidance

## Repository purpose

- This repository produces educational migration documentation and ready-to-use Bruin/DAC templates. It is not a workspace for a live customer migration.
- Write each track so a future user can adapt it to a named source platform and their own Bruin project. Use explicit placeholders and assumptions; never imply that the example represents a production system or a complete compatibility guarantee.
- Treat agent prompts, sample configurations, fixtures, commands, and migration-plan documents as reusable template artifacts. Describe the expected runtime action, inputs, outputs, and human decisions without connecting to external customer systems from this repository.

## Action plan for developing a template

- Apply this plan separately to each template. Its example, flow, agent prompts, commands, validations, and review criteria must fit the documented product and workflow—such as Ingestr, Bruin CLI, or DAC—rather than assuming a legacy ingestion source.

1. Create a representative real-world example for the template's specific product and workflow. Keep it deterministic, minimal, local, and free of customer data and credentials; it should still exercise the capabilities the template claims to support.
2. Create the appropriate workflow and agent prompts from that example. Document the relevant inputs and outputs, assumptions, decision points, mappings where applicable, and expected artifacts.
3. Run the agent prompts against the example to test the complete template. Capture generated output only in `.artifacts/`, validate with the product's native toolchain and any applicable data comparison, and make the test fail on a mismatch.
4. Conduct a manual review of the documentation, generated artifacts, unsupported features, safety guarantees, and open human decisions before treating the template as ready to use.

## Evidence and scope

- Base research claims on official source-platform and Bruin/DAC documentation. Keep links, version assumptions, and unsupported features in the track README.
- Start every migration template with a source and target inventory: objects, SQL/code, dependencies, schemas, materializations, schedules, credential requirements, incremental state, and validation rules.
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

## Ingestion migration workflow

- Build ingestion tracks as an agentic migration template with four runtime stages: import the migration inputs; create and validate an MVP ingestion pipeline; run it to create v0 tables and demonstrate value; then plan the production migration.
- Start by importing the source configuration and connection details. Include optional database and table mappings where available, and optional AI enhancement as a reviewable draft—not an automatic migration decision. An agent skill or script may automate any supported import step; preserve the resulting inputs, provenance, version, and missing metadata in the user's migration workspace.
- Treat adding connections as a runtime prerequisite for the template user. Include only connection names, required parameters, and environment-variable placeholders; never add real credentials or actual customer connection configurations to this repository.
- Include the generic first-agent prompt below in each applicable ingestion track, adapted only for source-platform terminology and documented capabilities. It specifies the runtime work the first implementation agent must perform; contributors do not perform that work against external customer systems while authoring this template.

```text
Read the imported source configuration, connection details, optional database and
table mappings, and source table/asset schemas and definitions. Read the relevant
Bruin documentation and legacy-to-Bruin configuration mapping, including
frequency, materialization, incremental strategy, and related execution settings.

Use the Bruin MCP and documentation to build an MVP/draft ingestion pipeline.
Create `plan.md` alongside the reviewed target reference material. Initially, it
must record configuration mismatches; ingestion-specific column mappings
(including casts, defaults, renames, omissions, and generated fields); and every
TODO or question requiring clarification, such as materialization and incremental
strategy.

Validate the MVP, then run it to an isolated temporary destination to create v0
tables and demonstrate the ingestion outcome. Verify the resulting data and make
the validation fail on a mismatch. Update `plan.md` after that run with next steps
and a production-migration plan, including decisions still needed for incremental
strategy, metadata columns, downstream refactors, validation, and switchover.
```

- The template must define the expected `plan.md` location with its reviewed target reference material (not in `.artifacts/`) and link to it from the track README. The runtime plan must distinguish automated findings, hand-authored decisions, unsupported features, and open human-review items.
- Provide deterministic local fixtures or a clearly bounded mock for the template's example validation. Its documented runtime test must target an isolated temporary destination table, include teardown, and fail on a data mismatch without affecting production or shared tables.

## Future skills and converters

- A future custom skill belongs at `.agents/skills/<skill>/SKILL.md`.
- Skills and converters must treat these examples as regression fixtures and write generated output only to `.artifacts/`.
- Keep converter behavior reviewable: preserve source inputs, produce a conversion report, and flag human decisions instead of silently guessing.

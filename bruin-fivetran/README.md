# Fivetran to Bruin migration template

This is an agent-led migration template for turning one reviewed Fivetran
connection into a new Bruin `ingestr` project. It is designed for Bruin users to
copy into a migration workspace and run with an agent; it is not a one-shot
converter or a production compatibility guarantee.

## Start the migration

Use the copyable [agent prompt](agent-prompt.md) with any capable coding agent,
or invoke the bundled Codex skill from this template's root:

```text
Use $migrate-fivetran-to-bruin to migrate my Fivetran connection into a new Bruin project.
```

The skill drives this conversation in order:

1. Import one Fivetran connection into `fivetran/.artifacts/<run-id>/` and
   create/update the root [plan.md](plan.md).
2. Create a bare `bruin/` project and an untracked `bruin/.bruin.yml` containing
   connection placeholders, then pause for the user to fill them in.
3. Build `bruin/pipeline.yml` and ingestr assets from scratch using the Fivetran
   capture, Bruin MCP, and Bruin documentation. The agent records mappings and
   TODOs in `plan.md`.
4. Ask the user to resolve every TODO, including the scope of the first run,
   before any ingestion executes.
5. Run the approved scope, profile and compare source/target data with
   `bruin query`, run quality checks, summarize results, and pause again.
6. If the user requests final review, enhance metadata, write `bruin/README.md`,
   and add cutover actions and risks to `plan.md`.

## Workspace layout

```text
bruin-fivetran/
├── plan.md                         # living migration plan and user action list
├── fivetran/
│   ├── README.md
│   └── .artifacts/<run-id>/         # ignored capture, drafts, and run evidence
├── bruin/                           # agent-created Bruin project
│   ├── .bruin.yml                   # ignored user-supplied connections
│   ├── pipeline.yml
│   ├── assets/
│   └── README.md                    # created during optional final review
├── scripts/
│   ├── import_fivetran.py
│   └── initialize_bruin_project.py
├── .agents/skills/migrate-fivetran-to-bruin/
└── tests/                           # maintainer-only deterministic fixture
```

`fivetran/` is the migration input area. Captures stay in its `.artifacts`
subdirectory so API metadata, generated drafts, logs, and query results are
ignored. Nothing in this repository creates, pauses, resumes, updates, or
deletes a Fivetran connection.

## Safety and review boundary

- Do not paste Fivetran or database secrets into chat. Set scoped Fivetran API
  credentials in local environment variables or an untracked config file.
- The agent creates connection placeholders but pauses for the user to add real
  values and explicitly continue.
- The agent may generate drafts, but it does not run a destination write until
  the user approves the initial run’s table scope, data bounds, and target.
- Fivetran schedules, checkpoint state, deletes, system columns, schema policy,
  transformations, private networking, alerts, and retries require review; they
  are never silently assumed equivalent.

## Maintainer regression fixture

The root-level user workflow intentionally has no `example/` directory. A
deterministic local regression fixture lives in [tests/](tests/README.md) so the
template can be validated without a Fivetran account or customer data.

## Version assumptions and official references

Validate the current versions before using this template in a production
migration. The implementation is tested with Python 3.13, PyYAML 6.0.3, Bruin
`v0.11.706`, ingestr `v1.1.7`, and PostgreSQL `16.4-alpine` for the regression
fixture.

- [Fivetran REST API getting started](https://fivetran.com/docs/rest-api/getting-started)
- [Fivetran Connections API](https://fivetran.com/docs/rest-api/api-reference/connections/list-connections)
- [Fivetran Connection Schema API](https://fivetran.com/docs/rest-api/api-reference/connection-schema)
- [Bruin connection configuration](https://getbruin.com/docs/bruin/secrets/bruinyml.html)
- [Bruin ingestr assets](https://getbruin.com/docs/bruin/assets/ingestr.html)
- [Bruin query command](https://getbruin.com/docs/bruin/commands/query.html)
- [Bruin AI enhance command](https://getbruin.com/docs/bruin/commands/ai-enhance.html)

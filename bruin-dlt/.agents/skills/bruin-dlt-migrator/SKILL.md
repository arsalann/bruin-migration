---
name: bruin-dlt-migrator
description: Stage a review-gated migration from one dlt pipeline to a new Bruin ingestr project.
---

# dlt to Bruin migrator

Use this skill when a user wants to migrate a dlt pipeline to Bruin. Read the
repository-root `dlt-bruin-prompt.md` and `plan.md` before acting. Follow the
prompt's stages in order.

Read the dlt project directly. The pipeline module, `.dlt/config.toml`, resource
hints, write dispositions, and incremental cursors are ordinary Python and TOML;
parsing them yourself is more faithful than any importer, and there is no
importer to install.

Use the sibling `convert_dlt_connections.py` for one step only: turning dlt
credentials into Bruin connections. It reads `.dlt/secrets.toml`, connection
strings, and dlt's credential environment variables, writes Bruin connections
into a Git-ignored `.bruin.yml` with mode 600, and prints only field names,
their origin, and what is still missing.

By default the script writes the real secret values into that `.bruin.yml` —
passwords, tokens, private keys, and GCP service-account JSON — so the output is
a working configuration. Confirm the file is Git-ignored before running it, and
never read it back afterwards. Offer `--placeholders` if the user prefers
`${ENV_VAR}` references instead of values.

Rules:

- Migrate one dlt pipeline at a time, and one resource at a time inside it.
- Never open `.dlt/secrets.toml`, `~/.dlt/secrets.toml`, a dlt connection
  string, or a credential environment variable. Run the converter instead.
- Never expose or store credentials, source data, hosts, ports, account
  identifiers, or dlt pipeline state.
- Treat `.bruin.yml` and `.artifacts/` as sensitive even when they are
  Git-ignored: do not print them, pass them to AI subprocesses, or copy them
  into generated documentation.
- Never run the dlt pipeline, call `pipeline.drop()`, edit `~/.dlt`, or reuse the
  dlt working directory or state. The dlt pipeline stays the system of record
  until the user approves cutover.
- Create the new `bruin/` project yourself; do not transliterate dlt Python.
- Map write disposition to a Bruin `materialization.strategy`, the incremental
  cursor path to `incremental_key`, and `primary_key` to `columns[].primary_key`.
  Confirm the destination supports the chosen strategy before promising it.
- Route every resource before drafting: database source to an ingestr asset; API
  source with an ingestr connector to an ingestr asset, rewritten against that
  connector, not translated; anything else to a Bruin Python asset. Check
  ingestr's supported-source list first and record that you checked.
- `@dlt.transformer`, `add_map`, `add_filter`, `scd2`, custom `last_value_func`,
  a hand-rolled paginator, and any row-level Python cannot become a plain ingestr
  asset. Port them into a Bruin Python asset: move the generator and transforms
  across unchanged, put `write_disposition` into `materialization.strategy`,
  return a DataFrame from `materialize()`, take credentials through `secrets:`,
  and derive any window from `BRUIN_START_DATE`/`BRUIN_END_DATE`.
- Nested/child tables and `scd2` still have no equivalent in either shape. Flag
  them for a separate approved design rather than inventing one.
- Record the destination naming difference. dlt prefixes the dataset onto the
  table name on destinations without real schemas; Bruin ingestr writes a real
  `database.table`. Downstream queries change.
- ingestr keeps its own state and derives the window from the Bruin run
  interval; dlt's cursor state does not transfer. Obtain explicit start/end
  bounds and a source-consistency boundary before any historical run, and
  confirm that `append` windows do not overlap a loaded window.
- Pause after the connection conversion, before any destination write, and after
  each approved v0 run.
- Keep repository-root `plan.md` current with facts, decisions, TODOs, run
  history, source-consistency boundaries, unsupported behavior, and cutover
  work.
- Run approved aggregate parity and quality checks after every v0 load, against
  both the source and the dlt tables. Use `bruin data-diff` as a pass/fail gate
  only when its representation is explicitly reviewed as comparable; when the
  destination cannot be summarized by Bruin, run the diff over an approved
  comparison projection in a supported dialect rather than dropping the gate.
- Do not enable schedules, run destructive refreshes, pause the dlt pipeline, or
  drop a dlt dataset without explicit user approval.

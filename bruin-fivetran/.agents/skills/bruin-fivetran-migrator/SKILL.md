---
name: bruin-fivetran-migrator
description: Stage a review-gated migration from one Fivetran connection to a new Bruin ingestr project.
---

# Fivetran to Bruin migrator

Use this skill when a user wants to migrate one Fivetran connection to Bruin.
Read `bruin-fivetran/fivetran-bruin-prompt.md` and
`bruin-fivetran/plan.md` before acting. Follow the prompt's stages in order.

Use the sibling `import_fivetran.py` for Fivetran access. It makes GET requests
only and writes redacted captures to `bruin-fivetran/.artifacts/`.

Rules:

- Capture exactly one connection selected by the user.
- Never expose or store credentials, source data, endpoints, or Fivetran state.
- Create the new `bruin/` project yourself; do not expect generated assets.
- Pause after connection placeholders, before any destination write, and after
  each approved v0 run.
- Keep `bruin-fivetran/plan.md` current with facts, decisions, TODOs, run
  history, unsupported behavior, and cutover work.
- Do not enable schedules, run destructive refreshes, or disable Fivetran
  without explicit user approval.

# Testing

Validation for this framework lives in a separate repository:
**[fds-blueprint-testbed](https://github.com/kmflynn5/fds-blueprint-testbed)**

This is intentional. Keeping the test harness external means framework development agents
and contributors cannot write implementation code that passes tests by knowing what the
tests assert. The testbed is a genuine outside observer.

---

## What the Testbed Validates

The testbed exercises the framework against a live Snowflake trial instance using three
realistic connector archetypes, each with a distinct write pattern:

| Connector | Archetype | Write Pattern | Data Source |
|---|---|---|---|
| `fivetran_nyc` | Managed SaaS | Append | MotherDuck public sample_data |
| `python_pipeline_hn` | Custom Python pipeline | Incremental upsert | MotherDuck public sample_data |
| `penguins_reference` | Reference / dimension data | Full refresh (TRUNCATE + INSERT) | DuckDB public CSV |

The third connector exists specifically to validate that the `write_mode` field in
`connectors.yaml` correctly drives conditional `TRUNCATE` privilege grants through the
`for_each` role generation logic — confirming that privilege variation across connectors
is handled cleanly, not just the common case.

---

## Test Phases

The testbed is organized into phases that mirror the framework's own maturity progression.

**CORE** — Greenfield instance, three connector archetypes, manual execution.
Validates role topology, write pattern correctness, privilege isolation, and that
`PHILOSOPHY.md` is legible to someone who did not author the framework.

**OBSERVABILITY** — Planned. Will cover multi-environment promotion, dbt transformation
layer, and CI/CD pipeline for `terraform apply`.

**ENFORCEMENT** — Planned. Will cover brownfield intake path, production data volumes,
and schema drift detection.

---

## What This Repository Does Not Contain

There are no test fixtures, mock data, or test runner configuration in this repository.
If you are looking for those, see
[fds-blueprint-testbed](https://github.com/kmflynn5/fds-blueprint-testbed).

Pull requests to this repository are not required to pass a local test suite before
merge. Framework correctness is validated externally, against a real Snowflake instance,
after the fact — not inlined into the development loop. This is a deliberate tradeoff:
it keeps the framework repo clean and prevents tests from being written to match the
implementation rather than the other way around.

---

## Running Validation Yourself

If you are evaluating this framework for your own environment, clone the testbed and
follow its README. You will need:

- A Snowflake trial account (30-day free tier is sufficient for Core phase)
- Terraform >= 1.5.0 with the Snowflake provider >= 0.90.0
- Python 3.11+
- `openssl` for key pair generation

The testbed README walks through the full setup sequence, from key pair generation
through `terraform apply` through running all three connector simulations and
executing `scripts/verify_roles.sql` to confirm the role topology.

---

## Relationship Between Repos

```
github.com/kmflynn5/fds-snowflake-maturation-blueprint   (this repo)
│
│   Terraform modules, connectors.yaml schema,
│   intake process, PHILOSOPHY.md
│
└── validated by ──►  github.com/kmflynn5/fds-blueprint-testbed
                       │
                       │   Connector simulations, verify_roles.sql,
                       │   Core/Observability/Enforcement test plans
```

Changes to the `connectors.yaml` schema or the role generation logic in this repo
should be followed by a Core phase validation run in the testbed before being
considered stable. There is no automated enforcement of this — it is a convention,
documented here so it is not forgotten.

# ADR-011: Silver-Layer Data Quality Strategy

## Status
Accepted — implemented and verified (Milestone 5)

## Context
Bronze (Milestone 4) deliberately enforces schema but does not validate data quality —
malformed rows are preserved as-is, and real validation is explicitly deferred to
Silver. Milestone 5 needed to decide two independent things: **how** validation logic
is implemented, and **what happens** to a row that fails a rule.

## Problem
1. What should execute the validation rules — a dedicated data-quality framework, or
   plain Spark code?
2. When a row fails a rule, should it stop the pipeline, be silently dropped, or be
   handled some other way?

## Options Considered — Validation Mechanism
| Option | Trade-off |
|---|---|
| **Great Expectations** | Industry-standard name, rich expectation library, human-readable data docs. Cost: a second framework/config layer on top of Spark; Data Docs/checkpoint artifact storage adds infrastructure with unclear payoff on a single-user Databricks Free Edition serverless workspace. |
| **Pandera** | Clean, typed API; strong for pandas. Its PySpark support is the less mature side of the library. |
| **Delta Live Tables expectations** | Native, elegant declarative quality gates (`@dlt.expect`). Cost: DLT is its own orchestration paradigm (pipelines, not notebooks) — adopting it now would preempt the Airflow-based orchestration planned for Milestone 12 and create two competing orchestrators. |
| **PySpark-native (chosen)** | No new dependency; consistent with Bronze's existing manual-check style; more verbose, but every rule is explicit and owned, which is also the more defensible answer in an interview ("I wrote and understand every check"). |

## Options Considered — Failure Handling
| Option | Trade-off |
|---|---|
| **Hard fail** | Any violation stops the whole write — no partial Silver output. Simple, but at real-world scale a single bad row blocking an entire batch is often too blunt. |
| **Silent drop** | Bad rows disappear. Rejected outright — violates the project's own principle that data-quality failures must be visible/actionable, and destroys the audit trail. |
| **Quarantine (chosen)** | Valid rows proceed to Silver; failing rows go to a parallel `_rejects` table with per-row reasons. Nothing disappears silently; the rejects table is itself queryable and became the diagnostic tool that caught the `amount=0.0` issue below. |

## Decision
- Validation is implemented as plain PySpark (`filter`, `isNull`, `when`/`otherwise`,
  window functions for uniqueness), matching Bronze's existing convention.
- Failing rows are quarantined into `ced.silver.<table>_rejects`, not dropped or
  hard-failed. Valid rows and rejected rows always sum to the Bronze input count
  (enforced programmatically — see `write_silver_tables`'s reconciliation check).
- A row can fail multiple rules simultaneously; `_rejection_reasons` is an array
  capturing all of them, not just the first match.

## Honest Limitation
Quarantining is an **enforcement point and audit trail**, not a pipeline
circuit-breaker. There is no orchestrator wired up yet (Airflow integration is
Milestone 12) to actually halt downstream processing on a bad batch — today,
"stopping downstream processing" means "bad rows are isolated in a separate table,"
not "the pipeline run fails." This should not be overstated as more automation than
currently exists.

## Known Technical Debt Introduced: `amount` NULL vs. `0.0`
The M3 generator writes a literal `0.0` (not NULL) as its default `amount` value for
non-monetary event types, unlike `merchant_category`, which correctly defaults to
NULL for the same "not applicable" case (see ADR-010). Two fixes were available:

- **Fix the generator** (write `None`/NULL instead of `0.0`) — architecturally
  consistent with `merchant_category`, but requires regenerating and re-verifying an
  already-closed milestone (M3).
- **Relax the Silver rule** to accept `0.0` as the valid non-monetary sentinel —
  chosen, to avoid reopening M3.

**Consequence:** for `amount`, "not applicable" and "genuinely zero" are
indistinguishable in Silver and beyond. This is a real cost if `amount_spike`-style
feature engineering (Milestone 6+) ever needs that distinction (e.g. treating a
$0 monetary transaction as a legitimate anomaly signal). The Silver rule still
flags any *other* non-zero value on a non-monetary event as invalid — only exact
`0.0` is treated as the accepted sentinel.

## Rationale
Both decisions optimize for the same thing: staying inside the project's existing
toolset and conventions unless a new tool earns its place architecturally, while
keeping every data-quality decision auditable rather than silent. The `amount=0.0`
call trades long-term semantic cleanliness for not re-touching a verified milestone —
documented here explicitly so it isn't mistaken for the preferred design.

## Consequences
- Silver validation has zero new runtime dependencies.
- Every Bronze row is accounted for in exactly one of `<table>` or `<table>_rejects`,
  verified programmatically on every run.
- The `amount` ambiguity is now a tracked, visible debt item rather than a silent gap
  — revisit by fixing `event_generator.py` if Milestone 6+ feature engineering
  actually needs to distinguish "not applicable" from "zero."
- `merchant_category`'s NULL-handling ambiguity from ADR-010 is resolved: NULL is
  valid/expected for non-monetary events, and only flagged as invalid when NULL on a
  monetary event.

## Future Considerations
- If reject rates become non-trivial at larger synthetic scales (Milestone 21,
  scalability testing), reconsider whether Great Expectations' reporting/dashboarding
  earns its keep at that volume.
- Once Milestone 12 wires Airflow orchestration around this notebook, revisit whether
  a high reject rate should actually fail the Airflow task (true "stop downstream
  processing"), rather than only quarantining.
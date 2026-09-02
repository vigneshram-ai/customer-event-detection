# ADR-012: Gold-Layer Feature Engineering Strategy

## Context

Milestone 6 introduces the Gold layer: `ced.silver.events` (27,128 valid rows) and
`ced.silver.customers` (1,000 valid rows) are joined and transformed into
`ced.gold.customer_events_features`, one row per event, enriched with behavioral
features computed from each customer's event history. This is the first layer
where the pipeline moves from "is this row structurally valid?" (Bronze/Silver)
to "what does this event look like in the context of this customer's history?" —
introducing genuinely new design risks (temporal leakage, ambiguous feature
applicability, Spark window-aggregate edge cases) that didn't exist in earlier
milestones.

The milestone was originally scoped to a "core" subset of six features, with
geographic deviation, time-of-day deviation, and failed-login velocity deferred
to a follow-up pass. Mid-milestone, the scope was expanded back to fold all
three into this same milestone — this ADR reflects the final, actual scope:
**eight** features shipped, one (time-of-day deviation) considered and
deliberately dropped after design.

## Problem

Several design questions had to be resolved before and during implementation:

1. How do we guarantee rolling/window features never use information from the
   future relative to the event being scored?
2. `amount = 0.0` is a documented sentinel for "not applicable" on non-monetary
   events (ADR-011). Amount-based rolling features must not let that sentinel
   distort the calculation, and must not silently produce a *plausible-looking
   but meaningless* number on non-monetary rows.
3. What does "new device" mean for a customer's very first event — is a
   customer's declared `normal_device` "known" from the start, or does it need
   to be observed in event history first?
4. Is country-level mismatch (`country != home_country`) an honest enough proxy
   for "geographic deviation," given the data model has no lat/long?
5. Does a rolling count over a Spark window return a genuine `0` when the
   window frame is empty (no qualifying prior events), or something else?
6. Is time-of-day deviation worth the implementation complexity it requires
   (circular statistics, since raw hour comparison breaks at midnight) for
   this milestone?

## Options Considered

### Leakage boundary
- **A. Symmetric/centered windows** (e.g. `rowsBetween(-3, 3)`) — rejected
  outright. Would let an event's own future behavior leak into its own
  "historical" feature, invalidating any later anomaly-detection use.
- **B. Windows ending at `-1` relative to the current row** (`rowsBetween`/
  `rangeBetween` up to but excluding the current row) — **chosen**. Guarantees
  every feature value is computable at the moment the event occurs.

### Amount-based feature applicability
- **A. Gate only the window's *input*** (exclude non-monetary amounts from
  feeding the rolling average, but still emit a value on every row) — initial
  implementation. Live verification showed `prior_avg_amount_90d` resolved to
  a real number on non-monetary rows (e.g. `login` events) once the customer
  had any monetary history, rather than `NULL` — a mismatch with the intended
  design, caught by inspecting sanity-check output rather than accepting a
  clean run at face value.
- **B. Gate both the window's input and the emitted value on the current
  row's `event_type`** — **chosen**. `prior_avg_amount_90d` and
  `amount_deviation_from_prior_avg` are `NULL` on any row whose `event_type`
  is not monetary, full stop, regardless of history.

### New-device definition
- **A. Events-only history** (a device counts as "known" only once observed
  in a prior event) — initial default proposed.
- **B. `normal_device` counts as known from event zero, in addition to
  observed history** — **chosen**, on user direction. `normal_device`
  represents the device the bank has on file, reasonable to treat as known
  before any event history exists.

### Geographic deviation representation
- **A. Skip it** — the data model has no lat/long, so "geographic deviation"
  can't be computed as a true distance.
- **B. Country-level mismatch** (`country != home_country`) — **chosen**.
  An honest, clearly-scoped proxy: the ADR and code comments are explicit that
  this is country mismatch, not geo-distance, so the feature can't be
  misrepresented later as more precise than it is.

### Rolling-count-over-empty-window behavior
- **Discovered, not chosen between options**: Spark's `SUM` (and other
  aggregates) over an **empty window frame** — i.e. no rows fall within the
  `rangeBetween` bounds — returns `NULL`, not the aggregate's identity value
  (`0` for `SUM`). This was not anticipated in the original design ("defaults
  to 0, not NULL" was stated as a design assumption in the notebook's own
  sanity-check comments) and was caught only by running the notebook: with
  27,128 events and comparatively sparse per-customer event spacing, 19,062 of
  27,128 rows (~70%) had an empty 24-hour window and therefore a `NULL`
  `prior_failed_login_count_24h` instead of the correct `0`.
  **Fix**: wrap the window aggregate in `F.coalesce(..., F.lit(0))`, since
  "zero failed logins in the past 24 hours" is a known fact whenever a
  customer has no qualifying prior events in that window — not missing
  information, and should never read as `NULL`.

### Time-of-day deviation
- **A. Implement via circular statistics** — designed in detail (hour-angle
  encoding via `sin`/`cos`, circular mean via `atan2`, wrapped angular
  distance converted back to hours) and partially implemented.
- **B. Drop from this milestone** — **chosen**, on user direction, after the
  design was already written up. The circular-statistics approach is
  correct and was fully specified, but the added implementation complexity
  wasn't justified without a concrete downstream consumer (e.g. a model
  actually needing this signal) driving the requirement right now.

## Decision

- All rolling/window features use windows ending at `-1` relative to the
  current row.
- `prior_avg_amount_90d` and `amount_deviation_from_prior_avg` are `NULL`
  whenever the current row's `event_type` is not monetary
  (`card_transaction`, `payment`, `transfer`), regardless of event history.
- `is_new_device` is `False` if the device matches the customer's
  `normal_device` **or** appears in prior event history; `True` only when
  neither is true.
- `is_unusual_country` is a direct `country != home_country` comparison —
  documented explicitly as a country-mismatch proxy, not a geo-distance
  calculation.
- `prior_failed_login_count_24h` is a rolling 24-hour count of `failed_login`
  events, **coalesced to `0`** on an empty window frame, and applies to every
  row regardless of the current row's own `event_type` (unlike the amount
  features — a burst of failed logins is relevant context for any subsequent
  event, not just other failed logins).
- **Time-of-day deviation is deliberately not shipped in Milestone 6.** The
  design (circular statistics via hour-angle sin/cos encoding) is sound and
  documented here for future reference, but implementation was stopped
  mid-way and removed before final verification, on the basis that the added
  complexity didn't earn its place without a concrete need driving it yet.
- Final Milestone 6 feature set (8 features): `prior_event_count_7d`,
  `prior_avg_amount_90d`, `amount_deviation_from_prior_avg`, `is_new_device`,
  `is_unusual_channel`, `is_unusual_country`, `prior_failed_login_count_24h`,
  `time_since_last_event_seconds`.

## Rationale

Treating the leakage boundary as non-negotiable protects the eventual ML
model from a subtle but serious bug class (features that couldn't have
existed at prediction time). Gating amount features on the current row's own
type keeps their meaning simple and auditable: "not applicable" always looks
like `NULL`, never a real-looking number reflecting unrelated history.
Coalescing the failed-login count to `0` on empty windows keeps the column
meaning what it says — a count, never "unknown." Treating `normal_device` as
known from the start reflects how a bank would realistically already have a
device on file before a customer's first observed event. Naming the country
feature honestly (mismatch, not distance) avoids letting a modest proxy be
mistaken for something more sophisticated later. Dropping time-of-day
deviation mid-implementation, rather than shipping a half-verified version,
keeps the "implemented and verified" claim meaningful — every feature that
did ship has been checked against real sanity-check output.

## Consequences

- **Two independent, real bugs were caught during live verification, not
  code review** — both by reading actual sanity-check numbers and noticing
  they contradicted the stated design, rather than accepting a clean run at
  face value:
  1. `prior_avg_amount_90d`'s initial implementation gated the window's
     input but not the emitted value on `event_type`.
  2. `prior_failed_login_count_24h`'s initial implementation assumed Spark
     window `SUM` returns `0` on an empty frame; it returns `NULL`.
  Both are now fixed. This reinforces the project's standing discipline:
  sanity-check output must be read and reasoned about, not just confirmed as
  "ran without error" — and it's worth explicitly remembering the second
  lesson (`empty window frame → NULL, not the aggregate's identity`) for any
  future rolling-count feature added to this project, since it will recur.
- `prior_avg_amount_90d` no longer functions as general "customer's recent
  monetary context" available on any event type — strictly scoped to
  monetary events. A future milestone wanting monetary context on a
  non-monetary event would need a separately-named feature.
- `is_unusual_country` is explicitly a coarser signal than true geographic
  deviation would be (e.g. travel within a large home country, or between
  neighboring countries, isn't distinguished from travel to a distant one).
  Acceptable given the data model's actual granularity — should not be
  presented in an interview as more sophisticated than it is.
- `is_new_device` being `False` for a `normal_device` match means it reads
  `False` more often early in a customer's history than a pure
  events-only definition would — intentional, not a weaker signal by
  accident.
- **Time-of-day deviation remains fully designed but unimplemented.** The
  design in this ADR (hour-angle via `sin`/`cos`, circular mean via
  `atan2`, wrapped angular distance) is ready to pick up later without
  redesigning from scratch, but must not be described as implemented.
- No automated test coverage for `gold_feature_engineering.py`, consistent
  with Bronze/Silver — Databricks/Spark-only code, no local PySpark harness
  in this project. This means bugs of exactly the two kinds caught here
  (applicability-gate mismatches, empty-window-frame NULLs) are only
  detectable via live-run sanity checks — worth remembering as this project's
  actual test strategy for Spark logic, not a placeholder for "tests to add
  later."

## Future Considerations

- If time-of-day deviation is picked up later, reuse the design in this ADR
  rather than re-deriving it, and verify the `[0, 12]`-hour output range as
  part of closing that work (this bound was identified during design but
  never checked against real data, since implementation was stopped first).
- If a future milestone needs "recent monetary behavior regardless of
  current event type," add it as a new, separately named column rather than
  relaxing `prior_avg_amount_90d`'s applicability rule.
- Any future rolling-count-style feature (count/sum over a time-bounded or
  row-bounded window) should default to `F.coalesce(..., F.lit(0))` (or the
  appropriate identity value) from the start, given the empty-window-frame
  NULL behavior confirmed here — no need to rediscover this via another
  live-run bug.
- Gold features have not been cross-referenced against
  `events_ground_truth.csv` (the Milestone 3 anomaly labels) for
  correctness — only structural sanity checks (row counts, null-count
  patterns, plausible true/false counts) have been performed. Worth
  revisiting once a detector actually consumes these features.
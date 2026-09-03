# ADR-013: Baseline Rule-Based Detector Design

## Status
Accepted

## Context
Milestone 7 required a detector prior to the ML model (Milestone 8), serving three
purposes: (1) establish the `detection_score`/`detection_flag`/`model_version`
output contract reused by the eventual ML model and batch inference, (2) provide
a naive reference point the ML model must outperform, (3) provide the first
cross-reference of Gold-layer features (Milestone 6) against the Milestone 3
synthetic ground-truth anomaly labels (`events_ground_truth.csv`), closing
technical debt item #13.

## Problem
How should a rule-based baseline combine the eight Gold-layer features into a
single per-event detection outcome, without the scoring logic being tuned
against ground truth — which would defeat the purpose of a baseline and
introduce a subtle form of leakage into what's supposed to be a naive
reference point?

## Options Considered

**Scoring logic:**
- **A. Any-rule-fires (OR logic).** Flag if any single feature crosses its
  threshold. Simple and maximally explainable per event, but no way to weigh
  weak signals against strong ones; likely to over-flag on weak signals
  common in normal behavior (e.g., channel switching).
- **B. Weighted additive point score (chosen).** Each rule contributes a fixed
  number of points; points sum to a continuous `detection_score`; a threshold
  on that score produces `detection_flag`. Slightly more "model-like," and
  produces a genuine continuous score (not just a boolean) that could support
  PR-AUC-style evaluation later — while remaining fully rule-based, with no
  training or fitting involved.

**Threshold selection:**
- **A. Sweep thresholds against ground truth to maximize F1 (rejected).**
  Would produce better-looking baseline metrics, but this is leakage for a
  component whose entire purpose is being an untuned reference point. A
  baseline "tuned" against the same ground truth it's evaluated on isn't a
  fair benchmark for the ML model to beat.
- **B. Fixed, individually reasoned thresholds (chosen).** Each threshold is
  justified on its own terms (e.g., "a new device is a strong signal on its
  own"; "a single failed login is common and not suspicious; six in 24h is").
  No threshold was selected by looking at ground-truth outcomes.

**Where the detector runs vs. where it's evaluated:**
- **A. Everything in Databricks (rejected as sole approach).** Ground truth
  is explicitly synthetic-only test scaffolding (per ADR-010's exclusion of
  the ground-truth sidecar from the Bronze volume upload) and was deliberately
  never promoted into the warehouse. Keeping it there permanently would blur
  that boundary.
- **B. Detector on Databricks, evaluation locally (chosen).** The detector
  notebook (`notebooks/baseline_detector.py`) runs on Databricks like Bronze/
  Silver/Gold, consistent with the Spark-based pipeline. Its output is
  exported as CSV to a new Unity Catalog volume (`ced.gold.exports`) and
  downloaded by a local script (`evaluation/evaluate_baseline.py`), which
  joins it against the local `events_ground_truth.csv` and computes metrics.
  This keeps "Databricks does Spark work, local does local work" consistent
  with the rest of the project, and keeps ground truth out of the warehouse
  permanently.

## Decision
Implement a fixed, additive point-scoring rule set over the eight Gold
features:

| Feature | Rule | Points |
|---|---|---|
| `is_new_device` | `True` | +2 |
| `is_unusual_country` | `True` | +2 |
| `is_unusual_channel` | `True` | +1 |
| `amount_deviation_from_prior_avg` / `prior_avg_amount_90d` (ratio) | `> 2` | +1 |
| same ratio | `> 5` | +1 more (+2 total at this tier) |
| `prior_failed_login_count_24h` | `>= 3` | +1 |
| same feature | `>= 6` | +1 more (+2 total at this tier) |

`detection_flag = detection_score >= 2`. `prior_event_count_7d` and
`time_since_last_event_seconds` are deliberately excluded from scoring —
neither has a principled global threshold without a customer-relative
baseline, which the ML model is better positioned to learn than a hand-set
rule. Both are carried through as context-only columns in the output.

The amount-ratio calculation only evaluates when `prior_avg_amount_90d` and
`amount_deviation_from_prior_avg` are both non-NULL and the average is
non-zero (guarding divide-by-zero and non-monetary/no-history rows per the
Milestone 6 NULL-applicability rule); such rows contribute 0 points from
this rule rather than erroring.

`model_version = "baseline_rule_v1"` is used deliberately, not
`detector_version` or similar — this establishes the field name the eventual
MLflow-registered model and batch inference will reuse unchanged, even
though the baseline involves no training.

Output written to `ced.gold.baseline_detections`, one row per Gold input row
(27,128), no filtering — consistent with Gold's no-quarantine convention
(ADR-012): a row-count mismatch here is a bug, not a data-quality outcome.

## Rationale
This design maximizes explainability (every flag traces to specific named
rules via the `reason` field) and avoids any leakage from ground truth into
the baseline's own construction, while still producing a genuine
`detection_score`/`detection_flag`/`model_version` contract that later
milestones can build against unchanged.

## Consequences

**Verified result (real end-to-end run, evaluated against
`events_ground_truth.csv`):**
- Precision: **1.0000** (403/403 flagged events were genuine injected
  anomalies; 0 false positives across 27,128 events)
- Recall: **0.7435** (403/542 total injected anomalies caught)
- F1: **0.8529**
- False positive rate: **0.0000**

**Recall by anomaly type:**
- `new_device`: 100% (229/229) — 2-point solo trigger
- `geo_deviation`: 100% (128/128) — 2-point solo trigger
- `amount_spike`: 80.7% (46/57) — only spikes crossing the tier-2 ratio (>5x)
  are caught solo; softer spikes are under-scored
- `channel_deviation`: **0%** (0/128) — structural, by-design limitation,
  not a bug (see below)

**Known limitation — `channel_deviation` is structurally unreachable by this
baseline.** `is_unusual_channel` correctly fires on every single one of the
128 `channel_deviation` anomalies (confirmed: the notebook's `reason`
breakdown shows exactly 128 `is_unusual_channel` firings, matching ground
truth exactly). But it contributes only 1 point, and the flag threshold is 2,
so a channel-deviation anomaly can never flag *on its own* — only if it
happens to co-occur with another signal, which the M3 generator's
single-event-level anomaly injection (technical debt #4) never produces.
This is the direct, correctly-implemented consequence of the deliberate
design choice that a single weak signal should not flag alone. **This is not
being retuned** — raising the channel weight after seeing this result would
be tuning against ground truth after the fact, which the threshold-design
decision above explicitly rejected. It is retained as an honest, named
limitation and framed as a concrete motivator for Milestone 8: an ML model
can learn that weak signals combined with context are still predictive,
without needing a hand-picked cutoff per feature.

**`prior_failed_login_count_24h` rules never fired (0 support in this
dataset).** Per technical debt item #5, only `new_device` has event-type-aware
anomaly injection logic in the M3 generator — there is no injected
failed-login-burst anomaly type. The rule is architecturally sound but
currently untested by available ground truth; revisit if a login-burst
anomaly type is ever added to the generator.

**Two Spark implementation bugs caught during verification, both fixed
before closing the milestone:**
1. `F.array_remove(array, None)` was used intending to strip null entries
   from the `reason` array, but Spark's `array_remove` nulls out the *entire
   array* when the value-to-remove argument is itself `NULL` (a value-equality
   removal, not a null-filter). This silently produced `NULL` for every row's
   `reason` column, undetected until the exploded rule-frequency sanity check
   came back completely empty rather than erroring. Fixed using
   `F.filter(array, lambda x: x.isNotNull())`, which filters by predicate
   instead. **General Spark null-semantics gotcha, not specific to this
   dataset — worth remembering for any future array-building logic in this
   project.**
2. `NameError: name 'spark' is not defined` when the notebook was structured
   in a way that didn't implicitly expose the Databricks runtime `spark`
   session — same root cause as the Bronze notebook fix in Milestone 4.
   Fixed identically: `from databricks.sdk.runtime import spark`. This is now
   a confirmed *recurring* pattern in this project (two independent
   instances), not a one-off — worth checking proactively in any new
   notebook going forward rather than waiting for the `NameError`.

**New dependency:** `pandas` added as a production dependency (`uv add
pandas`) for the local evaluation script — first use of pandas in this
project; needed for the CSV join against ground truth and will likely be
reused by future local evaluation/monitoring scripts.

**New Unity Catalog volume:** `ced.gold.exports`, for baseline detection
output flattened to CSV for local download — kept separate from
`ced.bronze.raw_uploads` (which is scoped to raw input landing per ADR-010)
to keep the Bronze input boundary clean as the project grows more output
artifacts.

## Future Considerations
- If Milestone 8's ML model is evaluated against this same baseline, the
  precision/recall/F1 numbers above are the reference point it must beat —
  particularly on `channel_deviation` recall, where the baseline is at 0% by
  construction.
- If a login-burst anomaly type is ever added to the synthetic generator,
  re-run this evaluation to determine whether the failed-login rules (never
  triggered) are well-calibrated.
- The amount-ratio heuristic (`abs(deviation) / prior_avg`) is a
  mean-relative-magnitude proxy, not a true z-score (no standard deviation
  available in the current feature set) — a limitation inherited from
  Milestone 6's feature scope, not newly introduced here.
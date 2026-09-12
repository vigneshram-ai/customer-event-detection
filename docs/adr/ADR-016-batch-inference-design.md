# ADR-016: Batch Inference Design

## Status
Accepted — implemented and verified, Milestone 10.

## Context
Milestone 9 established an alias-based promotion mechanism:
`ced.models.logistic_regression_detector@champion` now points at a
validated model version. Until something actually consumes that alias,
Milestone 9's mechanism has no real user — it's promotion with nowhere to
go. Milestone 10 closes that loop: load the model by alias, score a batch
of customer events, and write results in the `model_version`-tagged
contract format established since Milestone 7
(`customer_id`, `event_id`, `event_timestamp`, `model_version`,
`detection_score`, `detection_flag`).

## Problem
Several sub-decisions had no obviously-correct default and needed
resolving before implementation:
1. Where do the events to score come from?
2. How should the model be loaded — flavor-specific or generic?
3. How is a continuous `detection_score` obtained, given the model was
   trained as a binary classifier?
4. How should missing feature values be handled at inference time,
   consistent with how the model was trained?
5. Where do detection results live, and how are they written?

## Options Considered

### Sourcing the batch to score
- **A — Genuinely new synthetic event batch**, replayed through
  Bronze→Silver→Gold combined with existing history (so window features
  are correct), requiring Bronze to move from `overwrite` to `append`
  mode (a deviation from ADR-010) plus a new `ingestion_batch` marker
  column. Architecturally the most honest "new events" story, but
  materially more work: new data generation, a Bronze-mode change, a
  full Silver/Gold re-run.
- **B — Reconstruct the exact Milestone 8 held-out test split.** The
  split was computed in-memory in `train_model.py` and never persisted
  (deliberately, per ADR-014, so no table would contain both features
  and labels). Reconstructing it exactly would require re-deriving it
  from `ced.training` labels, which conflicts with the standing rule
  that inference never reads `ced.training`. Possible via a one-time
  bootstrap script that persists only the resulting `event_id` list, but
  adds process complexity for a boundary case.
- **C — Reproducible random sample of existing `ced.gold.customer_events_features`**
  (chosen). No new data generation, no Bronze/ADR-010 conflict, no
  `ced.training` access. Keeps focus on the inference *mechanism*
  (alias-based loading → scoring → contract-compliant output) rather
  than data governance. Explicit trade-off: the scored batch overlaps
  training data, so results here are not a fresh performance
  measurement — that already happened correctly in Milestone 8 against
  the genuine held-out split.

**Decision: Option C.** A reproducible sample (n=500, seed=42) of
`ced.gold.customer_events_features`.

### Model loading
`mlflow.pyfunc.load_model()` — the generic, flavor-agnostic interface,
the same one `mlflow.pyfunc.spark_udf()` would use for distributed
scoring — rather than `mlflow.sklearn.load_model()`. Chosen deliberately
over the flavor-specific loader for consistency with how this project
would eventually need to load models at larger scale.

### Getting a continuous score
The generic `pyfunc.predict()` contract calls the underlying sklearn
model's `.predict()`, which returns the class label (0/1), not a
probability — there's no flavor-agnostic "give me `predict_proba`."
Since `detection_score` is a required contract field (not optional), the
underlying sklearn estimator is unwrapped from the pyfunc wrapper via
`_model_impl.sklearn_model` specifically to call `.predict_proba()`. This
is a deliberate, documented compromise: the *loading* is generic, but the
*probability extraction* is sklearn-specific and would not carry over
unchanged to genuinely distributed `spark_udf`-based scoring. A
model logged at training time as a custom `PythonModel` whose own
`predict()` returns probabilities would remove this compromise — out of
scope for this milestone (would require an M8-level retrain).

A related question came up during design: since the fixed threshold
(0.5) happens to equal sklearn's own default classification boundary,
generic `pyfunc.predict()` alone would produce an identical class label
without any unwrapping. That's true, but relying on it would silently
couple the project's threshold decision to a library default rather than
an explicit, owned value in this pipeline — and would only work by
coincidence of the number chosen. `detection_score` was kept as a
first-class output specifically so the threshold stays a visible,
adjustable decision, and to support future monitoring (score-distribution
drift, severity ranking) that a bare flag cannot.

### Missing feature values
`train_model.py` applies `fillna(0)` to the same `FEATURE_COLS` before
`.fit()`. Inference replicates this exactly, for train/serve parity — any
deviation here would be a worse bug (silent, unthrown skew between what
the model learned on and what it's scored against) than the imputation
choice itself.

On review, the choice is judged reasonable, not merely unavoidable:
`prior_avg_amount_90d` and `amount_deviation_from_prior_avg` are `NULL`
either because the current-row event is non-monetary (structural, per
ADR-012) or because a monetary row has no prior monetary history yet.
Since the synthetic generator never produces a genuinely monetary event
with `amount = 0.0` (that value is reserved as the ADR-011 non-monetary
sentinel), a real prior-amount average of exactly `0` cannot occur
structurally either — so `0` unambiguously signals "no relevant monetary
history," regardless of which of the two NULL causes produced it. The two
causes still collapse to the same encoded value, which remains a
structural limitation (see Technical Debt), but not one likely to mislead
the model given this dataset's actual amount distribution.

### Output location and write mode
New `ced.inference` schema, table `detection_results`:
`customer_id`, `event_id`, `event_timestamp`, `model_version`,
`detection_score`, `detection_flag`, the 8 Gold feature values
(interpretability context), `scored_at`. Written with `mode("overwrite")`
— each run represents "the current batch scored," consistent with how
Bronze/Silver/Gold already behave. Idempotent accumulation
(append-with-dedup-by-`event_id`) is a real future need once genuinely
repeated/incremental batches exist — not solved here.

### Execution model
Scoring pulls the 500-row sample to a pandas DataFrame (`toPandas()`) and
calls sklearn directly. Reasonable at this scale; a materially larger
batch would need a Spark-native path (`pyfunc.spark_udf` or a pandas
UDF) instead of single-node collection — a scalability limitation, not a
correctness issue at this size.

## Decision
Score a reproducible random sample of existing Gold features via
`pyfunc.load_model` (unwrapped for `predict_proba`), fixed 0.5 threshold,
`fillna(0)` matching training exactly, output to
`ced.inference.detection_results`, overwrite per run.

## Rationale
Prioritizes demonstrating the batch-inference *mechanism* — alias-based
model loading with no hardcoded version, scoring, contract-compliant
output — over reproducing exact train/test boundaries or investing
further in synthetic data generation, consistent with this milestone's
stated goal of understanding the full MLOps lifecycle end-to-end rather
than maximizing any single stage's fidelity.

## Consequences
- Detection results from this run are not a model-performance
  measurement; the batch overlaps training data. M8's held-out test-split
  evaluation remains the authoritative performance numbers.
- The `pyfunc` + unwrap pattern for probability extraction is
  sklearn-specific and would need rework for genuinely distributed
  scoring.
- `ced.inference.detection_results` has no historical accumulation yet —
  each run replaces the last.
- The two distinct NULL causes in amount-based features remain
  structurally indistinguishable in the encoded data, accepted as safe
  for this dataset rather than resolved.

## Future Considerations
- A genuinely new/unseen event batch (Option A or B above), if the
  "batch inference against new customer events" resume claim needs
  strengthening beyond the mechanism-level demonstration achieved here.
- Distributed scoring via `pyfunc.spark_udf` for larger batches.
- A custom `PythonModel` logged at training time to make probability
  extraction flavor-agnostic.
- An append/dedup strategy for `ced.inference.detection_results` once
  genuinely incremental batches exist.
- A dedicated indicator feature (e.g. `has_prior_monetary_history`) to
  fully disambiguate the two NULL causes, if ever revisited.
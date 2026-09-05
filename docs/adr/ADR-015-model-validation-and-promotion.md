# ADR-015: Model Validation and Promotion Strategy

## Status
Accepted — Milestone 9, implemented and verified.

## Context
Milestone 8 registered two models (`logistic_regression_detector`,
`xgboost_detector`) to the Unity Catalog model registry, but "registered"
only means versioned and stored — nothing distinguished a model version
that was safe to use from one that wasn't. No mechanism existed to decide
which version a future batch-inference process should load, and no
rollback path existed if a bad version were ever promoted.

Unity Catalog does not support the legacy MLflow model registry's
stage-based promotion (`Staging`/`Production`/`Archived`). The current
mechanism is **named aliases** attached to a specific model version via
`MlflowClient.set_registered_model_alias()`.

## Problem
Define a concrete, automatable gate that a registered model version must
pass before being trusted for inference, and a promotion mechanism that
gives a rollback path — without recomputing any metrics (they are already
logged from Milestone 8) and without introducing complexity this project
can't actually demonstrate (e.g. live shadow evaluation).

## Options Considered

**Gate thresholds:**
- *Match/exceed the M7 baseline's exact precision (1.0000)* — rejected.
  Baseline metrics were computed on the full 27,128-row dataset (untrained,
  no split applies); ML metrics are computed only on the 8,139-row test
  split (Technical Debt #19). Requiring an exact match would compare two
  numbers that are not on the same basis — dishonest, not rigorous.
- *No quantitative gate, manual promotion only* — rejected. Defeats the
  purpose of this milestone and isn't a demonstrable MLOps pattern.
- *Composite/weighted score across many metrics* — rejected for the gate
  itself (see below re: F1 for comparison). Would require inventing a
  weighting scheme with no real basis for a threshold check that just
  needs a floor, not a ranking.
- **Chosen:** three independent floor checks against already-logged
  metrics — `recall_channel_deviation >= 0.95`, `recall >= 0.95`,
  `precision >= 0.90`. `channel_deviation` recall is checked explicitly
  because recovering it from the M7 baseline's structural 0% is the
  entire reason Milestone 8 (and this gate) exists — a future retrain
  must not silently regress it. The precision floor of 0.90 is
  deliberately below the baseline's 1.0000, for the non-like-for-like
  reason above.

**Promotion mechanism:**
- *Stage-based (`Staging`/`Production`)* — rejected. Deprecated by Unity
  Catalog; would not reflect current platform practice.
- **Chosen:** alias-based promotion (`champion`, `challenger`,
  `previous_champion`, `archived` — all project-defined conventions, not
  Unity Catalog built-in concepts; UC alias support itself is the platform
  feature).

**Champion/challenger comparison metric:**
- *`recall_channel_deviation` alone* — rejected. Risks promoting a version
  that regressed elsewhere as long as it holds this one metric.
- *Weighted composite* — rejected, same reasoning as above.
- **Chosen: F1** — already logged for every run, a standard single-number
  answer to "which model is better overall." Ties favor the incumbent
  champion (stability bias — don't replace a working champion over a
  negligible or coincidental difference).

**Scope: which models go through the gate:**
- XGBoost is **not** gated in this milestone. It underperforms
  LogisticRegression on every M8 metric (precision 0.9581 vs. 0.9879,
  recall 0.9816 vs. 1.0000, `amount_spike` recall 0.8235 vs. 1.000) — a
  deliberate scope decision, not an oversight. Gating a model that would
  only ever fail on comparison (there being no champion for it to become)
  doesn't add a new architectural pattern beyond what LogisticRegression
  already demonstrates.

## Decision
Implemented `notebooks/validate_and_promote_model.py`:

1. **Discovery, not assumption.** The script queries
  `search_model_versions(name=...)` for the *latest* registered version of
  `ced.models.logistic_regression_detector`, then reads that version's
  already-logged MLflow metrics via `get_run()`. It does not assume a
  fixed run name or a 1:1 run-to-version mapping — retraining creates new
  runs and new versions, so "latest version" must be resolved dynamically
  each time the script runs, not hardcoded.

2. **Gate.** All three thresholds are checked and reported individually
  (pass/fail per check, not just an overall boolean) — this is what would
  let a future retrain's failure be diagnosed at a glance rather than
  requiring a re-investigation. Any failed check aborts promotion entirely
  (`sys.exit(1)`); no alias is touched.

3. **Promotion, given the gate passes:**
   - No `champion` exists yet → the version becomes `champion` directly.
   - The version already *is* `champion` → no-op (safe to re-run).
   - A different `champion` exists → the version is tagged `challenger`
     **immediately** (this is what makes it a challenger — passing the
     gate and entering comparison against the incumbent), then compared
     to the current champion on F1:
     - **Wins (strictly greater F1):** outgoing champion is tagged
       `previous_champion` (rollback path — reassign `champion` back to
       it); the challenger becomes `champion`; the `challenger` alias is
       removed (it graduated, it's no longer "challenging").
     - **Loses or ties:** the `challenger` alias is removed and the
       version is tagged `archived` instead. This project runs a one-shot
       batch comparison, not a live shadow-deployment evaluation — there
       is no ongoing "still being evaluated" state to preserve for a
       version that already lost its one comparison, so leaving it
       tagged `challenger` indefinitely would misrepresent that an
       evaluation is still in progress.

## Consequences
- Batch inference (Milestone 10+) has a single stable thing to query —
  `ced.models.logistic_regression_detector@champion` — rather than needing
  to know a specific version number or re-derive "which one is good."
- Rollback is a one-line alias reassignment (`champion` → whatever
  `previous_champion` currently points to), not a redeploy.
- **Known limitation:** `archived` is a single alias. Only the *most
  recently* gate-passed-but-losing version carries that tag at any time;
  earlier losing versions remain in the registry (immutable, never
  deleted — full history is recoverable by version number) but lose the
  alias tag once a newer version is archived. A future milestone could
  address this with a naming convention (e.g. per-version tags) if the
  history needs to be queryable via alias alone; not needed to demonstrate
  the pattern here.
- **Known limitation:** the champion/challenger pattern here is atomic and
  batch — it does not implement live shadow inference (running challenger
  against real traffic alongside champion before deciding). That would
  require batch/online inference to exist first (Milestone 10+) and is a
  natural extension, not implemented now.
- XGBoost remains registered in `ced.models` but outside the gate/alias
  system entirely — it is neither promotable nor blocked, simply not
  evaluated by this mechanism. This is a stated scope choice, revisitable
  if a future milestone wants to demonstrate multi-model gating.

## Verified Result
Run against live Databricks (Free Edition), `ced.models.logistic_regression_detector` v1:
# Databricks notebook source
# Milestone 9 — model validation gate and promotion via Unity Catalog aliases.
#
# Reads already-logged MLflow metrics for the LATEST version of
# ced.models.logistic_regression_detector — no recomputation. See ADR-015
# for full rationale; summary of the alias policy below.
#
# GATE (applied to the latest registered version only):
#   recall_channel_deviation >= 0.95
#   recall                   >= 0.95
#   precision                >= 0.90
#   Fails any check -> no alias set, script exits non-zero, nothing touched.
#
# PROMOTION (only reached if the gate passes):
#   - No 'champion' alias exists yet
#       -> latest version becomes 'champion' directly.
#   - Latest version IS already 'champion'
#       -> no-op (re-running the script is safe).
#   - A different 'champion' already exists
#       -> latest version is tagged 'challenger' first (this is what makes
#          it a challenger — passing the gate and being evaluated against
#          the incumbent), THEN compared to champion on F1 (single decisive
#          metric, already logged; ties favor the incumbent — stability
#          bias):
#            - Challenger F1 > champion F1:
#                * outgoing champion -> 'previous_champion' (rollback path:
#                  reassign 'champion' back to that version)
#                * challenger -> 'champion'
#                * 'challenger' alias removed (it graduated)
#            - Challenger F1 <= champion F1:
#                * 'challenger' alias removed
#                * this version -> 'archived' (verdict is final; this
#                  project runs one-shot batch comparison, not live shadow
#                  evaluation, so there is no ongoing "still being
#                  evaluated" state to preserve)
#
# KNOWN LIMITATION (see ADR-015): 'archived' is a single alias, so only the
# MOST RECENT losing version is tagged 'archived' at any time. Earlier
# archived versions keep their version number in the registry (immutable,
# never deleted) but lose the alias tag once a newer version is archived.
# Full loss history therefore lives in the registry's version list, not in
# alias state alone.

import sys

from mlflow.tracking import MlflowClient

client = MlflowClient()

REGISTERED_MODEL_NAME = "ced.models.logistic_regression_detector"

THRESHOLDS = {
    "recall_channel_deviation": 0.95,
    "recall": 0.95,
    "precision": 0.90,
}
COMPARISON_METRIC = "f1"


def get_metrics_for_version(version_number: str) -> dict:
    mv = client.get_model_version(REGISTERED_MODEL_NAME, version_number)
    run = client.get_run(mv.run_id)
    return run.data.metrics


def safe_delete_alias(alias: str) -> None:
    """Delete an alias if it exists; no-op if it doesn't."""
    try:
        client.delete_registered_model_alias(REGISTERED_MODEL_NAME, alias)
    except Exception:
        pass


# --- Find the latest registered version (not tied to a specific run name;
#     retraining creates new runs/versions, so we always gate the newest) ---
versions = client.search_model_versions(f"name='{REGISTERED_MODEL_NAME}'")
if not versions:
    raise RuntimeError(f"No versions found for '{REGISTERED_MODEL_NAME}'.")
latest_version = max(versions, key=lambda v: int(v.version))
latest_metrics = get_metrics_for_version(latest_version.version)

print(f"Evaluating {REGISTERED_MODEL_NAME} v{latest_version.version}\n")

# --- Gate checks: report every check regardless of pass/fail ---
results = []
for metric_key, threshold in THRESHOLDS.items():
    actual = latest_metrics.get(metric_key)
    if actual is None:
        raise RuntimeError(f"Metric '{metric_key}' not found on this run.")
    passed = actual >= threshold
    results.append((metric_key, actual, threshold, passed))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {metric_key}: {actual:.4f} (threshold >= {threshold})")

all_passed = all(passed for _, _, _, passed in results)
print()

if not all_passed:
    print(
        f"GATE FAILED — {REGISTERED_MODEL_NAME} v{latest_version.version} "
        f"NOT promoted. No alias set."
    )
    sys.exit(1)

# --- Promotion decision ---
existing_aliases = client.get_registered_model(REGISTERED_MODEL_NAME).aliases
champion_version = existing_aliases.get("champion")

if champion_version is None:
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", latest_version.version)
    print(
        f"GATE PASSED — no existing champion. "
        f"v{latest_version.version} promoted directly to 'champion'."
    )

elif champion_version == latest_version.version:
    print(f"GATE PASSED — v{latest_version.version} is already 'champion'. Nothing to do.")

else:
    # Passing the gate is what makes this version a challenger, regardless
    # of how the comparison below turns out.
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, "challenger", latest_version.version)
    print(f"v{latest_version.version} tagged 'challenger' (gate passed).")

    champion_metrics = get_metrics_for_version(champion_version)
    challenger_score = latest_metrics[COMPARISON_METRIC]
    champion_score = champion_metrics[COMPARISON_METRIC]

    print(
        f"Comparing challenger v{latest_version.version} "
        f"({COMPARISON_METRIC}={challenger_score:.4f}) vs. "
        f"champion v{champion_version} "
        f"({COMPARISON_METRIC}={champion_score:.4f})"
    )

    if challenger_score > champion_score:
        client.set_registered_model_alias(
            REGISTERED_MODEL_NAME, "previous_champion", champion_version
        )
        client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", latest_version.version)
        safe_delete_alias("challenger")
        print(
            f"CHALLENGER WINS — v{latest_version.version} promoted to "
            f"'champion'. Former champion v{champion_version} tagged "
            f"'previous_champion' (rollback: reassign 'champion' to that "
            f"version). 'challenger' alias retired."
        )
    else:
        safe_delete_alias("challenger")
        client.set_registered_model_alias(REGISTERED_MODEL_NAME, "archived", latest_version.version)
        print(
            f"CHAMPION HOLDS — v{champion_version} outperforms or ties "
            f"v{latest_version.version} on {COMPARISON_METRIC}. "
            f"v{latest_version.version} tagged 'archived' (comparison is "
            f"final for this version — no ongoing shadow evaluation exists "
            f"in this project)."
        )

# --- Final alias state, for verification ---
final_aliases = client.get_registered_model(REGISTERED_MODEL_NAME).aliases
print("\nFinal registered aliases:")
for alias, version in sorted(final_aliases.items()):
    print(f"  {alias} -> v{version}")

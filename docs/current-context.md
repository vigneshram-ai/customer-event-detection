# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–13 are **complete and verified**. Milestone 13 empirically
tested security and secrets management against the live Databricks Free
Edition workspace: secret scopes, Unity Catalog RBAC, and audit logging.
All three were found genuinely functional — better than assumed. No
pipeline code changed. Milestone 14 (CI/CD extension) has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 12; unaffected by
  Milestone 13 since no project code changed this milestone.
- **Databricks CLI now installed locally** (1.16.1, via `winget`), added to
  User PATH, authenticated against the Free Edition workspace via
  token-based `configure --token`.
- **The project's PAT had silently expired** — discovered by chance during
  Milestone 13's CLI setup (`auth profiles` showed `Valid: NO`). A new PAT
  was generated and both `.env` and Airflow's `databricks_default`
  connection were updated. No expiry monitoring exists; this was luck, not
  detection. Flagged as a real, unresolved gap.
- **Databricks secret scopes verified working**: scope `ced-secrets`
  created; write/read/redaction all confirmed via CLI + notebook. **The
  project's PAT was deliberately NOT migrated into it** — `dbutils.secrets`
  is only reachable from inside the Databricks runtime, and the PAT's job
  is to let processes *outside* that runtime (local scripts, Airflow)
  authenticate in. Moving it would be circular. Full reasoning in ADR-007.
- **Unity Catalog RBAC verified working, overturning a Milestone-1
  assumption.** Free Edition is NOT single-user in the way previously
  documented — it supports multiple human identities and service
  principals, with fully functional, correctly hierarchical
  `GRANT`/`REVOKE` enforcement. A service principal (`test_sp`) was created,
  granted a scoped chain on `ced` / `ced.training`, and successfully
  authenticated independently via OAuth client credentials — confirmed via
  both a successful read of `ced.training` and a correctly-denied read of
  `ced.bronze`.
- **`system.access.audit` confirmed populated and usable** — no explicit
  enablement step needed on this workspace. Captured this milestone's own
  RBAC probe activity with correct, detailed attribution.
- **`docs/adr/ADR-007-security-secrets-management.md`** (new) — full
  findings and decisions for all three areas above.
- All Milestone 1–12 artifacts unchanged — generators, ingestion,
  Bronze/Silver/Gold, baseline detector, ground-truth loading, model
  training/registry, batch inference, monitoring, and both Airflow DAGs
  all run exactly as they did at the close of Milestone 12.
- `pyproject.toml` unchanged. The Databricks CLI is a standalone binary,
  not a Python package — not tracked as a project dependency, same
  category as Git.

## Key Design Decisions From Milestone 13 (do not silently revisit — full detail in ADR-007)
- **PAT is not migrated to a Databricks secret scope.** This is a
  deliberate, reasoned decision based on a genuine architectural
  constraint (bootstrap circularity — you can't fetch the credential that
  lets you fetch credentials from the very system that credential
  unlocks), not an unexplored option or oversight. The secret scope
  remains created and validated for the use case it's actually suited to
  (a credential a *notebook* needs mid-execution), which doesn't currently
  exist in this project.
- **Unity Catalog RBAC is real and functional on Free Edition — the
  "single-user" assumption carried since Milestone 1 was wrong.** Multiple
  identities, service principals, and hierarchical grant enforcement all
  confirmed via direct testing (not documentation). This means
  `ced.training` isolation via a dedicated identity is now
  **implementable**, not a permanent limitation — though it is **not
  implemented this milestone**. A working, correctly-scoped service
  principal (`test_sp`) already exists as proof; migrating
  `train_model.py`/`validate_and_promote_model.py` to actually run as it
  is deferred future work, not an open question.
- **`system.access.audit` is real, usable audit infrastructure** —
  populated by default, capturing detailed per-event records. Documented
  as available; no dashboard or query built against it yet.
- **This was a verification-and-documentation milestone, not an
  implementation milestone.** Consistent with the project's established
  discipline (same pattern as Milestone 12's serverless-compute
  verification): empirically test platform capability before designing or
  building against it. No pipeline, DAG, or notebook code changed.
- **CI/CD extension is explicitly Milestone 14, not part of this
  milestone** — user directed this scoping explicitly at the start of
  Milestone 13.

## Key Design Decisions From Milestone 12 (do not silently revisit — full detail in ADR-002 / ADR-018)
Unchanged from prior snapshot — two-DAG split via the `champion` alias;
baseline detector excluded from both DAGs; WSL2-native Airflow execution;
`DatabricksSubmitRunOperator` + multi-task `tasks=[...]` shape required for
Free Edition serverless compute; champion/challenger tie-break verified
live (Technical Debt #20 resolved); both DAGs `schedule=None` by deliberate
design; Technical Debt #29 (monitoring `run_id` not deterministic). See
prior snapshot or ADR-002/ADR-018 for full detail.

## Key Design Decisions From Milestone 11 (do not silently revisit — full detail in ADR-017)
Unchanged from prior snapshot. See prior snapshot or
`docs/adr/ADR-017-monitoring-strategy.md`.

## Key Design Decisions From Milestone 10 (do not silently revisit — full detail in ADR-016; see M11 correction)
Unchanged from prior snapshot.

## Key Design Decisions From Milestone 9 (do not silently revisit — full detail in ADR-015)
Unchanged from prior snapshot.

## Key Design Decisions From Milestones 5–8
Unchanged from prior snapshots — see `docs/project-status.md` and
ADR-011 through ADR-014 for full detail.

## Environment Snapshot
- Windows, with a dedicated WSL2 Ubuntu distro used for Airflow only
- Project code: `uv` 0.12.5, project Python 3.11.16, unchanged
- Airflow: 3.3.1, Python 3.12.13 (WSL2 venv), Fernet key present
  (non-default — confirmed this milestone, not deeply investigated further)
- **New this milestone**: Databricks CLI 1.16.1 installed locally via
  `winget`, added to User PATH, authenticated (`DEFAULT` profile,
  token-based)
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models`, `inference`, `monitoring`
- **New this milestone**: Databricks secret scope `ced-secrets` (created,
  validated, currently unused by any pipeline)
- **New this milestone**: service principal `test_sp`, Application Id
  `374365a1-96f6-4597-af4c-a82aec75fff6`, OAuth client credentials
  generated, scoped grants on `ced` (`USE CATALOG`) and `ced.training`
  (`USE SCHEMA`, `SELECT`) — not adopted into any pipeline yet
- **New this milestone**: `system.access.audit` confirmed populated,
  regional, 365-day default retention
- MLflow: Databricks-managed workspace experiment
  `/Shared/customer_event_detection_m8`
- Model registry aliases: unchanged from Milestone 12
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost`, `mlflow`, `evidently` are Databricks-side only.
  `apache-airflow`, `apache-airflow-providers-databricks` are WSL2-venv
  only. Databricks CLI is standalone local tooling. None of these are
  `pyproject.toml` dependencies except the first three.
- **PAT rotated this milestone** — the prior PAT had silently expired;
  new PAT generated, `.env` and Airflow's `databricks_default` connection
  both updated. Stored in `.env` (git-ignored) and Airflow's
  Fernet-encrypted connection store — deliberately NOT moved to the
  Databricks secret scope (see ADR-007 for why).

## Known Gaps (do not silently "fix" these — ask the user first)
- Time-of-day deviation — designed and partially implemented, then
  removed.
- ~~**`ced.training` access restricted to a training-job identity — 📐
  DESIGNED ONLY, cannot be enforced on Free Edition (single-user).**~~
  **CORRECTED Milestone 13** — empirically proven enforceable. Status is
  now: a working, correctly-scoped service principal exists and was
  verified; the training pipeline has not yet been migrated to use it.
  See ADR-007.
- **Milestone 8's train/test split is row-level, not customer-level** —
  Technical Debt #18.
- **Baseline (M7) and ML model (M8) metrics are on different evaluation
  bases** — Technical Debt #19.
- **The `archived` alias only tracks the single most-recent losing
  version** — Technical Debt #21.
- **Live/shadow evaluation for champion/challenger doesn't exist** — 📐
  DESIGNED as a future extension in ADR-015.
- **Milestone 10's batch is a sample of existing Gold data, not
  genuinely new/unseen events** — Technical Debt #22.
- **`predict_proba` extraction via sklearn-specific unwrap** — Technical
  Debt #23.
- **`ced.inference.detection_results` uses `overwrite`, no historical
  accumulation** — Technical Debt #24.
- **`fillna(0)` collapses two distinct NULL causes in amount-based
  features** — Technical Debt #25.
- **Milestone 10's exact `model_version` output string was inferred, not
  directly observed** — Technical Debt #26.
- **Monitoring's Evidently-dict extraction depends on an internal,
  non-public schema** — Technical Debt #27.
- **`ced.inference.detection_results`'s persisted feature columns are
  raw, not imputed** — Technical Debt #28.
- **Monitoring's `run_id` is a fresh UUID per run, not derived
  deterministically from the Airflow run context** — Technical Debt #29.
- **No real (cron-based) Airflow schedule exists for either DAG** — 📐
  DESIGNED but deliberately not implemented (no persistent scheduler
  survives a laptop shutdown on the WSL2 setup).
- **NEW — PAT lifecycle has no monitoring or rotation process.** This
  milestone's expired-PAT discovery was accidental. A real gap if any
  future milestone introduces scheduled/unattended execution.
- **NEW — the PAT remains the credential for local scripts and Airflow,
  not SP OAuth client credentials.** This is a deliberate, not-yet-taken
  next step (distinct from the secret-scope decision) — see ADR-007
  Future Considerations.
- **NEW — `test_sp` (the verification service principal) is not yet
  formally adopted or deleted.** Currently harmless but unused; a cleanup
  decision is pending.
- **NEW — `system.access.audit` is verified and populated but nothing
  consumes it yet.** No dashboard or scheduled query exists.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Claude Desktop workflow: never assume direct local file/execution access.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  Milestone 13 applied this to platform capability, not pipeline output:
  every claim (secret scope works, RBAC works, audit log works) was
  backed by actual command output, including negative-test confirmation
  (the SP correctly denied access to `ced.bronze`), not just the
  positive case.
- **Verify library/platform internals empirically before building against
  them** — Milestone 13 is the clearest instance of this principle yet:
  three separate assumptions carried since Milestone 1 were tested and
  two were found to be simply wrong (RBAC "single-user" limitation, and
  the assumption that audit logs would require special enablement).
  Assumptions that turn out to be incorrect are corrected in the
  documentation, not just noted as "still assumed."
- **Design proposals should be treated as genuinely open to challenge,
  not rubber-stamped** — this milestone's "move PAT to secret scope"
  proposal was reconsidered and correctly walked back once the bootstrap
  circularity was identified, rather than implemented as originally
  agreed.

## Immediate Next Step
Milestone 13 is closed. Milestone 14 (CI/CD extension) is next, per user
direction given at the start of this milestone. Not yet scoped in detail —
do not begin without explicit user confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-002-airflow-orchestration-layer.md` — Airflow selection
  rationale
- `docs/adr/ADR-007-security-secrets-management.md` — secrets, RBAC, and
  audit logging findings and decisions (new, Milestone 13)
- `docs/adr/ADR-009` through `ADR-017` — see prior snapshots for
  individual summaries
- `docs/adr/ADR-018-milestone-12-orchestration.md` — two-DAG split, WSL2
  environment change, serverless compute compatibility finding
- `README.md` — public-facing summary (kept minimal, accurate)
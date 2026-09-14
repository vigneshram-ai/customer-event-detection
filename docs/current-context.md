# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–12 are **complete and verified**. Milestone 12 built real
Airflow orchestration — two DAGs, `ced_inference_pipeline` and
`ced_training_pipeline` — replacing the temporary smoke-test DAG from
Milestone 1. Both DAGs ran end-to-end successfully with verified output.
Milestone 13 has **not** started.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 12.
- **Environment change, documented not silently patched**: Airflow no
  longer runs via Docker Compose on this laptop — Docker Desktop's own
  resource overhead made the machine unusable, independent of Airflow
  itself. Airflow does not support native Windows Python installation
  either (a hard platform restriction). Airflow 3.3.1 now runs natively
  inside a dedicated WSL2 Ubuntu distro (Python 3.12 venv, `airflow
  standalone`, SQLite, `SequentialExecutor`). This reverses the "Windows
  native, no WSL2 terminal use" principle stated since Milestone 1 — see
  ADR-018 for full rationale. The `dags_folder` points at the
  Windows-mounted project path, so DAG files remain version-controlled in
  the main repo.
- **Airflow only runs while manually started** — no persistent scheduler
  survives closing the WSL2 shell or shutting down the laptop. Both DAGs
  use `schedule=None` (manual trigger) as a direct, reasoned consequence
  of this, not a placeholder.
- All Milestone 1–11 artifacts unchanged: generators, ingestion,
  Bronze/Silver/Gold, baseline detector, ground-truth loading,
  LogisticRegression/XGBoost training, validation gate and alias-based
  promotion, batch inference, and monitoring are all as previously
  recorded.
- **New in Milestone 12**:
  - `airflow/dags/ced_inference_pipeline.py` — 5 tasks (`bronze_ingestion
    >> silver_transformation >> gold_feature_engineering >>
    batch_inference >> monitoring`), `schedule=None`, `retries=1`.
  - `airflow/dags/ced_training_pipeline.py` — 2 tasks (`train_model >>
    validate_and_promote_model`), `schedule=None`, `retries=1`.
  - Both use `DatabricksSubmitRunOperator` with the multi-task
    `tasks=[...]` shape (no cluster spec) — the only pattern that works
    against Databricks Free Edition serverless compute. See serverless
    finding below.
  - `docs/adr/ADR-002-airflow-orchestration-layer.md` (new — pending since
    Milestone 1, now written) and
    `docs/adr/ADR-018-milestone-12-orchestration.md` (new).
  - `00_environment_smoke_test.py` and `99_databricks_serverless_test.py`
    deleted — both served their purpose, fully documented in ADR-018.
- **Databricks side, new state**:
  - `ced.monitoring.batch_quality_report`: 237 rows total (158 from
    Milestone 11's two manual runs + 79 from Milestone 12's orchestrated
    run).
  - Model registry: `logistic_regression_detector` v2 now exists,
    trained via `ced_training_pipeline`, tagged `archived` after tying
    champion v1 on F1 and losing the incumbent tie-break. `champion`
    remains v1.
  - No other Databricks-side state changed structurally — same schemas,
    same tables, same underlying notebooks (now orchestrated rather than
    manually run).
- `pyproject.toml` unchanged — the Databricks Airflow provider
  (`apache-airflow-providers-databricks`) is installed only inside the
  WSL2 Airflow venv, not the project's `uv` environment.

## Key Design Decisions From Milestone 12 (do not silently revisit — full detail in ADR-002 / ADR-018)
- **Two-DAG split, not one combined DAG.** `ced_inference_pipeline` and
  `ced_training_pipeline` are independently triggered and not chained.
  Retraining is treated as a deliberate, reviewed event, not something
  that fires on every inference run — chaining them would retrain against
  the same static dataset every run, adding noise to the model registry
  with no new information. The two DAGs are connected only through the
  Unity Catalog `champion` alias: `ced_training_pipeline` updates it;
  `ced_inference_pipeline` always reads whichever version currently holds
  it, with no direct Airflow-level awareness of training runs.
- **Baseline detector excluded from both DAGs** — it's a one-time
  Milestone 7 analytical comparison, not part of the production inference
  path.
- **`ced_training_pipeline` assumes Gold is already current** — it does
  not re-run Bronze/Silver/Gold itself. This was a deliberate choice over
  an implicit cross-DAG dependency on `ced_inference_pipeline`'s schedule.
- **WSL2-native execution, not Docker.** Airflow does not support native
  Windows Python at all (hard platform check). The Milestone 1 Docker
  Compose setup could not run on this laptop (Docker Desktop's own
  overhead, independent of Airflow). Resolution: Airflow 3.3.1 native
  inside WSL2 Ubuntu — Python 3.12 venv, `airflow standalone`, SQLite,
  `SequentialExecutor`. This is a genuine, documented reversal of the
  "Windows native, no WSL2" principle stated since Milestone 1, made
  necessary by a real resource constraint — not a silent patch.
- **Databricks Free Edition serverless compute — empirically resolved.**
  `DatabricksNotebookOperator` cannot be used at all against Free Edition
  (requires a cluster reference; a brief upstream serverless-support PR
  was reverted before the currently-installed provider version).
  `DatabricksSubmitRunOperator`'s legacy single-task shorthand
  (`notebook_task=`) also fails, confirmed via a real `400
  INVALID_PARAMETER_VALUE` API error whose message pointed directly at
  the fix: the multi-task `tasks=[...]` array shape, with no cluster
  field anywhere. This was verified with a minimal single-task test DAG
  before building the real pipelines, then confirmed again at full scale
  across all 7 production tasks (5 in inference, 2 in training).
- **First live verification of the champion/challenger comparison
  branch** (previously Technical Debt #20, unverified since Milestone 9).
  `ced_training_pipeline`'s run trained v2, which passed all three gate
  thresholds and tied champion v1 exactly on F1 (0.9939 vs. 0.9939). The
  documented tie-break rule (ADR-015: "ties favor the incumbent champion")
  correctly held v1 as champion and tagged v2 `archived`. This is now
  confirmed-correct behavior under a real tie, not just confirmed
  code-path execution. **Technical Debt #20 is resolved.**
- **Both DAGs use `schedule=None` (manual trigger), not a placeholder.**
  The WSL2-native Airflow instance has no persistent scheduler surviving
  a laptop shutdown — a configured cron schedule would silently never
  fire in practice. This is an explicit, reasoned decision, documented in
  ADR-002.
- **New Technical Debt #29**: monitoring's `run_id` is a fresh UUID per
  run, not derived deterministically from Airflow's run context. A
  task-level retry after a partial failure could in principle
  double-write a batch under a new `run_id`. Low practical risk currently
  since both DAGs are manually triggered — flagged for revisit if either
  DAG ever moves to a real schedule.
- **Verified results**: `ced_inference_pipeline` — all 5 tasks succeeded;
  fresh timestamps confirmed across Bronze/Gold/inference tables;
  monitoring table grew by exactly 79 rows (158 → 237), confirming a
  single clean run with no double-write; Silver `_rejects` tables at 0.
  `ced_training_pipeline` — both tasks succeeded; champion/challenger
  tie-break confirmed correct. CI confirmed green.

## Key Design Decisions From Milestone 11 (do not silently revisit — full detail in ADR-017)
Unchanged from prior snapshot — Evidently used directly for every
monitoring metric; auto-selected drift tests, not forced PSI; Milestone
10's batch treated as current-under-monitoring with explicit
negative-control framing; the Milestone 10 feature-imputation correction
(Technical Debt #28); Evidently's `report.dict()` schema verified
empirically; two `FAIL` statuses interpreted as benign structural
properties, not defects. See prior snapshot or `docs/adr/ADR-017-monitoring-strategy.md`
for full detail.

## Key Design Decisions From Milestone 10 (do not silently revisit — full detail in ADR-016; see M11 correction)
Unchanged from prior snapshot — sample-based batch (n=500, seed 42), not
genuinely new/unseen events; generic `pyfunc.load_model` with sklearn
unwrap for `predict_proba`; `model_version` resolved at scoring time;
output to `ced.inference.detection_results` with `mode("overwrite")`. See
prior snapshot for full detail.

## Key Design Decisions From Milestone 9 (do not silently revisit — full detail in ADR-015)
Unchanged from prior snapshot, **with one update**: the champion/challenger
comparison branch is **no longer unverified** — see Milestone 12 above.
Gate reads already-logged metrics only, never recomputes; three thresholds
(`recall_channel_deviation >= 0.95`, `recall >= 0.95`, `precision >= 0.90`);
alias-based promotion; F1 comparison with incumbent-favoring tie-break;
`challenger` assigned immediately on gate-pass.

## Key Design Decisions From Milestones 5–8
Unchanged from prior snapshots — see `docs/project-status.md` and
ADR-011 through ADR-014 for full detail.

## Environment Snapshot
- Windows, with a dedicated WSL2 Ubuntu distro used for Airflow only
  (separate from the `docker-desktop` utility distro) — reverses the
  prior "no WSL2 terminal use" principle, see ADR-018
- Project code: `uv` 0.12.5, project Python 3.11.16, unchanged, still
  Windows-native
- Airflow: 3.3.1, Python 3.12.13 (WSL2 venv), `airflow standalone`
  (SQLite, `SequentialExecutor`), `apache-airflow-providers-databricks`
  7.18.1, manually started per session (no persistent scheduler)
- Docker Desktop: no longer used for Airflow; retained only as WSL2's own
  backend
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models`, `inference`, `monitoring`
- Volumes: `bronze.raw_uploads`, `gold.exports`, `training.raw_labels`
- MLflow: Databricks-managed workspace experiment
  `/Shared/customer_event_detection_m8`
- Model registry aliases: `ced.models.logistic_regression_detector` v1 →
  `champion`, v2 → `archived` (new, Milestone 12); `ced.models.xgboost_detector`
  v1 → no alias (unchanged)
- `ced.inference.detection_results`: 500 rows, 12 flagged, fresh
  timestamps confirmed post-Milestone-12 run (feature-column caveat:
  Technical Debt #28, unchanged)
- `ced.monitoring.batch_quality_report`: 237 rows (158 pre-M12 + 79 from
  the Milestone 12 orchestrated run)
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost`, `mlflow`, `evidently` are Databricks-side only.
  `apache-airflow`, `apache-airflow-providers-databricks` are WSL2-venv
  only — none of these are `pyproject.toml` dependencies.
- PAT stored in `.env` (git-ignored); Databricks connection also
  configured separately inside Airflow (`databricks_default`, via the
  Airflow UI, same PAT)

## Known Gaps (do not silently "fix" these — ask the user first)
- Time-of-day deviation — designed and partially implemented, then
  removed.
- **`ced.training` access restricted to a training-job identity — 📐
  DESIGNED ONLY, cannot be enforced on Free Edition (single-user).**
- **Milestone 8's train/test split is row-level, not customer-level** —
  Technical Debt #18.
- **Baseline (M7) and ML model (M8) metrics are on different evaluation
  bases** — Technical Debt #19.
- ~~**Milestone 9's champion-vs-challenger comparison branch is unverified
  against live output**~~ — **RESOLVED Milestone 12**, see above.
- **The `archived` alias only tracks the single most-recent losing
  version** — Technical Debt #21.
- **Live/shadow evaluation for champion/challenger doesn't exist** — 📐
  DESIGNED as a future extension in ADR-015.
- **Milestone 10's batch is a sample of existing Gold data, not
  genuinely new/unseen events** — Technical Debt #22. Still the reason
  Milestone 11's near-zero drift result is a negative control, not a
  genuine finding.
- **`predict_proba` extraction via sklearn-specific unwrap** — Technical
  Debt #23.
- **`ced.inference.detection_results` uses `overwrite`, no historical
  accumulation** — Technical Debt #24. Not addressed by adding
  orchestration in Milestone 12.
- **`fillna(0)` collapses two distinct NULL causes in amount-based
  features** — Technical Debt #25.
- **Milestone 10's exact `model_version` output string was inferred, not
  directly observed** — Technical Debt #26.
- **Monitoring's Evidently-dict extraction depends on an internal,
  non-public schema** — Technical Debt #27.
- **`ced.inference.detection_results`'s persisted feature columns are
  raw, not imputed** — Technical Debt #28.
- **NEW — Monitoring's `run_id` is a fresh UUID per run, not derived
  deterministically from the Airflow run context** — Technical Debt #29.
  A task retry after partial failure could double-write a batch. Low risk
  currently (manual trigger only); revisit if either DAG moves to a real
  schedule.
- **No real (cron-based) Airflow schedule exists for either DAG** — 📐
  DESIGNED but deliberately not implemented; the WSL2-native Airflow
  instance has no persistent scheduler surviving a laptop shutdown, so a
  configured schedule would silently never fire. Both DAGs use
  `schedule=None` as an explicit, reasoned decision.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output.
- Distinguish IMPLEMENTED / DESIGNED / FUTURE explicitly, always.
- Update `docs/project-status.md` after every milestone.
- Claude Desktop workflow: never assume direct local file/execution access.
- **Read sanity-check output carefully, don't just confirm it "ran"** —
  Milestone 12's verification (fresh timestamps, exact +79 row count on
  monitoring, `_rejects` still at 0) is the latest instance of this
  discipline, applied to an orchestration run rather than a notebook run.
- **When implementation reveals a preprocessing dependency between
  stages, go read the actual upstream code rather than choosing an
  independent approach** — unchanged principle, not specifically exercised
  this milestone but still in effect.
- **Verify library/platform internals empirically before building against
  them** — Milestone 12's serverless compute finding is the latest
  instance: the working `tasks=[...]` pattern was confirmed via a real
  API error message and a minimal test DAG, not assumed from documentation.
- **Design proposals should be treated as genuinely open to challenge,
  not rubber-stamped** — Milestone 12's environment path (WSL2 vs.
  trimming Docker vs. downgrading Airflow) was explicitly weighed with
  trade-offs stated before implementation began.

## Immediate Next Step
Milestone 12 is closed. Next milestone (13 onward per the approved
roadmap) not yet scoped in detail — do not begin without explicit user
confirmation.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-002-airflow-orchestration-layer.md` — Airflow selection
  rationale (new, Milestone 12)
- `docs/adr/ADR-009` through `ADR-017` — see prior snapshots for
  individual summaries (unchanged this milestone)
- `docs/adr/ADR-018-milestone-12-orchestration.md` — two-DAG split,
  WSL2 environment change, serverless compute compatibility finding (new,
  Milestone 12)
- `README.md` — public-facing summary (kept minimal, accurate)
# Current Context — Resume-Here Snapshot

_Purpose: if a new chat/session starts, read this file first to know exactly where the
project stands, without re-deriving it from conversation history._

## Where We Are
Milestones 1–14 are **complete and verified**. Milestone 15 (Docker /
Databricks Container Services, scoped to the training workload) is
**closed as 📐 DESIGNED ONLY** — a `Dockerfile`, a script-task adaptation
of the real `train_model.py`, and an annotated Databricks Jobs API payload
were all written, but nothing was built, run, or deployed. Docker Desktop
on the dev machine became unusably slow and hung the machine; the user
explicitly chose to leave that unresolved rather than fix it before
closing the milestone. Full reasoning and status in
`docs/adr/ADR-020-docker-container-services.md`. Milestone 16 has **not**
started and is not yet scoped.

## What Is Actually True Right Now
- The repo exists locally and on GitHub (`main` branch).
- CI is confirmed green on `main` through Milestone 14 — 3 jobs
  (`lint-and-test`, `dag-integrity`, `databricks-smoke-test`), all passing.
  **Unaffected by Milestone 15** — no CI-relevant code changed, and CI was
  not re-run this milestone.
- **`test_sp` (created in Milestone 13) authenticates live from GitHub
  Actions** via OAuth M2M (Milestone 14). Still not adopted into the
  training pipeline itself — unaffected by Milestone 15.
- **`notebooks/train_model.py` and the live Airflow-orchestrated training
  path are completely unchanged by Milestone 15.** Training still runs as
  a notebook on Databricks serverless compute, exactly as verified in
  Milestone 8. `training/train_model_job.py` is a new, parallel,
  **never-executed** file — not a replacement, not adopted into any DAG.
- **Docker Desktop, on the dev machine, is not functional** — it became
  unusably slow and hung the machine during Milestone 15. `docker build`
  was never successfully run. The user explicitly declined to troubleshoot
  further (e.g. installing Docker Engine directly inside the existing
  WSL2 distro was identified as a plausible fix but not attempted).
- **`docker/train-job/Dockerfile` has never been built.** It extends
  `databricksruntime/standard:17.3-LTS` and pins `mlflow-skinny==3.8.1`,
  `pandas==2.2.3`, `scikit-learn==1.6.1`, `xgboost==3.4.1` — versions read
  directly from `%pip freeze` against the live training notebook, so the
  *intended* contents are grounded in real data even though the build
  itself is unverified.
- **The `17.3-LTS` base image tag is an assumption, not a verified
  match** for the live pipeline's serverless environment version 5
  (Ubuntu 24.04.3 LTS, Python 3.12.3, Databricks Connect 18 — confirmed
  Sept 2026). There is no official Databricks-published mapping between
  serverless environment versions and classic Databricks Runtime version
  numbers; 17.3 LTS was chosen only as the nearest reasonable equivalent
  (current LTS, Python 3.12-based).
- **`training/train_model_job.py` has exactly two deliberate deviations**
  from the verified `notebooks/train_model.py` source: (1) the
  `%pip install xgboost` + `dbutils.library.restartPython()` cell is
  removed, since the (unbuilt) image would bake xgboost in at build time
  instead; (2) `from databricks.sdk.runtime import spark` is replaced with
  `SparkSession.builder.getOrCreate()`, the documented pattern for
  non-notebook Databricks Job `spark_python_task` execution, vs. the
  notebook-context magic-import pattern the real notebook uses. Every
  other line (feature columns, the in-memory join and its ADR-014
  row-count assertion, the stratified split, the baseline reference run,
  both training runs, registered model names) is unchanged from the real
  M8 source — this was a faithful adaptation of actual code, not an
  invented reconstruction.
- **`scripts/dcs_job_spec.json` is not a submittable API payload as-is.**
  It carries `_*_note` annotation keys (not part of the real Databricks
  Jobs API schema) documenting every placeholder (registry URL, workspace
  path, node type, running identity) and the single largest unverified
  assumption: whether `SINGLE_USER` access mode + `docker_image` + Unity
  Catalog table access actually combine cleanly on real DCS compute.
- Databricks Container Services (DCS) itself was never attempted against
  any real workspace this milestone. A 14-day free trial workspace with
  classic compute was explicitly considered and explicitly declined by
  the user, in favor of keeping Milestone 15 a documented design exercise
  rather than a throwaway verified run.
- Full detail in `docs/adr/ADR-020-docker-container-services.md`.
- All Milestone 1–14 artifacts unchanged — generators, ingestion,
  Bronze/Silver/Gold, baseline detector, ground-truth loading, model
  training/registry, batch inference, monitoring, both Airflow DAGs, and
  the CI/CD pipeline all run exactly as they did at the close of
  Milestone 14.
- `pyproject.toml` unchanged. Docker is not, and (had the image been
  built) would not become, a `pyproject.toml`-tracked dependency — same
  category as the Databricks CLI and Git: standalone local tooling.

## Key Design Decisions From Milestone 15 (do not silently revisit — full detail in ADR-020)
- **Docker adoption was scoped specifically to Databricks Container
  Services (DCS), targeting the training workload — not a client-side
  container.** Containerizing a script that merely calls Databricks via
  SDK/REST (e.g. the generator, or the M14 CI smoke-test script) was
  identified as the lower-risk, fully-verifiable-on-Free-Edition option
  and explicitly set aside at the user's direction, because it doesn't
  exercise DCS, the specific feature the user wanted to learn.
- **A 14-day free trial Databricks workspace with classic compute was
  considered and explicitly declined**, in favor of keeping this a
  documented design exercise rather than a throwaway verified run. This
  means no part of the DCS deployment path has real verified status, by
  deliberate choice, not oversight.
- **`train_model.py` was chosen over `batch_inference.py` or the
  generator** as the workload to re-platform, because "lock the
  environment so it's immune to platform runtime drift" is a materially
  stronger, more specific architectural argument for training specifically
  than for a lighter-weight script.
- **The Docker Desktop performance blocker was deliberately left
  unresolved.** The user was offered a plausible fix (Docker Engine
  directly inside the existing WSL2 distro, bypassing Docker Desktop's
  GUI/VM overhead) and explicitly chose not to pursue it. Do not assume
  this gets silently fixed in a future milestone — it's an open,
  acknowledged gap.
- **This was a design-and-learning milestone, not an implementation
  milestone**, by explicit user choice at the point of scoping (asked
  directly: build+verify locally vs. design-only; user chose design-only
  even before the Docker Desktop problem arose). The Docker Desktop
  failure reinforced that choice but did not cause it.

## Key Design Decisions From Milestone 14 (do not silently revisit — full detail in ADR-019)
- **Airflow installed only inside the `dag-integrity` CI job's own
  throwaway environment, never added to `pyproject.toml`.** Consistent
  with ADR-018's treatment of Airflow as environment-specific tooling
  (same category as the Databricks CLI). This was a deliberate choice
  among the options considered, not an oversight.
- **Live smoke test authenticates as `test_sp`, not the personal PAT.**
  Considered and rejected using the PAT for this — narrower blast radius
  matters more than reusing an existing credential, especially since
  `test_sp` already had exactly the right least-privilege grants sitting
  unused since Milestone 13.
- **`databricks-smoke-test` runs on `push` to `main` only, never on
  `pull_request`.** A public repo can receive PRs from anyone, including
  forks; live-workspace secrets must never be reachable from a
  PR-triggered run. Confirmed empirically — the job does not appear at
  all in a PR's checks.
- **No deploy automation added.** Considered and explicitly rejected:
  there is no persistent orchestration target to deploy to (both DAGs
  remain `schedule=None` per ADR-018), so auto-triggering anything on
  merge would be automation without a real destination.
- **No Docker CI stage added.** Nothing in the architecture was
  containerized at the time (M14) to satisfy the word "CD" would have been
  technology without genuine architectural purpose. (Superseded in scope,
  not reversed, by Milestone 15 — see above; M15 still did not add
  anything to CI.)
- **This was a CI/testing-depth milestone, not a pipeline-implementation
  milestone.** No `airflow/dags/*.py` or `notebooks/*.py` files changed.

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
  (non-default, confirmed Milestone 13, not deeply investigated further)
- **WSL2 note (Milestone 14)**: the distro's bare `python3` resolves to
  3.14, not 3.12 — `python3.12-venv` (via `apt`) and explicit `python3.12`
  invocation are needed for any ad hoc local venv work (e.g. reproducing
  the `dag-integrity` CI job). Does not affect the real Airflow venv,
  which is already correctly on 3.12.13.
- Databricks CLI 1.16.1 installed locally via `winget`, added to User
  PATH, authenticated (`DEFAULT` profile, token-based)
- GitHub Actions repo secrets `DATABRICKS_HOST`, `DATABRICKS_SP_CLIENT_ID`,
  `DATABRICKS_SP_CLIENT_SECRET` — used only by the `databricks-smoke-test`
  CI job, on `push` to `main` only
- Git remote connected, Git version 2.55.0.windows.4
- Databricks Free Edition workspace (serverless compute only):
  `https://dbc-01205ae9-f87b.cloud.databricks.com/`
- Unity Catalog: catalog `ced`, schemas `bronze`, `silver`, `gold`,
  `training`, `models`, `inference`, `monitoring`
- Databricks secret scope `ced-secrets` (created, validated, currently
  unused by any pipeline)
- Service principal `test_sp`, Application Id
  `374365a1-96f6-4597-af4c-a82aec75fff6`, OAuth client credentials
  generated, scoped grants on `ced` (`USE CATALOG`) and `ced.training`
  (`USE SCHEMA`, `SELECT`) — authenticated live from GitHub Actions every
  push to `main` (Milestone 14); still not adopted into the training
  pipeline itself
- `system.access.audit` confirmed populated, regional, 365-day default
  retention
- MLflow: Databricks-managed workspace experiment
  `/Shared/customer_event_detection_m8`
- Model registry aliases: unchanged from Milestone 12
- Production dependencies: `databricks-sdk`, `python-dotenv`, `pandas`.
  `xgboost`, `mlflow`, `evidently` are Databricks-side only.
  `apache-airflow`, `apache-airflow-providers-databricks` are WSL2-venv
  only. Databricks CLI is standalone local tooling. None of these are
  `pyproject.toml` dependencies except the first three.
- **NEW this milestone (15) — Docker Desktop installed but non-functional
  on the dev machine**: severe slowdowns / hangs the machine. `docker
  build` never completed successfully. Left unresolved by explicit user
  choice. A Docker-Engine-in-WSL2 alternative was identified as a
  candidate fix but not attempted.
- **NEW this milestone (15) — `%pip freeze` values captured from the live
  training notebook** (Sept 2026): `mlflow-skinny==3.8.1`,
  `pandas==2.2.3`, `scikit-learn==1.6.1`, `xgboost==3.4.1`. Used to pin
  the (unbuilt) `docker/train-job/Dockerfile`. Serverless environment
  version confirmed as 5 (Ubuntu 24.04.3 LTS, Python 3.12.3, Databricks
  Connect 18).
- PAT rotated Milestone 13 — the prior PAT had silently expired; new PAT
  generated, `.env` and Airflow's `databricks_default` connection both
  updated. Stored in `.env` (git-ignored) and Airflow's Fernet-encrypted
  connection store — deliberately NOT moved to the Databricks secret scope
  (see ADR-007 for why). Unaffected by Milestone 15.

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
- **PAT lifecycle has no monitoring or rotation process.** This
  milestone's expired-PAT discovery (M13) was accidental. A real gap if
  any future milestone introduces scheduled/unattended execution.
- **The PAT remains the credential for local scripts and Airflow, not SP
  OAuth client credentials.** This is a deliberate, not-yet-taken next
  step (distinct from the secret-scope decision) — see ADR-007 Future
  Considerations.
- **`test_sp` is not yet formally adopted into the training pipeline, or
  deleted.** It now has a genuine automated consumer (the CI smoke test,
  M14), so it's no longer purely unused infrastructure, but
  `train_model.py` / `validate_and_promote_model.py` still run under the
  personal account, not as `test_sp`. Cleanup/adoption decision still
  pending. M15's `training/train_model_job.py` doesn't change this either
  — it's unbuilt and unadopted.
- **`system.access.audit` is verified and populated but nothing consumes
  it yet.** No dashboard or scheduled query exists.
- **Local reproduction of the `dag-integrity` CI job needs `python3.12`
  explicitly in WSL2**, not the distro's bare `python3` (which is 3.14).
  Doesn't affect the real Airflow venv or the GitHub Actions runner
  itself, only local ad hoc verification.
- **NEW — Docker Desktop on the dev machine is effectively unusable**
  (severe slowdowns / hangs the machine). Blocks even local-only build
  verification of the M15 Docker artifacts. Left unresolved by explicit
  user choice, not by inability to identify a fix — a Docker-Engine-in-
  WSL2 alternative was proposed but not pursued.
- **NEW — every M15 artifact (`docker/train-job/Dockerfile`,
  `training/train_model_job.py`, `scripts/dcs_job_spec.json`) is entirely
  unverified** — not built, not run, not deployed. The single largest
  unverified assumption:  whether `SINGLE_USER` access mode +
  `docker_image` + Unity Catalog table access actually combine cleanly on
  real DCS compute, and whether `SparkSession.builder.getOrCreate()`
  behaves as expected in a real `spark_python_task` (vs. the notebook
  context the verified `train_model.py` actually runs in).
- **NEW — the `17.3-LTS` base image tag is an unverified assumption**,
  not a confirmed match, for the live pipeline's serverless environment
  version 5 — no official mapping exists between the two versioning
  schemes.

## Operating Rules Still In Effect (carried over, do not relax)
- Build incrementally — one milestone at a time, user runs everything themselves.
- Never claim something is implemented unless it was actually built and
  verified with observed output. **Milestone 15 is the clearest
  application of this rule to date on the "not implemented" side**: every
  artifact produced was explicitly downgraded from a forward-looking
  "built and verified" framing to "designed only, never run" the moment it
  became clear the local build had not actually happened — the discipline
  applies symmetrically, not just to claims of success.
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
  not rubber-stamped** — Milestone 13's "move PAT to secret scope"
  proposal was reconsidered and correctly walked back once the bootstrap
  circularity was identified, rather than implemented as originally
  agreed. Milestone 14 applied the same discipline: a PAT-based smoke
  test and full deploy automation were both considered and rejected with
  documented reasoning (ADR-019), not defaulted into. Milestone 15
  applied it again: a client-side container and a real trial-workspace
  deployment were both genuinely considered and explicitly declined in
  favor of the designed-only DCS path (ADR-020).
- **Test the risky part before writing it into a CI config** — Milestone
  14's `dag-integrity` design was validated by actually installing
  Airflow 3.3.1 + the Databricks provider into a sandbox and running
  `DagBag` against the real DAGs before proposing the CI job, which
  caught two real API differences (Airflow 3.x dropped `DagBag`'s
  `include_examples` kwarg; `DAG.schedule_interval` no longer exists,
  replaced by `.timetable`) that would otherwise have shipped as a
  broken test.
- **Adapt real, verified source code rather than inventing a plausible
  reconstruction** — Milestone 15's `training/train_model_job.py` was
  written only after the user supplied the actual, current
  `notebooks/train_model.py` source; every line not explicitly called out
  as changed (and why) is verbatim from that real source, not an
  approximation from the status doc's summary.

## Immediate Next Step
Milestone 15 is closed (📐 designed only, per ADR-020; Docker Desktop
blocker deliberately left unresolved). Milestone 16 is next, not yet
scoped in detail — do not begin without explicit user confirmation.
Candidates raised but not yet chosen: architecture diagrams pass,
exercising the champion/challenger branch, `test_sp` adoption into the
training pipeline, a scalability run on larger synthetic data.

## Reference Files
- `docs/project-status.md` — full status detail
- `docs/adr/ADR-002-airflow-orchestration-layer.md` — Airflow selection
  rationale
- `docs/adr/ADR-007-security-secrets-management.md` — secrets, RBAC, and
  audit logging findings and decisions (Milestone 13)
- `docs/adr/ADR-019-cicd-extension.md` — DAG integrity testing and live
  smoke-test findings and decisions (Milestone 14)
- `docs/adr/ADR-020-docker-container-services.md` — Docker/DCS design
  scope, options considered, and full unverified-status accounting (new,
  Milestone 15)
- `docs/adr/ADR-009` through `ADR-017` — see prior snapshots for
  individual summaries
- `docs/adr/ADR-018-milestone-12-orchestration.md` — two-DAG split, WSL2
  environment change, serverless compute compatibility finding
- `README.md` — public-facing summary (kept minimal, accurate)
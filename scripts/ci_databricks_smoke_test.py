"""
CI smoke test: confirms the test_sp service principal (Milestone 13,
ADR-007) can still authenticate against the live Databricks Free Edition
workspace via OAuth M2M, and that its Unity Catalog grants on
ced / ced.training are still in place.

Read-only. Makes no writes, triggers no jobs, changes nothing in the
workspace. This automates exactly the manual verification already
performed in Milestone 13 (see project-status.md "Commands Used to
Verify Milestone 13"), rather than adding new claims about what the SP
can do.

Run only by the databricks-smoke-test job in .github/workflows/ci.yml,
on push to main, using credentials from GitHub Actions secrets:
  DATABRICKS_HOST            -> DATABRICKS_HOST
  DATABRICKS_SP_CLIENT_ID    -> DATABRICKS_CLIENT_ID
  DATABRICKS_SP_CLIENT_SECRET -> DATABRICKS_CLIENT_SECRET

The databricks-sdk WorkspaceClient() constructor auto-detects OAuth M2M
auth from those three env var names -- confirmed empirically during
Milestone 14 design (constructing WorkspaceClient() with no arguments
resolved auth_type to "oauth-m2m" purely from the environment).
"""

import os
import sys

from databricks.sdk import WorkspaceClient

REQUIRED_ENV_VARS = ["DATABRICKS_HOST", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET"]

CATALOG = "ced"
SCHEMA_FULL_NAME = "ced.training"


def main() -> int:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print(f"FAIL: missing required environment variables: {missing}")
        print(
            "Expected these to be set from GitHub Actions secrets DATABRICKS_HOST, "
            "DATABRICKS_SP_CLIENT_ID, DATABRICKS_SP_CLIENT_SECRET."
        )
        return 1

    try:
        w = WorkspaceClient()
    except Exception as e:
        print(f"FAIL: could not construct WorkspaceClient (auth resolution failed): {e}")
        return 1

    try:
        catalog = w.catalogs.get(CATALOG)
        print(f"OK: authenticated as test_sp, read catalog '{catalog.name}'")
    except Exception as e:
        print(f"FAIL: test_sp could not read catalog '{CATALOG}': {e}")
        return 1

    try:
        schema = w.schemas.get(SCHEMA_FULL_NAME)
        print(f"OK: test_sp grant still valid, read schema '{schema.full_name}'")
    except Exception as e:
        print(
            f"FAIL: test_sp could not read schema '{SCHEMA_FULL_NAME}' "
            f"(RBAC grant from ADR-007 may have been revoked or changed): {e}"
        )
        return 1

    print("Smoke test passed: test_sp credentials and RBAC grants are live and correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

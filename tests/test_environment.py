"""Milestone 1 smoke test: confirms the test harness and Python env work.

This test will be replaced/expanded once real modules exist in Milestone 2+.
"""

import sys


def test_python_version_is_supported():
    assert sys.version_info >= (3, 11), "Project requires Python 3.11+"


def test_pytest_itself_runs():
    assert 1 + 1 == 2

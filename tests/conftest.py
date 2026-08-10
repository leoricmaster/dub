"""pytest configuration and live-test gating.

Two test lanes:
  - Fast lane (default): no network, no API keys, runs on every commit.
  - Live lane (@pytest.mark.live): real provider calls; skipped unless
    --run-live is passed. Used for the small smoke/acceptance suite.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run @pytest.mark.live tests (real provider API calls).",
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --run-live is given."""
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="needs --run-live (real API call)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)

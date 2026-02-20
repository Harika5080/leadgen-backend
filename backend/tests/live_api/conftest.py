# tests/live_api/conftest.py
"""
Live API tests - Uses REAL API keys and makes REAL API calls
Only run when you have API credits and want to verify integrations
"""

import pytest
import os

# Skip all tests in this directory if API keys not set
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_api: Tests that make real API calls (expensive, requires API keys)"
    )

# Check for required API keys
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Skip entire directory if no API keys
def pytest_collection_modifyitems(config, items):
    """Skip live API tests if API keys not configured"""
    if not SERPAPI_KEY and not GOOGLE_MAPS_KEY:
        skip_live = pytest.mark.skip(reason="No API keys configured (set SERPAPI_API_KEY or GOOGLE_MAPS_API_KEY)")
        for item in items:
            if "live_api" in item.nodeid:
                item.add_marker(skip_live)
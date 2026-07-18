"""Pytest configuration and fixtures for tests."""

import asyncio
import inspect
import pytest
import tempfile
import os
from typing import Generator


@pytest.fixture
def temp_config_file() -> Generator[str, None, None]:
    """Fixture providing a temporary config file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


def pytest_configure(config: pytest.Config) -> None:
    """Register local markers used by tests."""
    config.addinivalue_line("markers", "asyncio: mark async coroutine tests")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run async test functions via asyncio when no plugin is installed."""
    test_func = pyfuncitem.obj
    if inspect.iscoroutinefunction(test_func):
        asyncio.run(test_func(**pyfuncitem.funcargs))
        return True
    return None

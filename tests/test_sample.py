"""Sample test file to verify the testing setup."""

import pytest


def test_sample():
    """A simple test to verify pytest is working."""
    assert 1 + 1 == 2


@pytest.mark.asyncio
async def test_async_sample():
    """A sample async test (requires pytest-asyncio)."""
    result = await async_function()
    assert result is True


async def async_function():
    """Sample async function for testing."""
    return True

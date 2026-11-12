import pytest

from .llm_helpers import WireHarness


@pytest.fixture
def harness_factory():
    harnesses = []

    def make(**kwargs):
        harness = WireHarness(**kwargs)
        harnesses.append(harness)
        return harness

    yield make
    for harness in harnesses:
        harness.close()

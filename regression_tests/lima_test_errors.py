"""Failures for which repeating a scenario cannot produce a valid pass."""


class TestSetupError(RuntimeError):
    """Fail this test without retrying its setup."""


class TestCleanupError(TestSetupError):
    """Stop the run: subsequent tests cannot safely use the remaining state."""

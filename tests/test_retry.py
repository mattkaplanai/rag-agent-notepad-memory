"""Tests for exponential backoff retry logic."""

from unittest.mock import call, patch

import pytest

from app.agents.retry import MAX_ATTEMPTS, invoke_with_retry


class TestInvokeWithRetry:
    def test_success_on_first_attempt(self):
        result = invoke_with_retry(lambda: "ok", label="Test")
        assert result == "ok"

    def test_retries_on_timeout(self):
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise Exception("Connection timed out")
            return "ok"

        with patch("app.agents.retry.time.sleep"):
            result = invoke_with_retry(flaky, label="Test")

        assert result == "ok"
        assert calls == 3

    def test_retries_on_rate_limit(self):
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise Exception("rate_limit exceeded")
            return "done"

        with patch("app.agents.retry.time.sleep"):
            result = invoke_with_retry(flaky, label="Test")

        assert result == "done"
        assert calls == 2

    def test_retries_on_overloaded(self):
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise Exception("Overloaded")
            return "done"

        with patch("app.agents.retry.time.sleep"):
            result = invoke_with_retry(flaky, label="Test")

        assert result == "done"

    def test_raises_after_max_attempts(self):
        def always_fails():
            raise Exception("Connection timed out")

        with patch("app.agents.retry.time.sleep"):
            with pytest.raises(Exception, match="timed out"):
                invoke_with_retry(always_fails, label="Test")

    def test_attempt_count_equals_max(self):
        calls = 0

        def always_fails():
            nonlocal calls
            calls += 1
            raise Exception("timeout")

        with patch("app.agents.retry.time.sleep"):
            with pytest.raises(Exception):
                invoke_with_retry(always_fails, label="Test")

        assert calls == MAX_ATTEMPTS

    def test_does_not_retry_non_retryable_error(self):
        calls = 0

        def auth_error():
            nonlocal calls
            calls += 1
            raise Exception("Invalid API key — authentication failed")

        with patch("app.agents.retry.time.sleep"):
            with pytest.raises(Exception, match="authentication"):
                invoke_with_retry(auth_error, label="Test")

        assert calls == 1  # no retry on auth errors

    def test_sleep_uses_exponential_backoff(self):
        def always_fails():
            raise Exception("503 Service Unavailable")

        with patch("app.agents.retry.time.sleep") as mock_sleep:
            with pytest.raises(Exception):
                invoke_with_retry(always_fails, label="Test")

        # Delays should be 2^1=2, 2^2=4 (MAX_ATTEMPTS=3, so 2 sleeps)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [2.0, 4.0]

    def test_returns_value_from_successful_call(self):
        result = invoke_with_retry(lambda: {"decision": "APPROVED"}, label="Test")
        assert result == {"decision": "APPROVED"}

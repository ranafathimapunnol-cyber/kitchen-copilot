import pytest

from spikes.ai import tool_calling


class FakeGeminiError(Exception):
    def __init__(self, status_code):
        super().__init__(f"Gemini HTTP {status_code}")
        self.code = status_code


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def test_retries_after_429_then_succeeds(monkeypatch):
    client = FakeClient([
        FakeGeminiError(429),
        "Gemini response",
    ])

    delays = []
    monkeypatch.setattr(
        tool_calling.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )
    monkeypatch.setattr(
        tool_calling.random,
        "uniform",
        lambda low, high: 0.5,
    )

    result = tool_calling.generate_with_retry(
        client,
        model="test-model",
        contents="Hello",
    )

    assert result == "Gemini response"
    assert client.models.calls == 2
    assert delays == [2.5]


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_retries_temporary_http_errors(monkeypatch, status_code):
    client = FakeClient([
        FakeGeminiError(status_code),
        "Success",
    ])

    monkeypatch.setattr(tool_calling.time, "sleep", lambda _: None)
    monkeypatch.setattr(tool_calling.random, "uniform", lambda *_: 0)

    result = tool_calling.generate_with_retry(
        client,
        model="test-model",
        contents="Hello",
    )

    assert result == "Success"
    assert client.models.calls == 2


def test_does_not_retry_non_retryable_error(monkeypatch):
    client = FakeClient([
        FakeGeminiError(400),
        "Should not be reached",
    ])

    delays = []
    monkeypatch.setattr(
        tool_calling.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )

    with pytest.raises(FakeGeminiError):
        tool_calling.generate_with_retry(
            client,
            model="test-model",
            contents="Hello",
        )

    assert client.models.calls == 1
    assert delays == []


def test_stops_after_three_failed_attempts(monkeypatch):
    client = FakeClient([
        FakeGeminiError(429),
        FakeGeminiError(429),
        FakeGeminiError(429),
    ])

    delays = []
    monkeypatch.setattr(
        tool_calling.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )
    monkeypatch.setattr(
        tool_calling.random,
        "uniform",
        lambda *_: 0,
    )

    with pytest.raises(FakeGeminiError):
        tool_calling.generate_with_retry(
            client,
            model="test-model",
            contents="Hello",
        )

    assert client.models.calls == 3
    assert delays == [2, 4]


def test_success_on_first_attempt_does_not_retry(monkeypatch):
    client = FakeClient(["Immediate success"])

    delays = []
    monkeypatch.setattr(
        tool_calling.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )

    result = tool_calling.generate_with_retry(
        client,
        model="test-model",
        contents="Hello",
    )

    assert result == "Immediate success"
    assert client.models.calls == 1
    assert delays == []


def test_retries_actual_google_genai_api_error(monkeypatch):
    from google.genai import errors

    client = FakeClient([
        errors.APIError(429, {"message": "Rate limit exceeded"}),
        "Success",
    ])

    delays = []
    monkeypatch.setattr(
        tool_calling.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )
    monkeypatch.setattr(
        tool_calling.random,
        "uniform",
        lambda *_: 0,
    )

    result = tool_calling.generate_with_retry(
        client,
        model="test-model",
        contents="Hello",
    )

    assert result == "Success"
    assert client.models.calls == 2
    assert delays == [2]


def test_retries_actual_google_genai_server_error(monkeypatch):
    from google.genai import errors

    client = FakeClient([
        errors.APIError(503, {"message": "Service unavailable"}),
        "Success",
    ])

    monkeypatch.setattr(tool_calling.time, "sleep", lambda _: None)
    monkeypatch.setattr(tool_calling.random, "uniform", lambda *_: 0)

    result = tool_calling.generate_with_retry(
        client,
        model="test-model",
        contents="Hello",
    )

    assert result == "Success"
    assert client.models.calls == 2


def test_does_not_retry_actual_google_genai_client_error(monkeypatch):
    from google.genai import errors

    client = FakeClient([
        errors.APIError(400, {"message": "Invalid request"}),
        "Should not be reached",
    ])

    delays = []
    monkeypatch.setattr(
        tool_calling.time,
        "sleep",
        lambda seconds: delays.append(seconds),
    )

    with pytest.raises(errors.APIError):
        tool_calling.generate_with_retry(
            client,
            model="test-model",
            contents="Hello",
        )

    assert client.models.calls == 1
    assert delays == []

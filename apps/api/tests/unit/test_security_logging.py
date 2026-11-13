"""로그 경계에서 중첩 필드와 traceback도 비밀을 노출하지 않아야 한다."""

import json
import logging
import sys

from app.core.logging import JsonFormatter, SecretMasker


def test_masks_nested_fields_and_traceback():
    secret = "test-secret-only-for-masking"
    try:
        raise ValueError(f"provider failed: {secret}")
    except ValueError:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "failure %s", (secret,), sys.exc_info()
        )
    record.headers = {"Authorization": "Basic dGVzdDpwYXNz", "nested": [secret]}
    masker = SecretMasker([secret])
    masker.filter(record)
    output = JsonFormatter().format(record)
    assert secret not in output
    assert "dGVzdDpwYXNz" not in output
    assert "ValueError" in json.loads(output)["exc"]

from mantau_core.notify.channels.push.errors import PushErrorKind, classify_fcm_error


def test_unregistered_token_is_classified_for_pruning():
    body = {"error": {"status": "NOT_FOUND",
                       "details": [{"errorCode": "UNREGISTERED"}]}}
    assert classify_fcm_error(404, body) is PushErrorKind.UNREGISTERED


def test_invalid_argument_is_not_retried():
    body = {"error": {"status": "INVALID_ARGUMENT", "details": []}}
    assert classify_fcm_error(400, body) is PushErrorKind.INVALID


def test_server_error_is_retryable():
    assert classify_fcm_error(500, {"error": {"status": "INTERNAL"}}) is PushErrorKind.RETRYABLE


def test_rate_limit_is_retryable():
    assert classify_fcm_error(429, {"error": {}}) is PushErrorKind.RETRYABLE


def test_resource_exhausted_is_retryable():
    body = {"error": {"status": "RESOURCE_EXHAUSTED"}}
    assert classify_fcm_error(429, body) is PushErrorKind.RETRYABLE


def test_unclassified_error_falls_back_to_unknown():
    assert classify_fcm_error(418, {"error": {"status": "IM_A_TEAPOT"}}) is PushErrorKind.UNKNOWN


def test_empty_body_does_not_crash_classification():
    assert classify_fcm_error(500, {}) is PushErrorKind.RETRYABLE

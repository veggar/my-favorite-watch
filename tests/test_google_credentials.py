"""P0-1 회귀 테스트.

Flask 세션 쿠키는 서명만 되고 암호화되지 않으므로, 세션에 저장되는
자격증명 페이로드에 client_secret / refresh_token 이 절대 포함되면 안 된다.

실행: pytest -q
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")

from services.google_credentials import (  # noqa: E402
    build_credentials,
    credentials_from_session,
    credentials_from_worker_payload,
    session_payload,
    worker_payload,
)

SECRET_KEYS = ("client_secret", "refresh_token")


@pytest.fixture()
def creds():
    return build_credentials(
        token="ya29.access-token",
        refresh_token="1//refresh-token-secret",
        expiry=datetime(2026, 8, 5, 12, 0, 0),
    )


def test_session_payload_has_no_secrets(creds):
    payload = session_payload(creds)
    for key in SECRET_KEYS:
        assert key not in payload, f"세션 페이로드에 {key} 가 포함되면 안 된다"
    # 직렬화 결과 전체를 문자열로 훑어 값 자체가 새지 않는지도 확인
    dumped = repr(payload)
    assert "1//refresh-token-secret" not in dumped
    assert "test-client-secret" not in dumped


def test_session_payload_keeps_only_token_and_expiry(creds):
    assert set(session_payload(creds)) == {"token", "expiry"}


def test_credentials_from_session_restores_client_config(creds):
    restored = credentials_from_session(session_payload(creds), refresh_token="1//from-firestore")
    # 세션에 없던 값들이 환경 변수 · 상수에서 복원되어야 한다
    assert restored.client_id == "test-client-id"
    assert restored.client_secret == "test-client-secret"
    assert restored.refresh_token == "1//from-firestore"
    assert restored.token == "ya29.access-token"
    assert restored.expiry == creds.expiry


def test_expired_token_is_detected_via_stored_expiry():
    """expiry 를 세션에 두지 않으면 creds.expired 가 항상 False 가 되어
    토큰 갱신이 영원히 일어나지 않는다. 회귀 방지."""
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    creds = build_credentials(token="stale", refresh_token=None, expiry=past)
    restored = credentials_from_session(session_payload(creds))
    assert restored.expired is True


def test_worker_payload_round_trip_keeps_secrets_in_memory(creds):
    """워커 전달용 페이로드는 갱신이 가능해야 하므로 비밀 값을 포함한다."""
    payload = worker_payload(creds)
    for key in SECRET_KEYS:
        assert key in payload
    restored = credentials_from_worker_payload(payload)
    assert restored.refresh_token == "1//refresh-token-secret"
    assert restored.client_secret == "test-client-secret"

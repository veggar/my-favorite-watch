"""P0-2 회귀 테스트 — 검증된 Google `sub` 기반 HMAC 사용자 키.

조치안 5.1 / 7.4 완료 기준
- 단순 SHA-256(email) 을 쓰지 않는다.
- user_key 는 서버 비밀키에 의존하며, 키가 바뀌면 값도 바뀐다.
- 운영에서 HMAC 키가 없으면 로그인 대신 실패한다(이메일 저장으로 폴백하지 않는다).

실행: pytest -q
"""
import base64
import hashlib
import os

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")

from services import user_identity  # noqa: E402
from services.user_identity import (  # noqa: E402
    MIN_SECRET_BYTES,
    USER_KEY_VERSION,
    UserIdentityError,
    build_user_key,
    verify_id_token,
)

SECRET = "s" * MIN_SECRET_BYTES
OTHER_SECRET = "z" * MIN_SECRET_BYTES
SUB = "103547991597142817347"
EMAIL = "someone@example.com"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("USER_KEY_HMAC_SECRET", SECRET)
    monkeypatch.setenv("FLASK_SECRET_KEY", "unrelated-flask-secret")
    monkeypatch.setenv("APP_ENV", "production")


def test_user_key_is_deterministic(configured):
    assert build_user_key(SUB) == build_user_key(SUB)


def test_user_key_has_version_prefix(configured):
    assert build_user_key(SUB).startswith(f"{USER_KEY_VERSION}_")


def test_different_subjects_produce_different_keys(configured):
    assert build_user_key(SUB) != build_user_key(SUB + "1")


def test_user_key_depends_on_secret(configured, monkeypatch):
    first = build_user_key(SUB)
    monkeypatch.setenv("USER_KEY_HMAC_SECRET", OTHER_SECRET)
    assert build_user_key(SUB) != first


def test_user_key_is_not_a_plain_sha256(configured):
    """키 없는 해시(sub · email 모두)와 값이 겹치면 안 된다."""
    key = build_user_key(SUB)
    for candidate in (SUB, EMAIL):
        plain = base64.urlsafe_b64encode(
            hashlib.sha256(candidate.encode()).digest()
        ).decode().rstrip("=")
        assert plain not in key


def test_user_key_does_not_leak_subject_or_email(configured):
    key = build_user_key(SUB)
    assert SUB not in key
    assert EMAIL not in key


def test_missing_secret_fails_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("USER_KEY_HMAC_SECRET", raising=False)
    with pytest.raises(UserIdentityError):
        build_user_key(SUB)


def test_short_secret_fails_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USER_KEY_HMAC_SECRET", "too-short")
    with pytest.raises(UserIdentityError):
        build_user_key(SUB)


def test_secret_must_differ_from_flask_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("USER_KEY_HMAC_SECRET", SECRET)
    monkeypatch.setenv("FLASK_SECRET_KEY", SECRET)
    with pytest.raises(UserIdentityError):
        build_user_key(SUB)


def test_development_falls_back_to_fixed_secret(monkeypatch):
    """로컬 개발에서는 키 없이도 동작하되 값은 결정적이어야 한다."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("USER_KEY_HMAC_SECRET", raising=False)
    assert build_user_key(SUB) == build_user_key(SUB)


def test_empty_subject_is_rejected(configured):
    with pytest.raises(UserIdentityError):
        build_user_key("")


def test_verify_id_token_requires_token_and_audience():
    with pytest.raises(UserIdentityError):
        verify_id_token("", "client-id")
    with pytest.raises(UserIdentityError):
        verify_id_token("token", "")


def _patch_verifier(monkeypatch, claims):
    from google.oauth2 import id_token as google_id_token

    def _fake_verify(token, request, audience, clock_skew_in_seconds=0):
        return claims

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _fake_verify)


def test_verify_id_token_rejects_unexpected_issuer(monkeypatch):
    _patch_verifier(monkeypatch, {"iss": "https://evil.example.com", "sub": SUB})
    with pytest.raises(UserIdentityError):
        verify_id_token("dummy-token", "client-id")


def test_verify_id_token_rejects_missing_subject(monkeypatch):
    _patch_verifier(monkeypatch, {"iss": "https://accounts.google.com", "sub": ""})
    with pytest.raises(UserIdentityError):
        verify_id_token("dummy-token", "client-id")


def test_user_key_from_id_token_uses_verified_subject(configured, monkeypatch):
    _patch_verifier(
        monkeypatch,
        {"iss": "https://accounts.google.com", "sub": SUB, "email": EMAIL},
    )
    key, claims = user_identity.user_key_from_id_token("dummy-token", "client-id")
    assert key == build_user_key(SUB)
    assert claims["email"] == EMAIL

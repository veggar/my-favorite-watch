"""P0-5 회귀 테스트 — 세션 수명.

PERMANENT_SESSION_LIFETIME 을 명시하지 않으면 Flask 기본값 31일이 적용된다.
세션 쿠키에는 access token 이 담기므로 수명을 명시적으로 짧게 유지하고,
장기 로그인 유지는 device_id 쿠키(90일) + Firestore 가 담당해야 한다.

실행: pytest -q
"""
import os
from datetime import timedelta

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")

import app as app_module  # noqa: E402
from routes.auth import DEVICE_ID_MAX_AGE, set_device_cookie  # noqa: E402

FLASK_DEFAULT_LIFETIME = timedelta(days=31)


def test_permanent_session_lifetime_is_explicit():
    lifetime = app_module.app.config["PERMANENT_SESSION_LIFETIME"]
    assert lifetime != FLASK_DEFAULT_LIFETIME, "Flask 기본값 31일을 그대로 쓰면 안 된다"
    assert lifetime == timedelta(hours=12)


def test_session_lifetime_is_shorter_than_device_id_lifetime():
    """세션 쿠키는 단기, device_id 는 장기라는 2계층 구조를 강제한다."""
    lifetime = app_module.app.config["PERMANENT_SESSION_LIFETIME"]
    assert lifetime.total_seconds() < DEVICE_ID_MAX_AGE


def test_device_id_lifetime_is_90_days():
    assert DEVICE_ID_MAX_AGE == 60 * 60 * 24 * 90


def test_session_is_refreshed_each_request():
    """사용 중인 세션이 12시간마다 끊기지 않아야 한다."""
    assert app_module.app.config["SESSION_REFRESH_EACH_REQUEST"] is True


def test_session_cookie_security_flags():
    cfg = app_module.app.config
    assert cfg["SESSION_COOKIE_HTTPONLY"] is True
    assert cfg["SESSION_COOKIE_SAMESITE"] == "Lax"


@pytest.mark.parametrize("app_env,expected_secure", [
    ("production", True),
    ("development", False),
])
def test_device_cookie_secure_flag_follows_env(monkeypatch, app_env, expected_secure):
    monkeypatch.setenv("APP_ENV", app_env)

    class _Resp:
        def __init__(self):
            self.kwargs = None

        def set_cookie(self, *args, **kwargs):
            self.kwargs = kwargs

    resp = _Resp()
    set_device_cookie(resp, "device-123")
    assert resp.kwargs["secure"] is expected_secure
    assert resp.kwargs["httponly"] is True
    assert resp.kwargs["max_age"] == DEVICE_ID_MAX_AGE


def test_login_marks_session_permanent():
    """session.permanent 를 지정하지 않으면 브라우저 종료 시 세션이 사라지고
    PERMANENT_SESSION_LIFETIME 이 적용되지 않는다."""
    import inspect
    from routes import auth

    src = inspect.getsource(auth.auth_callback)
    assert "session.permanent = True" in src


def test_device_cookie_is_renewed_on_session_restore():
    """계속 사용 중인 사용자가 최초 로그인 90일 후 강제 로그아웃되지 않도록
    복원 성공 시 쿠키 만료를 연장해야 한다."""
    import inspect

    assert "renew_device_id" in inspect.getsource(app_module.auto_restore_session)
    assert "set_device_cookie" in inspect.getsource(app_module.renew_device_cookie)

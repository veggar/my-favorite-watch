"""P0-5 회귀 테스트 — 단일 `__session` 쿠키의 수명 2계층.

Firebase Hosting 은 백엔드로 `__session` 쿠키 하나만 전달한다. 따라서
예전의 "짧은 세션 쿠키 + 긴 device_id 쿠키" 구조를 쓸 수 없고, 수명 분리를
코드로 강제해야 한다(조치안 개정 2판 2.2).

    장기(90일)  쿠키 수명이 담당 — device_id · user_key · 시트 캐시
    단기(12시간) auth_at 검사로 강제 — credentials(access token)

이 파일은 그 구조가 무너지지 않도록 고정한다. 실행: python3 -m pytest -q
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

import app as app_module
from services.session_state import (
    DEFAULT_FRESHNESS_HOURS,
    auth_timestamp,
    freshness_hours,
    is_auth_fresh,
    new_device_id,
)

FLASK_DEFAULT_LIFETIME = timedelta(days=31)


# ── 쿠키 계층 ──────────────────────────────────────────────────────────────

def test_session_cookie_name_is_dunder_session():
    """이름이 `__session` 이 아니면 Firebase Hosting 이 쿠키를 버린다."""
    assert app_module.app.config["SESSION_COOKIE_NAME"] == "__session"


def test_cookie_lifetime_covers_device_layer():
    lifetime = app_module.app.config["PERMANENT_SESSION_LIFETIME"]
    assert lifetime != FLASK_DEFAULT_LIFETIME, "Flask 기본값 31일을 그대로 쓰면 안 된다"
    assert lifetime == timedelta(days=90)


def test_session_is_refreshed_each_request():
    """사용 중인 세션의 만료가 요청마다 연장되어야 90일이 마지막 사용 기준이 된다."""
    assert app_module.app.config["SESSION_REFRESH_EACH_REQUEST"] is True


def test_session_cookie_security_flags():
    cfg = app_module.app.config
    assert cfg["SESSION_COOKIE_HTTPONLY"] is True
    assert cfg["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_no_separate_device_cookie_is_issued():
    """두 번째 쿠키를 다시 도입하면 Firebase Hosting 에서 조용히 버려진다."""
    from routes import auth

    src = inspect.getsource(auth)
    assert "set_cookie(" not in src, "세션 외의 쿠키를 발급하면 안 된다"


def test_auth_freshness_is_shorter_than_cookie_lifetime():
    cookie_lifetime = app_module.app.config["PERMANENT_SESSION_LIFETIME"]
    assert timedelta(hours=freshness_hours()) < cookie_lifetime


# ── 단기 계층 판정 ─────────────────────────────────────────────────────────

def test_fresh_timestamp_is_accepted():
    assert is_auth_fresh(auth_timestamp()) is True


def test_missing_or_malformed_timestamp_is_stale():
    """이전 스키마에서 넘어온 세션(auth_at 없음)도 만료로 취급해야 한다."""
    assert is_auth_fresh(None) is False
    assert is_auth_fresh("") is False
    assert is_auth_fresh("not-a-timestamp") is False


def test_old_timestamp_is_stale(monkeypatch):
    monkeypatch.setenv("AUTH_FRESHNESS_HOURS", "12")
    old = datetime.now(timezone.utc) - timedelta(hours=13)
    assert is_auth_fresh(old.isoformat()) is False


def test_boundary_timestamp_is_still_fresh(monkeypatch):
    monkeypatch.setenv("AUTH_FRESHNESS_HOURS", "12")
    recent = datetime.now(timezone.utc) - timedelta(hours=11, minutes=59)
    assert is_auth_fresh(recent.isoformat()) is True


def test_future_timestamp_is_not_trusted():
    """시계 역행이나 조작된 값으로 신선도를 무한 연장할 수 없어야 한다."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert is_auth_fresh(future.isoformat()) is False


def test_naive_timestamp_is_treated_as_utc():
    naive = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None)
    assert is_auth_fresh(naive.isoformat()) is True


@pytest.mark.parametrize("value,expected", [
    ("6", 6),
    ("0", DEFAULT_FRESHNESS_HOURS),
    ("-3", DEFAULT_FRESHNESS_HOURS),
    ("abc", DEFAULT_FRESHNESS_HOURS),
])
def test_freshness_hours_falls_back_safely(monkeypatch, value, expected):
    monkeypatch.setenv("AUTH_FRESHNESS_HOURS", value)
    assert freshness_hours() == expected


def test_legacy_env_var_is_still_honored(monkeypatch):
    monkeypatch.delenv("AUTH_FRESHNESS_HOURS", raising=False)
    monkeypatch.setenv("SESSION_LIFETIME_HOURS", "8")
    assert freshness_hours() == 8


# ── 기기 식별자 ────────────────────────────────────────────────────────────

def test_device_id_is_unpredictable():
    first, second = new_device_id(), new_device_id()
    assert first != second
    assert len(first) >= 32


def test_login_marks_session_permanent():
    """permanent 가 아니면 브라우저 종료 시 세션이 사라져 90일 유지가 깨진다."""
    from routes import auth

    src = inspect.getsource(auth.auth_callback)
    assert "session.permanent = True" in src


def test_device_id_survives_account_switch_clear():
    """세션을 비우기 전에 device_id 를 꺼내 두어야 기기 식별이 유지된다."""
    from routes import auth

    src = inspect.getsource(auth.auth_callback)
    device_line = src.index('device_id = session.get("device_id")')
    clear_line = src.index("session.clear()")
    assert device_line < clear_line

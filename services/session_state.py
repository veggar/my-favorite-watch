"""단일 `__session` 쿠키 안에서 수명 2계층을 관리하는 헬퍼 (P0-5).

Firebase Hosting 은 백엔드로 `__session` 쿠키 하나만 전달한다. 따라서
예전처럼 짧은 세션 쿠키와 긴 `device_id` 쿠키로 수명을 나눌 수 없다.

대신 쿠키 수명은 기기 계층(90일)에 맞추고, access token 계층의 신선도는
세션 안의 `auth_at` 값으로 코드에서 판정한다.

    auth_at 이 신선함  → 세션의 access token 을 그대로 사용
    auth_at 이 만료됨  → credentials 를 세션에서 제거
                        → 자동 복원 경로가 Firestore refresh_token 으로
                          재발급하고 auth_at 을 갱신

사용자에게는 재로그인이 발생하지 않으며, 쿠키를 탈취당해도 그 안의
access token 은 최대 만료 시각까지만 유효하다.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

DEFAULT_FRESHNESS_HOURS = 12
DEVICE_ID_BYTES = 32


def freshness_hours() -> int:
    """access token 계층의 유효 시간(시간 단위).

    `AUTH_FRESHNESS_HOURS` 를 우선 보고, 없으면 기존 환경 변수
    `SESSION_LIFETIME_HOURS` 를 그대로 재사용한다.
    """
    raw = os.environ.get("AUTH_FRESHNESS_HOURS") or os.environ.get(
        "SESSION_LIFETIME_HOURS", str(DEFAULT_FRESHNESS_HOURS)
    )
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_FRESHNESS_HOURS
    return hours if hours > 0 else DEFAULT_FRESHNESS_HOURS


def auth_timestamp(now: datetime | None = None) -> str:
    """현재 인증 시각을 세션에 담을 문자열로 만든다."""
    return (now or datetime.now(timezone.utc)).isoformat()


def is_auth_fresh(value: str | None, now: datetime | None = None) -> bool:
    """`auth_at` 값이 아직 신선한지 판정한다.

    값이 없거나 형식이 깨졌으면 만료로 취급한다. 이전 스키마에서 넘어온
    세션(= `auth_at` 없음)도 이 경로로 걸러져 재구성된다.
    """
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    # 시계 역행이나 미래 값은 신뢰하지 않는다.
    if parsed > now + timedelta(minutes=5):
        return False
    return now - parsed < timedelta(hours=freshness_hours())


def new_device_id() -> str:
    """기기 식별자를 새로 발급한다."""
    return secrets.token_urlsafe(DEVICE_ID_BYTES)

"""P0-2 · 검증된 Google `sub` 기반 내부 사용자 키(user_key).

배경
    이메일은 변경될 수 있고 후보 공간이 좁아 사전 대입으로 추정하기 쉽다.
    따라서 사용자 식별키로 이메일(및 이메일의 단순 SHA-256)을 사용하지 않고,
    ID Token 검증 후 얻은 Google OIDC `sub` 에 **서버 비밀키 기반 HMAC** 을
    적용한 값을 내부 사용자 키로 사용한다.

        user_key = "v1_" + BASE64URL(HMAC-SHA-256(USER_KEY_HMAC_SECRET, sub))

키 관리 원칙 (조치안 5.1)
    - `USER_KEY_HMAC_SECRET` 은 최소 32바이트의 독립 난수.
    - `FLASK_SECRET_KEY` 와 절대 공유하지 않는다.
    - 운영에서는 Google Secret Manager 로만 주입한다(`scripts/deploy.sh` 참조).
    - 회전 대비로 `user_key_version` 을 문서에 함께 저장한다.
    - 레코드별 임의 Salt 는 멀티 디바이스의 결정적 조회를 깨뜨리므로 쓰지 않는다.

주의
    HMAC 적용은 유출 시 직접 식별 위험을 줄이는 안전조치일 뿐,
    개인정보 처리 의무를 면제하지 않는다(조치안 4.2).
"""
import base64
import hashlib
import hmac
import logging
import os

logger = logging.getLogger(__name__)

USER_KEY_VERSION = "v1"
SECRET_ENV = "USER_KEY_HMAC_SECRET"
MIN_SECRET_BYTES = 32

# ID Token 검증 시 허용할 시계 오차(초). Cloud Run 과 Google 간 미세한
# 시계 차이로 방금 발급된 토큰이 거부되는 것을 막는다.
CLOCK_SKEW_SECONDS = 10

_VALID_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

# 로컬 개발 전용 고정 키. 운영에서는 절대 사용되지 않는다(아래 hmac_secret 참조).
_DEV_SECRET = b"dev-only-user-key-hmac-secret-not-for-production"


class UserIdentityError(Exception):
    """ID Token 검증 또는 user_key 생성 실패.

    메시지에는 `sub`, 이메일, 토큰 원문을 담지 않는다(security.md Sanitization).
    """


def _is_dev() -> bool:
    env = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV", "production")
    return env.lower() in ("development", "dev", "local")


def hmac_secret() -> bytes:
    """HMAC 비밀키를 환경에서 읽는다.

    운영에서 미설정이거나 너무 짧으면 예외를 던진다. 이메일 원문 저장으로
    되돌아가는 폴백은 제공하지 않는다(조치안 9. 롤백 원칙).
    """
    raw = os.environ.get(SECRET_ENV, "").strip()
    if not raw:
        if _is_dev():
            logger.warning(
                "%s 미설정 — 개발 전용 고정 키를 사용한다. 운영 배포에서는 "
                "Secret Manager 주입이 필수다.", SECRET_ENV,
            )
            return _DEV_SECRET
        raise UserIdentityError(f"{SECRET_ENV} not configured")

    secret = raw.encode("utf-8")
    if len(secret) < MIN_SECRET_BYTES:
        if _is_dev():
            logger.warning("%s 가 %d바이트 미만이다(개발 환경이라 계속 진행).",
                           SECRET_ENV, MIN_SECRET_BYTES)
            return secret
        raise UserIdentityError(f"{SECRET_ENV} shorter than {MIN_SECRET_BYTES} bytes")

    # FLASK_SECRET_KEY 재사용 금지. 두 키가 같으면 세션 쿠키 서명키 유출이
    # 곧바로 사용자 키 역산 위험으로 이어진다.
    flask_secret = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if flask_secret and hmac.compare_digest(flask_secret, raw):
        raise UserIdentityError(f"{SECRET_ENV} must differ from FLASK_SECRET_KEY")

    return secret


def build_user_key(sub: str) -> str:
    """검증된 `sub` 로 결정적 user_key 를 만든다.

    `sub` 는 case-sensitive 값을 그대로 입력한다(정규화하지 않는다).
    """
    if not sub or not isinstance(sub, str):
        raise UserIdentityError("empty subject identifier")
    digest = hmac.new(hmac_secret(), sub.encode("utf-8"), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{USER_KEY_VERSION}_{encoded}"


def verify_id_token(raw_id_token: str, audience: str) -> dict:
    """ID Token 의 서명 · iss · aud · exp 를 검증하고 클레임을 반환한다."""
    if not raw_id_token:
        raise UserIdentityError("id_token missing in token response")
    if not audience:
        raise UserIdentityError("client_id not configured")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )
    except UserIdentityError:
        raise
    except Exception as e:
        # 예외 원문에는 토큰 일부가 포함될 수 있으므로 타입만 남긴다.
        logger.warning("ID token verification failed (%s)", type(e).__name__)
        raise UserIdentityError("id_token verification failed") from e

    if claims.get("iss") not in _VALID_ISSUERS:
        raise UserIdentityError("unexpected id_token issuer")
    if not claims.get("sub"):
        raise UserIdentityError("id_token has no subject")
    return claims


def user_key_from_id_token(raw_id_token: str, audience: str) -> tuple[str, dict]:
    """ID Token 을 검증하고 (user_key, claims) 를 반환한다."""
    claims = verify_id_token(raw_id_token, audience)
    return build_user_key(claims["sub"]), claims

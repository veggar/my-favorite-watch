"""Google OAuth 자격증명 직렬화 유틸.

Flask 세션 쿠키는 **서명만 되고 암호화되지 않는다.** 따라서 세션에는
`client_secret` / `refresh_token` 같은 비밀 값을 절대 담지 않는다.

- 세션에 저장하는 값: access token + 만료 시각 (둘 다 단기 · 비밀 아님)
- `client_id` / `client_secret` / `token_uri` / `scopes`: 환경 변수와 상수에서 재구성
- `refresh_token`: Firestore(`sessions/{device_id}`)에서 필요할 때만 조회

`.claude/rules/security.md` "No Hardcoding" / "Sanitization" 준수.
"""
import os
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/spreadsheets",
    # drive.readonly → metadata.readonly 로 최소 권한 원칙 적용
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


def client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "")


def client_secret() -> str:
    return os.environ.get("GOOGLE_CLIENT_SECRET", "")


def build_credentials(token: str | None, refresh_token: str | None,
                      expiry: datetime | None = None) -> Credentials:
    """환경 변수 · 상수와 전달받은 토큰으로 Credentials 를 재구성한다."""
    creds = Credentials(
        token=token,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id(),
        client_secret=client_secret(),
        scopes=SCOPES,
    )
    if expiry is not None:
        creds.expiry = expiry
    return creds


def session_payload(creds: Credentials) -> dict:
    """세션 쿠키에 저장해도 안전한 최소 정보만 추출한다.

    비밀 값(client_secret, refresh_token)은 의도적으로 제외한다.
    """
    return {
        "token": creds.token,
        "expiry": _expiry_to_str(creds.expiry),
    }


def credentials_from_session(session_data: dict,
                             refresh_token: str | None = None) -> Credentials:
    """세션에 저장된 최소 정보 + refresh_token 으로 Credentials 를 복원한다."""
    return build_credentials(
        token=session_data.get("token"),
        refresh_token=refresh_token,
        expiry=_expiry_from_str(session_data.get("expiry")),
    )


# ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

def _expiry_to_str(expiry: datetime | None) -> str:
    """google-auth 는 naive UTC datetime 을 사용한다. ISO 문자열로 직렬화."""
    if not expiry:
        return ""
    return expiry.isoformat()


def _expiry_from_str(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    # google-auth 내부 비교는 naive UTC 기준이므로 UTC 로 변환 후 tz 정보를 제거한다.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

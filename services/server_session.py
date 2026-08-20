"""서버 측 세션 저장소 — Firestore `server_sessions` 컬렉션 (task-2026-08-003).

브라우저 쿠키에는 예측 불가능한 `session_id` 만 두고, 민감한 세션 값
(access token · user_key · 표시용 사용자 정보 · 시트 캐시)은 이 모듈이
Firestore 에 보관한다.

구조 (task-003 §2)

    server_sessions/{sha256(session_id)}
        device_id                       # 운영 진단용 (쿠키의 값이 원본)
        user_key
        credentials                     # {token, expiry} — access token 만
        user                            # {name, email, picture} 표시용 · 단기
        sheet_id, sheet_title, worksheet_name
        auth_at
        created_at, updated_at, expires_at, schema_version

설계 원칙
    - 문서 키는 `session_id` 원본이 아니라 **sha256 해시**다. Firestore
      열람 권한이 있어도 문서 키만으로는 유효한 쿠키를 만들 수 없다.
    - `save_session` 은 **전체 치환**(merge 아님)이다. 인증 신선도 만료로
      `session.pop("credentials")` 가 일어나면 다음 저장에서 문서에서도
      해당 키가 사라져야 한다.
    - Firestore 미구성(로컬 개발) 시 모든 함수는 조용히 실패값을 반환하고,
      `services.hybrid_session` 이 쿠키 직저장 폴백으로 동작한다.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from services import firestore_session as _fs

logger = logging.getLogger(__name__)

SESSIONS_COLLECTION = "server_sessions"
SCHEMA_VERSION = 1

# 쿠키 수명(DEVICE_SESSION_DAYS = 90일)과 반드시 일치시킨다.
# password-manager 는 30일이라 값이 다르다 — 이 프로젝트 기준을 따른다.
SESSION_TTL_DAYS = 90

SESSION_ID_BYTES = 32

# firestore_session 과 같은 클라이언트(database="refresh-token")를 재사용한다.
# 두 번째 Client 생성을 피하고, 자격증명 유무 판단도 한 곳으로 모은다.
_db = _fs.get_db()


def is_configured() -> bool:
    """Firestore 저장소를 사용할 수 있는지."""
    return _db is not None


def new_session_id() -> str:
    """예측 불가능한 세션 식별자를 발급한다 (256bit)."""
    return secrets.token_urlsafe(SESSION_ID_BYTES)


def _hash(session_id: str) -> str:
    """문서 키용 해시. 원본 session_id 는 어디에도 저장하지 않는다."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expires_at() -> datetime:
    return _now() + timedelta(days=SESSION_TTL_DAYS)


def get_session(session_id: str) -> dict | None:
    """세션 값을 조회한다. 만료된 문서는 삭제하고 None 을 반환한다."""
    if _db is None or not session_id:
        return None
    try:
        ref = _db.collection(SESSIONS_COLLECTION).document(_hash(session_id))
        doc = ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        expires_at = data.get("expires_at")
        if expires_at is not None and expires_at < _now():
            ref.delete()
            return None
        return data
    except Exception as e:
        logger.warning("Server session lookup failed (%s)", type(e).__name__)
        return None


def save_session(session_id: str, payload: dict) -> bool:
    """세션 값을 저장한다. **항상 전체 치환**이다(merge 아님).

    호출부(HybridSessionInterface)가 세션에서 제거한 키는 payload 에 없고,
    전체 치환이므로 문서에서도 함께 사라진다.
    """
    if _db is None or not session_id:
        return False
    doc = dict(payload)
    doc["updated_at"] = _now()
    doc["expires_at"] = _expires_at()
    doc["schema_version"] = SCHEMA_VERSION
    try:
        ref = _db.collection(SESSIONS_COLLECTION).document(_hash(session_id))
        existing = ref.get()
        created_at = (existing.to_dict() or {}).get("created_at") if existing.exists else None
        doc["created_at"] = created_at or _now()
        ref.set(doc)  # merge=False — 전체 치환
        return True
    except Exception as e:
        logger.warning("Server session save failed (%s)", type(e).__name__)
        return False


def delete_session(session_id: str) -> None:
    """개별 로그아웃 — 이 세션 문서만 삭제한다."""
    if _db is None or not session_id:
        return
    try:
        _db.collection(SESSIONS_COLLECTION).document(_hash(session_id)).delete()
    except Exception as e:
        logger.warning("Server session delete failed (%s)", type(e).__name__)


def delete_all_sessions_for_user(user_key: str) -> int:
    """전체 로그아웃 — 같은 user_key 의 모든 세션 문서를 삭제한다."""
    if _db is None or not user_key:
        return 0
    deleted = 0
    try:
        docs = (
            _db.collection(SESSIONS_COLLECTION)
            .where("user_key", "==", user_key)
            .stream()
        )
        for doc in docs:
            doc.reference.delete()
            deleted += 1
    except Exception as e:
        logger.warning("Server session bulk delete failed (%s)", type(e).__name__)
    return deleted

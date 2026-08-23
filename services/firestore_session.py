"""Firestore 저장소 — 사용자 공통 설정과 기기별 인증 세션의 분리 (P0-3 · P0-4).

구조 (조치안 5.2)

    users/{user_key}
        sheet_id, sheet_title, worksheet_name
        created_at, updated_at, schema_version, user_key_version

    device_sessions/{device_id}
        user_key, refresh_token
        created_at, updated_at, expires_at, schema_version

설계 효과
    - 같은 계정은 모든 기기에서 같은 `user_key` 를 쓴다(멀티 디바이스).
    - 시트 설정은 사용자당 한 번만 저장한다.
    - refresh token 은 기기별로 분리되어 한 기기 로그아웃이 다른 기기를
      끊지 않는다.
    - 동일 브라우저에서 계정을 바꾸면 `user_key` 가 달라지므로 이전 계정의
      시트가 섞이지 않는다(조치안 7.3).

개인정보
    이메일 · 이름 · 프로필 이미지 URL 원문은 어느 컬렉션에도 저장하지 않는다.
    표시용 정보는 Flask 세션 수명 안에서만 사용한다(조치안 5.3).

레거시(`sessions` 컬렉션)
    전환 기간 동안 읽기 경로만 유지하며, 접근 시점에 신규 구조로 옮기고
    원문 개인정보를 제거한다. 전환 종료 후 이 경로와 컬렉션을 제거한다.
"""
import logging
from datetime import datetime, timedelta, timezone

from flask import session

from services.google_credentials import OAUTH_SCOPE_VERSION
from services.user_identity import USER_KEY_VERSION

logger = logging.getLogger(__name__)

USERS_COLLECTION = "users"
DEVICE_SESSIONS_COLLECTION = "device_sessions"
LEGACY_COLLECTION = "sessions"

SCHEMA_VERSION = 2
DEVICE_SESSION_TTL_DAYS = 90

try:
    from google.cloud import firestore as _firestore
    _db = _firestore.Client(database="refresh-token")
    _DELETE_FIELD = _firestore.DELETE_FIELD
except Exception:
    _db = None
    _DELETE_FIELD = None


def get_db():
    return _db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expires_at() -> datetime:
    return _now() + timedelta(days=DEVICE_SESSION_TTL_DAYS)


# ── 사용자 공통 설정: users/{user_key} ─────────────────────────────────────

def get_user_config(user_key: str) -> dict | None:
    if _db is None or not user_key:
        return None
    try:
        doc = _db.collection(USERS_COLLECTION).document(user_key).get()
        return (doc.to_dict() or {}) if doc.exists else None
    except Exception as e:
        logger.warning("Firestore user config lookup failed (%s)", type(e).__name__)
        return None


def save_user_sheet(user_key: str, sheet_id: str, sheet_title: str = "",
                    worksheet_name: str = "") -> bool:
    """사용자 시트 연결 정보를 저장한다.

    `sheet_id` 가 비어 있으면 저장하지 않는다. 재로그인 직후처럼 세션이 비어
    있는 상태에서 기존 연결을 빈 값으로 덮어쓰면 사용자가 시트를 다시
    설정해야 하기 때문이다.
    """
    if _db is None or not user_key or not sheet_id:
        return False
    payload = {
        "sheet_id": sheet_id,
        "sheet_title": sheet_title or "",
        "worksheet_name": worksheet_name or "",
        "updated_at": _now(),
        "schema_version": SCHEMA_VERSION,
        # 키 회전 시 어떤 HMAC 키 버전으로 만든 문서인지 판별한다.
        "user_key_version": USER_KEY_VERSION,
    }
    try:
        ref = _db.collection(USERS_COLLECTION).document(user_key)
        if not ref.get().exists:
            payload["created_at"] = _now()
        ref.set(payload, merge=True)
        return True
    except Exception as e:
        logger.warning("Firestore user sheet save failed (%s)", type(e).__name__)
        return False


def update_sheet_from_session(user_key: str) -> bool:
    """현재 Flask 세션의 시트 정보를 사용자 문서에 반영한다."""
    return save_user_sheet(
        user_key,
        session.get("sheet_id", ""),
        session.get("sheet_title", ""),
        session.get("worksheet_name", ""),
    )


def clear_user_sheet(user_key: str) -> bool:
    """시트 연결 해제 — 사용자 문서의 시트 정보를 비운다.

    비우지 않으면 다음 자동 복원에서 해제한 시트가 다시 연결된다.
    """
    if _db is None or not user_key:
        return False
    try:
        _db.collection(USERS_COLLECTION).document(user_key).set(
            {
                "sheet_id": "",
                "sheet_title": "",
                "worksheet_name": "",
                "updated_at": _now(),
            },
            merge=True,
        )
        return True
    except Exception as e:
        logger.warning("Firestore user sheet clear failed (%s)", type(e).__name__)
        return False


def delete_user(user_key: str) -> bool:
    """계정 삭제 · 연결 해제 시 사용자 문서를 제거한다."""
    if _db is None or not user_key:
        return False
    try:
        _db.collection(USERS_COLLECTION).document(user_key).delete()
        return True
    except Exception as e:
        logger.warning("Firestore user delete failed (%s)", type(e).__name__)
        return False


# ── 기기별 세션: device_sessions/{device_id} ───────────────────────────────

def save_device_session(device_id: str, user_key: str, refresh_token: str,
                        scope_version: int = OAUTH_SCOPE_VERSION) -> bool:
    if _db is None or not device_id or not user_key or not refresh_token:
        return False
    payload = {
        "user_key": user_key,
        "refresh_token": refresh_token,
        "updated_at": _now(),
        "expires_at": _expires_at(),
        "schema_version": SCHEMA_VERSION,
        "user_key_version": USER_KEY_VERSION,
        # 이 refresh token 이 어떤 OAuth 범위 구성으로 발급됐는지 기록한다.
        # 구버전 토큰은 자동 복원을 중단하고 재동의를 요청한다 (task-2026-08-004).
        "scope_version": scope_version,
    }
    try:
        ref = _db.collection(DEVICE_SESSIONS_COLLECTION).document(device_id)
        if not ref.get().exists:
            payload["created_at"] = _now()
        ref.set(payload, merge=True)
        return True
    except Exception as e:
        logger.warning("Firestore device session save failed (%s)", type(e).__name__)
        return False


def get_device_session(device_id: str) -> dict | None:
    if _db is None or not device_id:
        return None
    try:
        doc = _db.collection(DEVICE_SESSIONS_COLLECTION).document(device_id).get()
        return (doc.to_dict() or {}) if doc.exists else None
    except Exception as e:
        logger.warning("Firestore device session lookup failed (%s)", type(e).__name__)
        return None


def get_refresh_token(device_id: str) -> str | None:
    """device_id 로 저장된 refresh_token 을 조회한다.

    refresh_token 은 세션 쿠키(서명만 되고 암호화되지 않음)에 두지 않고
    Firestore 에만 보관하므로, 액세스 토큰 갱신이 실제로 필요한 시점에만
    이 함수로 조회한다.
    """
    data = get_device_session(device_id)
    if data and data.get("refresh_token"):
        return data["refresh_token"]
    legacy = _get_legacy_document(device_id)
    if legacy:
        return legacy.get("refresh_token") or None
    return None


def update_refresh_token(device_id: str, refresh_token: str) -> None:
    """갱신 과정에서 새 refresh_token 이 발급된 경우 저장한다."""
    if _db is None or not device_id or not refresh_token:
        return
    try:
        _db.collection(DEVICE_SESSIONS_COLLECTION).document(device_id).set(
            {
                "refresh_token": refresh_token,
                "updated_at": _now(),
                "expires_at": _expires_at(),
            },
            merge=True,
        )
    except Exception as e:
        logger.warning("Firestore refresh_token update failed (%s)", type(e).__name__)


def touch_device_session(device_id: str) -> None:
    """사용 중인 기기 세션의 TTL 을 연장한다."""
    if _db is None or not device_id:
        return
    try:
        _db.collection(DEVICE_SESSIONS_COLLECTION).document(device_id).set(
            {"updated_at": _now(), "expires_at": _expires_at()}, merge=True
        )
    except Exception as e:
        logger.warning("Firestore device session touch failed (%s)", type(e).__name__)


def delete_device_session(device_id: str) -> None:
    """현재 기기만 로그아웃한다. 다른 기기 세션은 유지된다."""
    if _db is None or not device_id:
        return
    try:
        _db.collection(DEVICE_SESSIONS_COLLECTION).document(device_id).delete()
    except Exception as e:
        logger.warning("Firestore device session delete failed (%s)", type(e).__name__)
    # 전환 기간 동안 남아 있는 레거시 문서도 함께 정리한다.
    try:
        _db.collection(LEGACY_COLLECTION).document(device_id).delete()
    except Exception as e:
        logger.warning("Legacy session delete failed on logout (%s)", type(e).__name__)


def delete_all_device_sessions(user_key: str) -> int:
    """전체 로그아웃 — 해당 사용자의 모든 기기 세션을 삭제한다."""
    if _db is None or not user_key:
        return 0
    deleted = 0
    try:
        docs = (
            _db.collection(DEVICE_SESSIONS_COLLECTION)
            .where("user_key", "==", user_key)
            .stream()
        )
        for doc in docs:
            doc.reference.delete()
            deleted += 1
    except Exception as e:
        logger.warning("Firestore device session bulk delete failed (%s)", type(e).__name__)
    # 아직 신규 구조로 옮겨지지 않은 레거시 기기 세션도 함께 무효화한다.
    try:
        legacy_docs = (
            _db.collection(LEGACY_COLLECTION).where("user_key", "==", user_key).stream()
        )
        for doc in legacy_docs:
            doc.reference.delete()
            deleted += 1
    except Exception as e:
        logger.warning("Legacy session bulk delete failed (%s)", type(e).__name__)
    return deleted


# ── 세션 복원 컨텍스트 ─────────────────────────────────────────────────────

def restore_device_context(device_id: str) -> dict | None:
    """device_id 로 자동 복원에 필요한 최소 정보를 조회한다.

    반환: {"user_key", "refresh_token", "scope_version",
           "source": "device" | "legacy"}
    `source == "legacy"` 인 경우 호출부가 갱신 성공 후
    `upgrade_legacy_device()` 로 신규 구조 이전을 마무리한다.
    `scope_version` 미기록 문서는 구버전(1)으로 취급한다.
    """
    data = get_device_session(device_id)
    if data and data.get("refresh_token"):
        return {
            "user_key": data.get("user_key", ""),
            "refresh_token": data["refresh_token"],
            "scope_version": int(data.get("scope_version") or 1),
            "source": "device",
        }
    legacy = _get_legacy_document(device_id)
    if legacy and legacy.get("refresh_token"):
        return {
            # 다른 기기의 로그인 과정에서 user_key 가 이미 기록됐을 수 있다.
            "user_key": legacy.get("user_key", ""),
            "refresh_token": legacy["refresh_token"],
            # 레거시 문서에는 scope_version 이 없다 → 구버전 취급.
            "scope_version": int(legacy.get("scope_version") or 1),
            "source": "legacy",
        }
    return None


def apply_sheet_to_session(data: dict | None) -> bool:
    """저장된 시트 연결 정보를 Flask 세션으로 복원한다."""
    if not data or not data.get("sheet_id"):
        return False
    session["sheet_id"] = data.get("sheet_id", "")
    session["sheet_title"] = data.get("sheet_title", "")
    session["worksheet_name"] = data.get("worksheet_name", "")
    return True


# ── 레거시(`sessions`) 점진적 마이그레이션 (P0-4) ──────────────────────────

def _get_legacy_document(device_id: str) -> dict | None:
    if _db is None or not device_id:
        return None
    try:
        doc = _db.collection(LEGACY_COLLECTION).document(device_id).get()
        return (doc.to_dict() or {}) if doc.exists else None
    except Exception as e:
        logger.warning("Legacy session lookup failed (%s)", type(e).__name__)
        return None


def _scrub_legacy_document(ref, user_key: str) -> None:
    """레거시 문서에서 원문 개인정보를 제거하고 이전 흔적만 남긴다.

    문서 자체는 즉시 삭제하지 않는다. 아직 재로그인하지 않은 다른 기기가
    같은 문서의 refresh_token 으로 자동 복원되어야 하기 때문이다
    (조치안 9. 롤백 원칙).
    """
    if _DELETE_FIELD is None:
        return
    payload = {
        "email": _DELETE_FIELD,
        "user": _DELETE_FIELD,
        "migrated_at": _now(),
        "schema_version": SCHEMA_VERSION,
    }
    if user_key:
        payload["user_key"] = user_key
    try:
        ref.set(payload, merge=True)
    except Exception as e:
        logger.warning("Legacy session scrub failed (%s)", type(e).__name__)


def migrate_legacy_user(user_key: str, email: str) -> dict | None:
    """레거시 이메일 기반 문서에서 시트 설정을 1회 인수인계한다.

    조건 (조치안 P0-4)
        - `users/{user_key}` 문서가 아직 없을 때만 호출한다.
        - 현재 로그인 이메일과 **정확히 일치**하는 문서만 대상으로 한다.
          (다른 계정의 시트가 연결되는 사고를 막는다)

    반환: 이전한 시트 정보 dict 또는 None
    """
    if _db is None or not user_key or not email:
        return None

    migrated_sheet: dict | None = None
    try:
        docs = list(
            _db.collection(LEGACY_COLLECTION)
            .where("email", "==", email)
            .limit(20)
            .stream()
        )
    except Exception as e:
        logger.warning("Legacy migration lookup failed (%s)", type(e).__name__)
        return None

    candidates = []
    for doc in docs:
        data = doc.to_dict() or {}
        # where 절과 별개로 값 일치를 한 번 더 확인한다.
        if data.get("email") != email:
            continue
        candidates.append((doc.reference, data))

    def _updated_ts(item):
        try:
            return item[1].get("updated_at").timestamp()
        except Exception:
            return 0.0

    for ref, data in sorted(candidates, key=_updated_ts, reverse=True):
        if migrated_sheet is None and data.get("sheet_id"):
            migrated_sheet = {
                "sheet_id": data.get("sheet_id", ""),
                "sheet_title": data.get("sheet_title", ""),
                "worksheet_name": data.get("worksheet_name", ""),
            }
        _scrub_legacy_document(ref, user_key)

    if migrated_sheet:
        save_user_sheet(
            user_key,
            migrated_sheet["sheet_id"],
            migrated_sheet["sheet_title"],
            migrated_sheet["worksheet_name"],
        )
        logger.info("legacy sheet config migrated to new user document")
    return migrated_sheet


def upgrade_legacy_device(device_id: str, user_key: str, refresh_token: str) -> None:
    """레거시 문서로 복원된 기기를 신규 device_sessions 구조로 옮긴다."""
    if _db is None or not device_id or not user_key or not refresh_token:
        return
    if save_device_session(device_id, user_key, refresh_token):
        try:
            ref = _db.collection(LEGACY_COLLECTION).document(device_id)
            _scrub_legacy_document(ref, user_key)
        except Exception as e:
            logger.warning("Legacy device upgrade cleanup failed (%s)", type(e).__name__)

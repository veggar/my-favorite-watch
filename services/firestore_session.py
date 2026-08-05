import logging
from datetime import datetime, timezone

from flask import session

logger = logging.getLogger(__name__)

try:
    from google.cloud import firestore as _firestore
    _db = _firestore.Client(database="refresh-token")
except Exception:
    _db = None


def get_db():
    return _db


def save_session(device_id: str, refresh_token: str, user_info: dict):
    if _db is None or not refresh_token:
        return
    payload = {
        "email": user_info.get("email", ""),
        "refresh_token": refresh_token,
        "user": user_info,
        "updated_at": datetime.now(timezone.utc),
    }
    # 시트 정보는 세션에 값이 있을 때만 기록한다.
    # 재로그인 직후처럼 세션이 비어 있는 상태에서 기존 연결 정보를
    # 빈 값으로 덮어쓰면 사용자가 시트를 다시 설정해야 하기 때문이다.
    if session.get("sheet_id"):
        payload.update(
            {
                "sheet_id": session.get("sheet_id", ""),
                "sheet_title": session.get("sheet_title", ""),
                "worksheet_name": session.get("worksheet_name", ""),
            }
        )
    try:
        _db.collection("sessions").document(device_id).set(payload, merge=True)
    except Exception:
        logger.warning("Firestore save failed", exc_info=True)


def get_refresh_token(device_id: str) -> str | None:
    """device_id 로 저장된 refresh_token 을 조회한다.

    refresh_token 은 세션 쿠키(서명만 되고 암호화되지 않음)에 두지 않고
    Firestore 에만 보관하므로, 액세스 토큰 갱신이 실제로 필요한 시점에만
    이 함수로 조회한다.
    """
    if _db is None or not device_id:
        return None
    try:
        doc = _db.collection("sessions").document(device_id).get()
        if not doc.exists:
            return None
        return (doc.to_dict() or {}).get("refresh_token") or None
    except Exception:
        logger.warning("Firestore refresh_token lookup failed", exc_info=True)
        return None


def update_refresh_token(device_id: str, refresh_token: str) -> None:
    """갱신 과정에서 새 refresh_token 이 발급된 경우 저장한다."""
    if _db is None or not device_id or not refresh_token:
        return
    try:
        _db.collection("sessions").document(device_id).set(
            {
                "refresh_token": refresh_token,
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )
    except Exception:
        logger.warning("Firestore refresh_token update failed", exc_info=True)


def lookup_saved_sheet(device_id: str, email: str = "") -> dict | None:
    """저장된 시트 연결 정보를 device_id 우선, 없으면 email 기준으로 조회한다."""
    if _db is None:
        return None
    try:
        if device_id:
            doc = _db.collection("sessions").document(device_id).get()
            if doc.exists:
                data = doc.to_dict() or {}
                if data.get("sheet_id"):
                    return data
        if email:
            # device_id 쿠키가 사라졌거나 기기를 바꾼 경우에도
            # 동일 계정의 마지막 연결 정보를 재사용한다.
            docs = _db.collection("sessions").where("email", "==", email).limit(20).stream()
            candidates = [d.to_dict() or {} for d in docs]
            candidates = [c for c in candidates if c.get("sheet_id")]
            if candidates:
                def _updated_ts(c):
                    # Firestore는 tz-aware datetime을 반환하므로 naive 값과의
                    # 직접 비교를 피하기 위해 epoch 초로 정규화한다.
                    try:
                        return c.get("updated_at").timestamp()
                    except Exception:
                        return 0.0

                candidates.sort(key=_updated_ts, reverse=True)
                return candidates[0]
    except Exception:
        logger.warning("Firestore saved sheet lookup failed", exc_info=True)
    return None


def apply_sheet_to_session(data: dict | None) -> bool:
    """Firestore 문서의 시트 연결 정보를 Flask 세션으로 복원한다."""
    if not data or not data.get("sheet_id"):
        return False
    session["sheet_id"] = data.get("sheet_id", "")
    session["sheet_title"] = data.get("sheet_title", "")
    session["worksheet_name"] = data.get("worksheet_name", "")
    return True


def update_sheet(device_id: str):
    if _db is None or not device_id:
        return
    try:
        _db.collection("sessions").document(device_id).update(
            {
                "sheet_id": session.get("sheet_id", ""),
                "sheet_title": session.get("sheet_title", ""),
                "worksheet_name": session.get("worksheet_name", ""),
                "updated_at": datetime.now(timezone.utc),
            }
        )
    except Exception:
        logger.warning("Firestore sheet update failed", exc_info=True)


def delete_session(device_id: str):
    if _db is None or not device_id:
        return
    try:
        _db.collection("sessions").document(device_id).delete()
    except Exception:
        logger.warning("Firestore delete failed on logout", exc_info=True)

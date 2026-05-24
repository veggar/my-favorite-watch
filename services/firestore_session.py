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
    try:
        _db.collection("sessions").document(device_id).set(
            {
                "email": user_info.get("email", ""),
                "refresh_token": refresh_token,
                "user": user_info,
                "sheet_id": session.get("sheet_id", ""),
                "sheet_title": session.get("sheet_title", ""),
                "worksheet_name": session.get("worksheet_name", ""),
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )
    except Exception:
        logger.warning("Firestore save failed", exc_info=True)


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

"""CSV·Excel 미리보기 → 등록 사이의 임시 파싱 결과를 서버 측에 보관.

이전 구현은 `session["csv_import_data"]`에 파싱 결과를 직접 담았다.
`__session` 쿠키는 서명만 되고 암호화되지 않으므로, 후기·줄거리 등 개인정보가
섞일 수 있는 가져오기 원본 데이터가 평문으로 브라우저에 노출됐다
(PRD §16.1, `docs/legal/privacy-policy-draft.md` "배포 전 필수 확인").

이 모듈은 `services/tmdb_tracker.py`·`services/server_session.py`와 같은
패턴을 따른다. 쿠키에는 예측 불가능한 staging id만 남기고, 실제 데이터는
Firestore(또는 로컬 개발 시 프로세스 메모리)에 짧은 TTL로 보관한다.

    save(items)              -> staging_id (세션 쿠키에 저장)
    load_and_clear(staging_id) -> items | None (1회용 — 조회 즉시 삭제)

문서 키는 `server_session`과 동일하게 staging id 원본이 아니라 sha256
해시를 쓴다. 미리보기 후 등록하지 않고 이탈한 데이터는 TTL로 정리된다
(Firestore 콘솔에 `expires_at` 기준 TTL 정책 필요 — SETUP.md 참조).
"""
import hashlib
import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

COLLECTION = "csv_import_staging"
STAGING_ID_BYTES = 32
# 미리보기 확인 후 등록까지의 정상 소요 시간보다 넉넉하되, 유출 노출 창을
# 최소화하도록 짧게 유지한다.
TTL_MINUTES = 30

# Firestore 미구성 환경(로컬 개발)용 폴백 저장소.
# tmdb_tracker 와 동일하게 단일 프로세스 안에서만 공유됨을 전제로 한다.
_fallback: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _collection():
    from services.firestore_session import get_db

    db = get_db()
    if db is None:
        return None
    return db.collection(COLLECTION)


def _hash(staging_id: str) -> str:
    """문서 키용 해시. 원본 staging id는 어디에도 저장하지 않는다."""
    return hashlib.sha256(staging_id.encode("utf-8")).hexdigest()


def _expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTES)


def save(items: list[dict]) -> str:
    """파싱 결과를 저장하고, 세션 쿠키에 담을 staging id를 돌려준다."""
    staging_id = secrets.token_urlsafe(STAGING_ID_BYTES)

    col = _collection()
    if col is None:
        with _lock:
            _fallback[staging_id] = items
        return staging_id

    try:
        col.document(_hash(staging_id)).set({
            "items": items,
            "expires_at": _expires_at(),
        })
    except Exception:
        logger.warning("csv_import_staging save failed; falling back to memory", exc_info=True)
        with _lock:
            _fallback[staging_id] = items
    return staging_id


def load_and_clear(staging_id: str) -> list[dict] | None:
    """저장된 파싱 결과를 조회하고 즉시 삭제한다(1회용). 없거나 만료되면 None."""
    if not staging_id:
        return None

    col = _collection()
    if col is None:
        with _lock:
            return _fallback.pop(staging_id, None)

    try:
        ref = col.document(_hash(staging_id))
        doc = ref.get()
        if not doc.exists:
            # Firestore 쓰기가 일시적으로 실패해 메모리 폴백에 남아 있을 수 있다.
            with _lock:
                return _fallback.pop(staging_id, None)
        data = doc.to_dict() or {}
        ref.delete()
        expires_at = data.get("expires_at")
        if expires_at is not None and expires_at < datetime.now(timezone.utc):
            return None
        return data.get("items")
    except Exception:
        logger.warning("csv_import_staging load failed", exc_info=True)
        with _lock:
            return _fallback.pop(staging_id, None)

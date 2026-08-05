"""TMDb 보강 작업의 진행 상태 추적.

이전 구현은 프로세스 메모리 dict 를 사용했다. 그러나 gunicorn 이 워커를
여러 개 fork 하고(`--workers 2`) Cloud Run 이 인스턴스를 수평 확장하면
상태 dict 가 프로세스마다 따로 존재하게 되어, 상태 조회 요청이 보강을
수행한 프로세스가 아닌 곳으로 라우팅되면 빈 값이 반환됐다.
(계획서 P0-3 원인 1 · 3)

Firestore 컬렉션 `tmdb_jobs`(문서 ID = item_id)로 이관하여 프로세스 ·
인스턴스 경계를 넘어 상태를 공유한다. Firestore 를 사용할 수 없는 로컬
개발 환경에서는 기존과 동일하게 메모리 dict 로 자동 폴백한다.

상태 값: "pending" | "searching" | "done" | "not_found"

완료 문서 정리
    문서에 `expires_at` 필드를 기록한다. Firestore 콘솔에서 `tmdb_jobs`
    컬렉션에 `expires_at` 기준 TTL 정책을 설정하면 자동 삭제된다.
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

COLLECTION = "tmdb_jobs"
TTL_HOURS = 24

# Firestore 쓰기 배치 상한(500)보다 넉넉히 낮게 잡는다.
_BATCH_LIMIT = 400

# Firestore 미구성 환경용 폴백 저장소
_statuses: dict[str, str] = {}
_lock = threading.Lock()


def _collection():
    from services.firestore_session import get_db

    db = get_db()
    if db is None:
        return None
    return db.collection(COLLECTION)


def _expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=TTL_HOURS)


# ── 공개 인터페이스 ────────────────────────────────────────────────────────

def mark_pending(item_ids: list[str]) -> None:
    set_statuses({id_: "pending" for id_ in item_ids if id_})


def set_status(item_id: str, status: str) -> None:
    if item_id:
        set_statuses({item_id: status})


def set_statuses(statuses: dict[str, str]) -> None:
    """여러 항목의 상태를 한 번에 기록한다(배치 쓰기)."""
    statuses = {k: v for k, v in statuses.items() if k}
    if not statuses:
        return

    col = _collection()
    if col is None:
        with _lock:
            _statuses.update(statuses)
        return

    try:
        from services.firestore_session import get_db

        db = get_db()
        expires_at = _expires_at()
        items = list(statuses.items())
        for start in range(0, len(items), _BATCH_LIMIT):
            batch = db.batch()
            for item_id, status in items[start:start + _BATCH_LIMIT]:
                batch.set(
                    col.document(item_id),
                    {"status": status, "expires_at": expires_at},
                )
            batch.commit()
    except Exception:
        logger.warning("tmdb_tracker set_statuses failed", exc_info=True)
        with _lock:
            _statuses.update(statuses)


def get_statuses(item_ids: list[str]) -> dict[str, str]:
    item_ids = [i for i in item_ids if i]
    if not item_ids:
        return {}

    col = _collection()
    if col is None:
        with _lock:
            return {id_: _statuses.get(id_, "") for id_ in item_ids}

    try:
        from services.firestore_session import get_db

        db = get_db()
        result = {id_: "" for id_ in item_ids}
        refs = [col.document(id_) for id_ in item_ids]
        for doc in db.get_all(refs):
            if doc.exists:
                result[doc.id] = (doc.to_dict() or {}).get("status", "")
        # 쓰기가 일시적으로 실패해 메모리로 폴백된 값이 있으면 함께 반영한다.
        if _statuses:
            with _lock:
                for id_ in item_ids:
                    if not result[id_] and _statuses.get(id_):
                        result[id_] = _statuses[id_]
        return result
    except Exception:
        logger.warning("tmdb_tracker get_statuses failed", exc_info=True)
        with _lock:
            return {id_: _statuses.get(id_, "") for id_ in item_ids}


def clear(item_ids: list[str]) -> None:
    item_ids = [i for i in item_ids if i]
    if not item_ids:
        return

    col = _collection()
    if col is None:
        with _lock:
            for id_ in item_ids:
                _statuses.pop(id_, None)
        return

    try:
        from services.firestore_session import get_db

        db = get_db()
        for start in range(0, len(item_ids), _BATCH_LIMIT):
            batch = db.batch()
            for item_id in item_ids[start:start + _BATCH_LIMIT]:
                batch.delete(col.document(item_id))
            batch.commit()
    except Exception:
        logger.warning("tmdb_tracker clear failed", exc_info=True)
    with _lock:
        for id_ in item_ids:
            _statuses.pop(id_, None)

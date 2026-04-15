"""
TMDb 비동기 보강 작업의 상태를 추적하는 모듈.
서버 메모리에 저장되므로 재시작 시 초기화됨.
"""
import threading

# item_id → "pending" | "searching" | "done" | "not_found"
_statuses: dict[str, str] = {}
_lock = threading.Lock()


def mark_pending(item_ids: list[str]) -> None:
    with _lock:
        for id_ in item_ids:
            _statuses[id_] = "pending"


def set_status(item_id: str, status: str) -> None:
    with _lock:
        _statuses[item_id] = status


def get_statuses(item_ids: list[str]) -> dict[str, str]:
    with _lock:
        return {id_: _statuses.get(id_, "") for id_ in item_ids}


def clear(item_ids: list[str]) -> None:
    with _lock:
        for id_ in item_ids:
            _statuses.pop(id_, None)

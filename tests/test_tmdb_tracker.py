"""P0-3 재현/회귀 테스트.

재현 대상
    tmdb_tracker 가 프로세스 메모리 dict 를 쓰면 gunicorn 워커가 2개일 때
    보강을 수행한 워커와 상태를 조회하는 워커가 달라 빈 값이 반환된다.
    (계획서 P0-3 원인 1 · 3)

검증 방식
    "다른 프로세스"를 메모리 dict 초기화로 흉내 낸다. 공유 저장소(Firestore)
    가 붙어 있으면 메모리를 비워도 상태를 읽을 수 있어야 한다.

실행: pytest -q
"""
import pytest

import services.tmdb_tracker as tracker


# ── Firestore 스텁 ────────────────────────────────────────────────────────

class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Ref:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return _Doc(self.id, self._store.get(self.id))


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _Ref(self._store, doc_id)


class _Batch:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def set(self, ref, data):
        self._ops.append(("set", ref.id, data))

    def delete(self, ref):
        self._ops.append(("delete", ref.id, None))

    def commit(self):
        for op, doc_id, data in self._ops:
            if op == "set":
                self._store[doc_id] = data
            else:
                self._store.pop(doc_id, None)
        self._ops = []


class _FakeDb:
    """프로세스 경계를 넘어 공유되는 저장소를 흉내 낸다."""

    def __init__(self):
        self.store = {}

    def collection(self, _name):
        return _Collection(self.store)

    def batch(self):
        return _Batch(self.store)

    def get_all(self, refs):
        return [ref.get() for ref in refs]


@pytest.fixture()
def shared_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("services.firestore_session.get_db", lambda: db)
    tracker._statuses.clear()
    yield db
    tracker._statuses.clear()


@pytest.fixture()
def no_db(monkeypatch):
    monkeypatch.setattr("services.firestore_session.get_db", lambda: None)
    tracker._statuses.clear()
    yield
    tracker._statuses.clear()


# ── 재현: 메모리 저장소는 프로세스 경계를 넘지 못한다 ──────────────────────

def test_memory_fallback_loses_state_across_processes(no_db):
    """Firestore 가 없으면 다른 프로세스의 상태를 읽지 못한다(기존 버그 재현)."""
    tracker.mark_pending(["a", "b"])
    tracker.set_status("a", "done")

    # 다른 gunicorn 워커 = 별도 메모리 공간
    tracker._statuses.clear()

    assert tracker.get_statuses(["a", "b"]) == {"a": "", "b": ""}


# ── 회귀: 공유 저장소로 교체하면 프로세스 경계를 넘어 조회된다 ─────────────

def test_shared_store_survives_across_processes(shared_db):
    tracker.mark_pending(["a", "b"])
    tracker.set_status("a", "done")

    # 다른 워커/인스턴스를 흉내 내어 로컬 메모리를 비운다
    tracker._statuses.clear()

    assert tracker.get_statuses(["a", "b"]) == {"a": "done", "b": "pending"}


def test_unknown_ids_return_empty_string(shared_db):
    tracker.mark_pending(["a"])
    assert tracker.get_statuses(["a", "zzz"]) == {"a": "pending", "zzz": ""}


def test_set_statuses_batches_writes(shared_db):
    ids = [f"id-{i}" for i in range(950)]  # _BATCH_LIMIT(400) 초과
    tracker.mark_pending(ids)
    tracker._statuses.clear()
    result = tracker.get_statuses(ids)
    assert len(result) == 950
    assert set(result.values()) == {"pending"}


def test_clear_removes_from_shared_store(shared_db):
    tracker.mark_pending(["a", "b"])
    tracker.clear(["a"])
    tracker._statuses.clear()
    assert tracker.get_statuses(["a", "b"]) == {"a": "", "b": "pending"}


def test_expires_at_is_written_for_ttl(shared_db):
    tracker.mark_pending(["a"])
    assert "expires_at" in shared_db.store["a"]


def test_empty_input_is_noop(shared_db):
    tracker.mark_pending([])
    tracker.clear([])
    assert tracker.get_statuses([]) == {}
    assert shared_db.store == {}


def test_falls_back_to_memory_when_firestore_raises(monkeypatch):
    class _BrokenDb(_FakeDb):
        def batch(self):
            raise RuntimeError("firestore unavailable")

    monkeypatch.setattr("services.firestore_session.get_db", lambda: _BrokenDb())
    tracker._statuses.clear()
    tracker.mark_pending(["a"])
    # Firestore 실패 시에도 조용히 죽지 않고 메모리로 폴백해야 한다
    assert tracker.get_statuses(["a"]) == {"a": "pending"}
    tracker._statuses.clear()

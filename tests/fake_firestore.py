"""테스트용 인메모리 Firestore 대역.

실제 Firestore 를 붙이지 않고 `services.firestore_session` 의 문서 구조와
삭제 필드 동작을 검증하기 위한 최소 구현이다. 지원 범위는 이 저장소가
실제로 사용하는 호출(`document/get/set/delete`, `where/limit/stream`)로
한정한다.
"""


class _DeleteSentinel:
    def __repr__(self):  # pragma: no cover - 디버깅 편의용
        return "<DELETE_FIELD>"


DELETE_FIELD = _DeleteSentinel()


class FakeSnapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self._data = data

    @property
    def id(self):
        return self.reference.id

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocumentRef:
    def __init__(self, store: dict, doc_id: str):
        self._store = store
        self.id = doc_id

    def get(self):
        return FakeSnapshot(self, self._store.get(self.id))

    def set(self, payload: dict, merge: bool = False):
        current = dict(self._store.get(self.id) or {}) if merge else {}
        for key, value in payload.items():
            if value is DELETE_FIELD:
                current.pop(key, None)
            else:
                current[key] = value
        self._store[self.id] = current

    def update(self, payload: dict):
        if self.id not in self._store:
            raise KeyError(self.id)
        self.set(payload, merge=True)

    def delete(self):
        self._store.pop(self.id, None)


class FakeQuery:
    def __init__(self, store: dict, filters=None, limit=None):
        self._store = store
        self._filters = list(filters or [])
        self._limit = limit

    def where(self, field, op, value):
        if op != "==":
            raise NotImplementedError(f"unsupported operator: {op}")
        return FakeQuery(self._store, self._filters + [(field, value)], self._limit)

    def limit(self, count):
        return FakeQuery(self._store, self._filters, count)

    def stream(self):
        results = []
        for doc_id, data in list(self._store.items()):
            if all(data.get(field) == value for field, value in self._filters):
                results.append(FakeSnapshot(FakeDocumentRef(self._store, doc_id), data))
        if self._limit is not None:
            results = results[: self._limit]
        return iter(results)


class FakeCollection(FakeQuery):
    def document(self, doc_id: str):
        return FakeDocumentRef(self._store, doc_id)


class FakeFirestoreClient:
    def __init__(self):
        self.collections: dict[str, dict] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.collections.setdefault(name, {}))

    # ── 테스트 헬퍼 ────────────────────────────────────────────────────
    def docs(self, name: str) -> dict:
        return self.collections.setdefault(name, {})

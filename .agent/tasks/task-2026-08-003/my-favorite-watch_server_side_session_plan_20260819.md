# My Favorite Watch — 완전한 서버 측 세션 도입 계획 (task-2026-08-003)

- 작성일: 2026-08-19
- 문서 성격: 계획. 이 문서 작성만으로 `my-favorite-watch`의 코드 변경, 배포를
  승인하거나 수행한 것으로 보지 않는다.
- 근거: `.agent/tasks/task-2026-08-002`의 두 조치안(`my-favorite-watch_auth_multidevice_privacy_remediation_20260818.md`,
  `my-favorite-watch_firebase_hosting_session_remediation_r2_20260819.md`)이 이미
  검증된 `sub` 기반 HMAC `user_key`와 `users`/`device_sessions` 스키마 분리까지는
  구현·머지했다(`v1.5.0`). 이 문서는 그 다음 단계인 **완전한 서버 측 세션**
  (조치안 A-5, "브라우저에는 예측 불가능한 세션 ID만 두는 서버 측 세션으로 전환")을 다룬다.
- 자매 프로젝트 `veggar/password-manager`(로컬 `first-by-claude-code`)에서 동일한
  항목을 `task-2026-08-002` P1-2 확장으로 이미 구현·검증했다(브랜치
  `claude/p1-user-key-session-schema`, PR #9). 이 문서는 그 구현을
  `my-favorite-watch`의 실제 파일 구조와 필드명에 맞춰 옮기는 계획이다.

## 1. 문제

`app.py`의 Flask 세션 쿠키(`__session`)는 **서명되지만 암호화되지 않는다**.
현재 `auth_callback`(`routes/auth.py`)은 `session["credentials"]`에 access
token을 직접 담고, `session["user_key"]`, `session["user"]`(표시용 이름·이메일·
프로필 이미지)도 쿠키에 직접 담긴다. 쿠키 값을 얻은 사람은 base64 디코드만으로
이 값을 전부 읽을 수 있다 — 서명은 변조 방지이지 비공개가 아니다.

두 조치안 모두 이를 "프로덕션 확대 전 보안 게이트"로 명시했다.

## 2. 목표 구조

```text
server_sessions/{sha256(session_id)}
  device_id
  user_key
  credentials          # {token, expiry}
  user                 # {name, email, picture} — 표시용, 단기
  sheet_id, sheet_title, worksheet_name
  auth_at
  created_at, updated_at, expires_at, schema_version
```

- 브라우저 `__session` 쿠키에는 **`session_id`(예측 불가능한 랜덤 값)와
  비민감 값**(`device_id`, `oauth_state`, `code_verifier`, `_csrf_token`)만
  서명해서 둔다.
- `device_id`는 의도적으로 서버 측으로 옮기지 않는다. 로그아웃 시
  `server_sessions` 문서는 삭제되지만, "이 기기를 알아본다"(계정 선택 화면,
  `prompt=select_account` 판단)는 `device_id`는 로그아웃 이후에도 살아있어야
  하기 때문이다. `device_id` 자체는 비밀값이 아니다 — Firestore 접근 권한 없이는
  아무 의미가 없는 상관관계 식별자일 뿐이다.
- CSRF 토큰도 서버 측으로 옮기지 않는다. CSRF 토큰의 보안 모델은 애초에
  "클라이언트가 값을 알고 있어야" 성립하므로(폼에 그대로 노출), 쿠키에 두는 것
  자체가 문제가 아니다.

## 3. 구현 방식 — SessionInterface 교체 (라우트 코드 무변경)

**핵심 설계 결정**: Flask의 `session["key"] = value` API를 쓰는 기존 코드
(`routes/auth.py`, `routes/main.py`, `routes/sheet.py`, `routes/settings.py`,
`routes/item.py` 전체)를 **한 줄도 바꾸지 않는다.** 대신 Flask에게 "세션을
어디에 저장할지"만 바꾸는 커스텀 `flask.sessions.SessionInterface`를 등록한다.
Flask-Session 확장이 Redis/Firestore 등을 붙일 때 쓰는 것과 같은 표준 방식이다.

### 3.1 신규 파일 `services/server_session.py`

`first-by-claude-code`의 `services/server_session.py`를 그대로 이식하되
다음만 이 프로젝트에 맞춘다.

- `SESSION_TTL_DAYS = 90` — `DEVICE_SESSION_DAYS`(기존 `app.py`의
  `PERMANENT_SESSION_LIFETIME=timedelta(days=DEVICE_SESSION_DAYS)`)와 맞춘다.
  `password-manager`는 30일이라 값이 다르다 — **반드시 이 프로젝트의 기존
  쿠키 수명(90일)에 맞출 것.**
- Firestore 데이터베이스 이름은 기존과 동일하게 `database="refresh-token"` 유지
  (`services/firestore_session.py`와 이미 일치).

핵심 함수 (변경 없이 그대로 이식):

```python
def is_configured() -> bool: ...          # _db is not None
def new_session_id() -> str: ...          # secrets.token_urlsafe(32)
def _hash(session_id: str) -> str: ...    # sha256 — 원본 대신 해시를 문서 키로
def get_session(session_id: str) -> dict | None: ...   # 만료 시 None
def save_session(session_id: str, payload: dict) -> bool: ...  # 항상 전체 치환(merge 아님)
def delete_session(session_id: str) -> None: ...
def delete_all_sessions_for_user(user_key: str) -> int: ...   # 전체 로그아웃용
```

`save_session`이 **전체 치환**이어야 하는 이유: 인증 신선도 만료로
`session.pop("credentials")`가 일어나면, 그 다음 저장에서 `credentials` 키
자체가 payload에 없어야 Firestore 문서에서도 사라진다. `merge=True`를 쓰면
지운 필드가 계속 남는다 — 이 프로젝트의 `services/firestore_session.py`가
이미 같은 이유로 `_scrub_legacy_document`에서 `DELETE_FIELD`를 쓰는 것과
같은 원칙이다.

### 3.2 신규 파일 `services/hybrid_session.py`

`first-by-claude-code`의 `services/hybrid_session.py`를 이식하되
`SERVER_SIDE_KEYS`만 이 프로젝트 필드명에 맞춘다.

```python
SERVER_SIDE_KEYS = frozenset({
    "credentials", "user_key", "user",
    "sheet_id", "sheet_title", "worksheet_name",
    "auth_at",
})
```

`HybridSessionInterface`는 `flask.sessions.SecureCookieSessionInterface`를
상속해 `open_session`/`save_session`만 오버라이드한다(`get_signing_serializer`,
`get_cookie_domain` 등 기존 메서드는 그대로 재사용 — Flask 기본 쿠키 서명·
`SameSite`/`Secure`/`HttpOnly` 설정과 100% 동일하게 유지된다).

- `open_session`: 쿠키를 복호화해 `session_id`를 꺼낸 뒤,
  `server_session.is_configured()`이면 Firestore에서 나머지 값을 조회해
  병합한다. 문서가 없으면(만료·삭제) `session_id`도 버린다.
- `save_session`: `session.modified`일 때만 Firestore에 쓴다(매 요청마다
  슬라이딩 만료로 쿠키만 다시 보내는 것과는 분리 — 실제 값이 바뀔 때만 쓰기
  발생, 쓰기 비용이 지금과 비슷한 수준으로 유지됨). `SERVER_SIDE_KEYS`에 해당
  하는 키만 Firestore로, 나머지는 쿠키로 나뉜다.
- **Firestore 미구성 시 자동 폴백**: `is_configured()`가 False면 예전처럼
  모든 값을 쿠키에 직접 담는다. 이 덕분에 (a) 로컬 개발(자격증명 없음)이
  그대로 동작하고, (b) 배포 직후 기존 쿠키(신규 `session_id` 없이 구 필드가
  최상위에 있는 형태)도 여전히 읽히며, 값이 바뀌는 다음 요청부터 자연스럽게
  신규 구조로 넘어간다 — **강제 재로그인이 필요 없다.**

### 3.3 `app.py` 변경 — 딱 두 줄

```python
from services.hybrid_session import HybridSessionInterface
...
app.session_interface = HybridSessionInterface()   # app.secret_key 설정 직후
```

`routes/*.py`의 `session[...]` 사용처는 전부 그대로 둔다.

### 3.4 `routes/auth.py`의 `logout_all` 보강

기존 `delete_all_device_sessions(user_key)` 호출에 아래를 추가한다.

```python
from services import server_session
...
def logout_all():
    user_key = session.get("user_key")
    if user_key:
        device_count = delete_all_device_sessions(user_key)
        server_count = server_session.delete_all_sessions_for_user(user_key)
        logger.info("full logout: %d device session(s), %d server session(s) removed",
                    device_count, server_count)
    session.clear()
    ...
```

개별 `/logout`은 코드 변경이 필요 없다. `session.clear()`가 세션을 비우면
`HybridSessionInterface.save_session`의 `if not session:` 분기가
`server_session.delete_session(sid)`를 자동으로 호출한다.

## 4. `first-by-claude-code`에서 구현 중 발견한 주의사항 (그대로 적용)

1. **Firestore 상수(`DELETE_FIELD` 등)를 `Client()` 생성과 같은 `try`에 두지
   말 것.** 이 프로젝트의 `services/firestore_session.py`를 먼저 확인해서
   같은 패턴이 있는지 점검한다 — 자격증명 없는 환경에서 `Client()`만 실패해도
   상수까지 함께 `None`이 되어, 개인정보 제거 로직이 조용히 아무 일도 하지
   않는 채 "성공"할 수 있다.
2. 로그아웃 폼에 `csrf_token` hidden 필드가 있는지 템플릿을 확인한다.
   `password-manager`에서는 이게 빠져 있어 로그아웃 버튼이 실제로는 작동하지
   않는 기존 버그가 있었다.

## 5. 테스트 계획

`first-by-claude-code`의 `tests/test_server_session.py` 구조를 참고해
아래를 검증한다. 특히 "쿠키에 민감한 값이 실제로 안 남는지"는 문자열
포함 여부가 아니라 **같은 서명 키로 쿠키를 직접 복호화해서** 키 목록을
확인해야 한다(base64/서명 때문에 리터럴 문자열 검사는 신뢰할 수 없다).

- `services/server_session.py` 단위 테스트: 저장/조회/삭제/만료/전체 삭제,
  `save_session`이 merge가 아니라 전체 치환인지
- `session_id`가 아니라 그 해시가 Firestore 문서 키로 쓰이는지
- Firestore 구성 시: 쿠키를 복호화해 `SERVER_SIDE_KEYS`가 하나도 없는지,
  `device_id`는 쿠키에 남아있는지
- Firestore 미구성 시: 예전처럼 값이 쿠키에 직접 담기는 폴백 동작
- 개별 로그아웃 시 해당 `server_sessions` 문서만 삭제되는지
- 전체 로그아웃 시 같은 `user_key`의 모든 `server_sessions`가 삭제되는지
- `server_sessions` 문서가 사라지면(만료 등) 쿠키에 `session_id`가 남아있어도
  로그인 필요 라우트가 재인증을 요구하는지

## 6. 배포 순서 권고

1. 로컬에서 `USER_KEY_HMAC_SECRET` 등 기존 환경변수로 회귀 테스트 통과 확인
2. Firestore 미구성 폴백 경로를 로컬(자격증명 제거 상태)에서 수동 확인
3. 배포 후 `04-verify-after-deploy.sh` 류 스크립트가 있다면, 로그인 후
   DevTools에서 쿠키 값이 예전보다 훨씬 짧아졌는지(≈session_id 길이) 확인
4. 기존 로그인 사용자가 재로그인 없이 유지되는지(폴백→신규 전환 확인),
   전체 로그아웃이 다른 기기에도 실제로 반영되는지 실환경 확인

## 7. 이 계획에 포함하지 않은 것

- P2(공개 운영 준비) 전체
- Firestore TTL 정책의 `ACTIVE` 상태 확인(스키마 도입 후 별도 확인 필요)
- Secret Manager 전환 상태 재확인(이미 조치안 P1-4에서 다뤄졌다면 생략)

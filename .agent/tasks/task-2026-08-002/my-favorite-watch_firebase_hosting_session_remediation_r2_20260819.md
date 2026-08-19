# My Favorite Watch 인증·세션 조치안 (개정 2판) — Firebase Hosting 환경

- 작성일: 2026-08-19
- 초판: `my-favorite-watch_auth_multidevice_privacy_remediation_20260818.md` (2026-08-18)
- 대상 저장소: veggar/my-favorite-watch
- 적용 기준: `master` (`210bdb0`, 초판 P0-1~P0-4 반영 완료, 배포 리비전 `my-favorite-watch-00006-rxn`)
- 개정 사유: 초판 배포 후 로그인이 `AUTH_STATE_MISSING`으로 실패. 근본 원인이 코드가 아니라 **Firebase Hosting의 쿠키 전달 제약**으로 확인됨
- 문서 성격: 기술 조치안. 개인정보 관련 최종 판단은 초판과 동일하게 담당자 검토가 필요하다

### 구현 반영 현황 (2026-08-19)

| 항목 | 상태 | 비고 |
|---|---|---|
| P0-5-1 쿠키 통합 | 구현 | `SESSION_COOKIE_NAME="__session"`, 쿠키 90일, `device_id` 세션 이동 |
| P0-5-2 논리적 2계층 | 구현 | `services/session_state.py` + `expire_stale_credentials` |
| P0-5-3 캐시 안전 헤더 | 구현 | `prevent_cdn_caching` (정적 파일 제외) |
| P0-5-4 진단 보강 | 구현 | 쿠키 이름 목록·host 헤더 로깅, `AUTH_COOKIE_BLOCKED` |
| P0-6 Hosting 구성 | 구현 | `hosting/firebase.json` · `.firebaserc.example` · `README.md` |
| P0-7 문서 갱신 | 구현 | `PRD.md` 4.2, `SETUP.md` 9.0, `.env.example`, `version.py` v1.5.0 |
| 2.6 Host 확인 | **미확인** | 배포 후 콜백 로그의 `host=` · `fh_host=` 값으로 판정 필요 |

회귀 테스트 105건 통과(신규 27건). 미확인 항목은 배포 후 5.2에서 확정한다.

---

## 1. 개정 요약

### 1.1 확인된 사실

1. **커스텀 도메인은 Cloud Run 직결이 아니라 Firebase Hosting을 경유한다.**
   - `gcloud beta run domain-mappings list` → 0건
   - `mfw.worldapex.studio` → CNAME `my-favorite-watch.web.app` → `199.36.158.100`
   - 응답 헤더에 `x-served-by: cache-icn…`, `x-cache: MISS`, `vary: … x-fh-requested-host`

2. **서버는 정상 동작한다.** `/auth/google` 응답에 세션 쿠키가 정상적으로 실려 나간다.

   ```text
   set-cookie: session=…; Path=/; HttpOnly; Secure; SameSite=Lax
   ```

3. **콜백 요청에는 그 쿠키가 도달하지 않는다.** 애플리케이션 로그에 동일 리비전에서
   `OAuth callback rejected: oauth_state missing in session`이 반복 기록됐다.
   리비전이 하나뿐이므로 `FLASK_SECRET_KEY` 불일치가 아니고, 매 시도마다
   `/auth/google` → 콜백 쌍이 존재하므로 새로고침·재방문도 아니다.

4. **원인은 Firebase Hosting의 쿠키 정책이다.** Firebase Hosting은 백엔드로 요청을
   전달할 때 **`__session`이라는 이름의 쿠키만 통과시키고 나머지 쿠키는 모두 제거**한다.
   현재 앱은 `session`과 `device_id` 두 쿠키를 쓰므로 둘 다 백엔드에 도달하지 못한다.

5. **초판이 놓친 지점.** 초판 1.1-2는 도메인 변경 후 "기기별 1회 재로그인"을 정상
   동작으로 정의했다. 그러나 실제로는 재로그인 자체가 **영구히 완료될 수 없는** 상태였다.
   같은 이유로 `device_id` 기반 자동 세션 복원과 90일 장기 로그인도 이 도메인에서는
   한 번도 동작한 적이 없다.

### 1.2 초판 승인 항목의 변경

| 번호 | 항목 | 초판 | 개정 2판 |
|---|---|---|---|
| A-2 | 도메인 전환 정책 | 새 도메인에서 기기별 1회 재로그인 | 유지. 단 **Firebase Hosting 경유를 전제**로 쿠키 구조를 변경해야 성립 |
| A-8 | 세션 전달 구조 (신설) | — | 백엔드로 전달 가능한 유일한 쿠키 `__session` **하나로 통합**. `device_id`는 세션 내부 필드로 이동 |
| A-9 | 수명 계층 (신설) | 쿠키 2개로 분리(12시간 / 90일) | **쿠키 1개 + 논리적 2계층**. 쿠키 수명 90일, 인증 신선도는 `auth_at`으로 12시간 강제 |
| A-10 | Hosting 구성 (신설) | — | `firebase.json` 등 Hosting 구성을 앱 저장소에서 버전 관리 |
| A-11 | 서버 측 세션 (초판 P1-2) | 프로덕션 공개 전 보안 게이트 | 유지. 본 개정의 `__session` 통합은 그 전 단계이며 **후속으로 별도 승인** |

### 1.3 채택하지 않은 대안

- **Cloud Run 도메인 매핑으로 전환**: 쿠키 제약이 사라지지만 Firebase Hosting으로
  두 서비스(msw·mfw)의 도메인·SSL을 일괄 관리하는 현재 운영 방식을 바꿔야 한다.
  운영 편의를 우선해 채택하지 않는다.
- **서버 측 세션 즉시 도입**: 가장 깨끗하지만 구현량이 크고, 지금은 장애 복구가 우선이다.
  단계적으로 진행한다(11장).

---

## 2. 목표 구조 (P0-5)

### 2.1 단일 `__session` 쿠키

```text
쿠키 이름   __session          (Firebase Hosting이 전달하는 유일한 이름)
속성        Path=/ · HttpOnly · Secure · SameSite=Lax
수명        90일 (마지막 요청 기준 슬라이딩 갱신)
서명        Flask 기본 서명 (암호화 아님 — 담는 값의 민감도를 아래 기준으로 제한)
```

세션에 담는 값

| 필드 | 계층 | 설명 |
|---|---|---|
| `device_id` | 장기(90일) | 기기 식별자. 기존 `device_id` 쿠키를 대체 |
| `user_key` / `user_key_version` | 장기 | HMAC 사용자 키 (초판 P0-2) |
| `auth_at` | — | 마지막 인증 시각(UTC ISO). 단기 계층 만료 판정 기준 |
| `credentials` | 단기(12시간) | access token + 만료 시각. **refresh token·client_secret은 절대 담지 않는다** |
| `user` | 단기 | 표시용 이름·프로필. 저장소에는 남기지 않는다(초판 5.3) |
| `sheet_id` / `sheet_title` / `worksheet_name` | 장기 | 사용자 문서 값의 캐시 |
| `_csrf_token` | 장기 | 기존과 동일 |
| `oauth_state` / `code_verifier` | 임시 | 로그인 진행 중에만 존재, 콜백에서 소비 |

### 2.2 논리적 2계층 수명

쿠키를 두 개 쓸 수 없으므로 **수명 분리를 코드로 강제**한다. 사용자 체감은 초판과 같다.

1. 요청 처리 초입에서 `auth_at`을 확인한다.
2. `now - auth_at > AUTH_FRESHNESS_HOURS`(기본 12)이면 세션에서 `credentials`와 `user`를
   제거한다. `device_id`·`user_key`·시트 정보는 남긴다.
3. 그 결과 기존 `auto_restore_session` 경로가 동작해, `device_id` → `device_sessions` →
   Firestore `refresh_token`으로 access token을 재발급하고 `auth_at`을 갱신한다.
4. 재발급이 실패하면(테스트 모드 7일 만료 등) 로그인 화면으로 유도한다.

즉 **12시간마다 access token 계층이 강제로 폐기되고 서버 저장 토큰으로만 재구성**된다.
쿠키를 탈취해도 그 안의 access token은 최대 1시간이면 만료된다.

### 2.3 device_id 수명과 재발급

- 콜백에서 세션에 `device_id`가 없으면 `secrets.token_urlsafe(32)`로 발급한다.
- 세션 쿠키가 유실되면 기기 식별도 함께 사라진다. 이때는 새 `device_id`가 발급되고,
  이전 `device_sessions` 문서는 90일 TTL로 정리된다. 고아 문서가 일시적으로 늘어나는 것을
  허용한다(기존 구조에서도 쿠키 삭제 시 동일했다).
- 같은 브라우저에서 계정을 바꾸면 `device_id`는 유지하되 문서의 `user_key`를 교체한다
  (초판 P0-3 로직 그대로).

### 2.4 로그아웃

| 동작 | 처리 |
|---|---|
| 이 기기 로그아웃 | `device_sessions/{device_id}` 삭제 + 세션 비우기 + `__session` 쿠키 삭제 |
| 전체 로그아웃 | `user_key`의 모든 기기 문서 삭제 + 세션 비우기 + 쿠키 삭제 |

다른 기기의 `__session` 쿠키는 즉시 무효화되지 않지만, 그 안의 access token은 최대
1시간 뒤 만료되고 재발급은 삭제된 Firestore 문서 때문에 실패한다. 즉 **최대 1시간의
지연을 두고 무효화**된다. 즉시 무효화는 서버 측 세션(11장)에서 해결한다. 이 지연을
조치안에 명시적으로 남긴다.

### 2.5 CDN 캐시 안전

Firebase Hosting은 응답을 CDN에 캐시할 수 있다. 인증된 응답이 캐시되어 다른 사용자에게
노출되는 사고를 막기 위해, 정적 파일을 제외한 모든 응답에 다음을 강제한다.

```text
Cache-Control: private, no-store
```

`vary: Cookie`가 붙어 있더라도 백엔드에 `__session`만 전달되는 구조에서는 캐시 키를
신뢰하지 않는다.

### 2.6 canonical host 확인

Firebase Hosting이 Cloud Run에 전달하는 `Host` 값이 `mfw.worldapex.studio`가 아니면
현재의 canonical 308 리디렉션이 루프를 만들 수 있다. 관측된 로그에 308이 없으므로
정상으로 보이나, 구현 시 **콜백 진단 로그로 1회 확정 확인**한다. 필요하면
`x-forwarded-host` 처리를 보정한다. Cloud Run 기본 URL 직접 접근은 Firebase를 우회하므로
쿠키가 정상 동작하지만, 도메인 이원화를 막기 위해 canonical 리디렉션은 유지한다.

---

## 3. 보안 평가

| 항목 | 초판(쿠키 2개) | 개정(쿠키 1개) | 판정 |
|---|---|---|---|
| refresh token 노출 | 쿠키에 없음 | 쿠키에 없음 | 동일 |
| access token 노출 창 | 세션 쿠키 12시간 | 쿠키는 90일이나 `auth_at`으로 12시간마다 폐기, 토큰 자체 1시간 만료 | 실질 동일 |
| 기기 식별자 탈취 시 영향 | `device_id` 쿠키(90일) 탈취로 자동 복원 가능 | 동일 (같은 값이 세션 안으로 이동) | 동일 |
| 탈취 쿠키 1개로 얻는 것 | 두 쿠키를 모두 훔쳐야 함 | 한 쿠키로 충분 | **소폭 악화** |
| 전체 로그아웃 반영 | 즉시(Firestore 삭제 + 짧은 쿠키) | 최대 1시간 지연 | **소폭 악화** |

완화책

- `HttpOnly` + `Secure` + `SameSite=Lax` 유지 (JS 접근 차단)
- 단기 계층 폐기를 요청마다 검사
- 로그아웃 시 쿠키 삭제 + 서버 문서 삭제 동시 수행
- 근본 해소는 서버 측 세션(11장). 프로덕션 공개 전 보안 게이트로 유지한다

---

## 4. 구현 작업 목록

### P0-5-1. 쿠키 통합

대상: `app.py`, `routes/auth.py`

- `SESSION_COOKIE_NAME = "__session"`
- `PERMANENT_SESSION_LIFETIME = 90일`, `SESSION_REFRESH_EACH_REQUEST = True`
- `set_device_cookie()` · `renew_device_cookie()` 제거
- `request.cookies.get("device_id")` 사용처를 `session.get("device_id")`로 전면 교체
  (`routes/auth.py`의 `get_credentials`·`logout`, `app.py`의 `auto_restore_session`)
- 로그아웃 시 레거시 `device_id` 쿠키 삭제는 한시적으로 유지(과거 쿠키 정리용)

### P0-5-2. 논리적 2계층

대상: `app.py`

- `AUTH_FRESHNESS_HOURS`(기본 12, 환경 변수 `SESSION_LIFETIME_HOURS` 재사용)
- `before_request` 초입에서 `auth_at` 검사 → 만료 시 `credentials`·`user` 제거
- 콜백 성공과 자동 복원 성공 시 `auth_at` 갱신

### P0-5-3. 캐시 안전 헤더

대상: `app.py`

- `after_request`에서 `/static/` 외 모든 응답에 `Cache-Control: private, no-store`

### P0-5-4. 진단 보강

대상: `routes/auth.py`

- 콜백에서 수신 쿠키 **이름 목록만**(값 제외) 기록
- `__session`이 아예 없으면 `AUTH_COOKIE_BLOCKED` 코드로 분기 — 이 코드가 나오면
  애플리케이션이 아니라 Hosting 구성 문제로 즉시 판정할 수 있다
- 기존 `AUTH_STATE_MISSING`은 "쿠키는 왔는데 state만 없는 경우"로 의미를 좁힌다

### P0-6. Hosting 구성 버전 관리

대상: 신규 `hosting/`

현재 운영 중인 구성(`~/worldapex-hosting/my-favorite-watch/firebase.json`)을 그대로 사본화한다.

- `hosting/firebase.json`

  ```json
  {
    "hosting": {
      "public": "./firebase-public",
      "ignore": [
        "firebase.json",
        "**/.*",
        "**/node_modules/**"
      ],
      "rewrites": [
        {
          "source": "**",
          "run": {
            "serviceId": "my-favorite-watch",
            "region": "asia-northeast3"
          }
        }
      ]
    }
  }
  ```

- `hosting/.firebaserc.example` — `{"projects": {"default": "my-favorite-watch"}}`
- DNS(Porkbun): `mfw` → CNAME `my-favorite-watch.web.app`

#### 이 구성에서 파생되는 제약

이 항목들은 앞으로 기능을 추가할 때 반복해서 걸리므로 문서에 고정한다.

| 제약 | 근거 | 영향 |
|---|---|---|
| 백엔드로 전달되는 쿠키는 `__session` 뿐 | Firebase Hosting 정책 | 본 개정의 전체 배경. **쿠키를 새로 추가할 수 없다** |
| `source: "**"` — 정적 파일도 Cloud Run이 서빙 | 위 rewrite | `/static/**`가 CDN 이점을 받지 못한다. 로그에도 `/static/css/style.css`가 Cloud Run에 기록된다 |
| `public: "./firebase-public"`에 `index.html`이 있으면 `/`가 그 파일로 응답 | rewrite는 정적 파일이 없을 때만 적용 | 디렉터리를 **비워 두어야** 한다. 배포 전 확인 항목 |
| Cloud Run 서비스가 공개(`--allow-unauthenticated`)여야 한다 | Hosting의 Cloud Run rewrite 요구사항 | Cloud Run 기본 URL로 Firebase를 우회하는 경로가 항상 존재한다. canonical 308로 커버 |
| Hosting은 백엔드 응답을 60초까지 기다린다 | Firebase Hosting 제한 | TMDb 청크 보강이 이를 넘지 않아야 한다. `TMDB_ENRICH_CHUNK` 기본 15를 유지하는 근거 |
| `serviceId`·`region`이 rewrite에 하드코딩됨 | 위 rewrite | 서비스 이름이나 리전을 바꾸면 **Hosting을 다시 배포**해야 한다. 리비전 변경만으로는 불필요 |
- `SETUP.md`에 배포 절차와 주의사항 기록
  - `firebase deploy --only hosting --project my-favorite-watch` (alias 대신 Project ID 명시)
  - **`mfw`를 Firebase project alias로 쓰지 않는다** — 삭제된 프로젝트의 alias가 남아
    `projects/mfw` 403이 발생한 사례가 있다. `mfw`는 도메인 prefix로만 사용한다
  - Cloud Run 재배포와 Hosting 재배포는 독립이며, 서비스 이름이 유지되면 Hosting은
    다시 배포할 필요가 없다
  - **`__session` 제약을 SETUP.md 본문에 명시** — 향후 쿠키 추가 시 재발 방지

### P0-7. 문서 갱신

- `PRD.md` 4.2 세션 관리: 쿠키 2계층 → 단일 `__session` + 논리적 2계층
- `PRD.md` 4.2 인증 실패 코드 표에 `AUTH_COOKIE_BLOCKED` 추가
- `SETUP.md` 배포 후 점검 항목에 Hosting 경유 확인 추가
- `version.py` → `v1.5.0` (세션 전달 구조 변경)

---

## 5. 테스트 계획과 완료 기준

### 5.1 회귀 테스트 (신규)

- [ ] `SESSION_COOKIE_NAME`이 `__session`이다
- [ ] 응답에 `device_id` 쿠키가 더 이상 발급되지 않는다
- [ ] 콜백 성공 시 세션에 `device_id`·`user_key`·`auth_at`이 채워진다
- [ ] `auth_at`이 12시간을 넘으면 `credentials`·`user`가 제거되고 `device_id`는 남는다
- [ ] 제거 후 자동 복원 경로가 Firestore `refresh_token`으로 세션을 재구성한다
- [ ] 두 클라이언트가 서로 다른 `device_id`, 같은 `user_key`를 가진다
- [ ] 한 기기 로그아웃이 다른 기기 문서를 지우지 않는다
- [ ] 정적 파일 외 응답에 `Cache-Control: private, no-store`가 붙는다
- [ ] 콜백에 쿠키가 하나도 없으면 `AUTH_COOKIE_BLOCKED`로 분기한다
- [ ] 쿠키 이름 목록 외에 쿠키 **값**은 로그에 남지 않는다

### 5.2 Hosting 구성 확인 (배포 전)

- [ ] `~/worldapex-hosting/my-favorite-watch/firebase-public/`이 비어 있다(`index.html` 없음)
- [ ] `.firebaserc`의 default가 `my-favorite-watch`(alias `mfw` 아님)이다
- [ ] Cloud Run 로그의 `requestUrl` 호스트가 `mfw.worldapex.studio`다 (2.6 확인)

### 5.3 배포 후 실환경 확인

- [ ] `https://mfw.worldapex.studio`에서 로그인이 완료되고 `/` 또는 `/connect`로 이동한다
- [ ] DevTools에서 `__session` 쿠키가 설정되고 콜백 요청에 실려 간다
- [ ] 브라우저를 닫았다 열어도 로그인이 유지된다(장기 계층 동작 확인)
- [ ] 기기 2대에서 같은 계정 로그인 → 같은 시트, 다른 `device_id`
- [ ] 한 기기 로그아웃 후 다른 기기 유지, 전체 로그아웃 후 최대 1시간 내 무효화
- [ ] 같은 브라우저에서 계정 전환 시 이전 계정 시트 미노출
- [ ] Firestore `users`·`device_sessions`에 이메일·이름·프로필 URL 없음

---

## 6. 배포·마이그레이션 순서

1. 회귀 테스트를 먼저 추가한다.
2. P0-5(쿠키 통합·2계층·캐시 헤더·진단)를 구현하고 로컬에서 검증한다.
3. Cloud Run에 배포한다. Hosting 재배포는 필요 없다(서비스 이름 불변).
4. 실환경에서 5.2 항목을 확인한다.
5. Hosting 구성 사본과 문서를 커밋한다(P0-6·P0-7).
6. 안정화 후 서버 측 세션(11장) 도입 여부를 별도 승인한다.

**사용자 영향**: 기존 `session`/`device_id` 쿠키는 어차피 백엔드에 도달하지 못했으므로
잃을 세션이 없다. 전원 1회 로그인이 필요하며, 이번 배포 이후부터 자동 로그인 유지가
처음으로 실제 동작하게 된다.

---

## 7. 롤백 원칙

- 쿠키 이름 변경은 되돌려도 이득이 없다. 이전 상태는 **로그인이 불가능한 상태**이므로
  롤백 대상이 아니다.
- 장애 시 되돌릴 축은 Cloud Run 리비전이 아니라 Hosting 경로다. 긴급 시에는
  Cloud Run 기본 URL(`https://my-favorite-watch-….run.app`)로 `PUBLIC_BASE_URL`을 바꿔
  재배포하면 Firebase를 우회해 즉시 로그인 가능한 상태를 만들 수 있다. 이때 OAuth
  클라이언트에 해당 리디렉션 URI가 등록되어 있어야 한다.
- 초판과 동일하게, 이미 제거한 원문 개인정보는 어떤 경우에도 복원하지 않는다.

---

## 8. 후속 — 서버 측 세션 (초판 P1-2)

본 개정의 통합 쿠키는 다음 단계로 자연스럽게 이어진다.

- `__session`에는 **예측 불가능한 세션 ID만** 남긴다
- access token·표시 정보·시트 캐시는 Firestore 서버 세션 문서로 옮긴다
- `device_sessions`는 그대로 유지하고 서버 세션과 `device_id`로 연결한다
- 효과: 쿠키에서 토큰이 사라지고, 전체 로그아웃이 **지연 없이** 반영되며, 세션 ID 회전과
  탈취 대응이 가능해진다
- 비용: 요청마다 Firestore 읽기 1회

프로덕션 공개 전 보안 게이트로 유지하며, 별도 승인 후 진행한다.

---

## 부록 A. 관측 근거 (마스킹)

```text
2026-08-18T15:21:01Z  my-favorite-watch-00006-rxn  302  GET /auth/callback
2026-08-18T15:21:01Z  WARNING:routes.auth:OAuth callback rejected: oauth_state missing in session
(동일 패턴 15:17:24 · 15:17:39 · 15:18:03 반복, 단일 리비전)

$ curl -sI https://mfw.worldapex.studio/auth/google
HTTP/2 302
server: Google Frontend
set-cookie: session=…; Path=/; HttpOnly; Secure; SameSite=Lax
x-served-by: cache-icn…      x-cache: MISS
vary: Cookie, need-authorization, x-fh-requested-host

$ gcloud beta run domain-mappings list --region=asia-northeast3
Listed 0 items.

$ dig +short mfw.worldapex.studio
my-favorite-watch.web.app.
199.36.158.100
```

OAuth code·state 값과 자격증명은 본 문서에 기록하지 않는다(초판 2.3 주의사항).

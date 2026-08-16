# My Favorite Watch — 설정 가이드

로컬 개발 환경 구성부터 Cloud Run 배포, 배포 후 1회성 설정까지 다룬다.
기능 정의는 `PRD.md`, 작업 규칙은 `CLAUDE.md`를 따른다.

- 대상 버전: v1.3.3
- 런타임: Python 3.12 / Flask (SSR)
- 배포: Cloud Run (`asia-northeast3`)

---

## 1. 패키지 설치

```bash
pip install -r requirements.txt          # 실행
pip install -r requirements-dev.txt      # 실행 + 테스트(pytest)
```

---

## 2. Google Cloud 프로젝트 준비

1. [Google Cloud Console](https://console.cloud.google.com)에서 프로젝트 생성 (예: `my-favorite-watch`)
2. **API 및 서비스 → 라이브러리**에서 다음을 사용 설정
   - `Google Sheets API`
   - `Google Drive API` (시트 검색용 · `drive.metadata.readonly`)
   - `Cloud Firestore API`

---

## 3. OAuth 동의 화면 · 클라이언트 ID

### 3.1 동의 화면

1. **API 및 서비스 → OAuth 동의 화면** → User Type **외부**
2. 앱 이름 · 지원 이메일 입력
3. 범위 추가

   | 스코프 | 용도 |
   |----|----|
   | `openid`, `userinfo.email`, `userinfo.profile` | 로그인 · 사용자 식별 |
   | `spreadsheets` | 시트 읽기/쓰기 |
   | `drive.metadata.readonly` | 기본 이름의 시트 검색 (최소 권한) |

> ⚠️ **테스트 모드에서는 Google이 refresh token을 7일 후 만료시킨다.**
> 이 경우 `device_id` 기반 90일 자동 로그인 유지(PRD §4.2)가 일반 사용자에게
> 동작하지 않는다. 일반 공개 전에 **프로덕션 게시 + 앱 검증**이 필요하다.
> `spreadsheets` / `drive.metadata.readonly`는 민감 스코프이므로 검증 대상이며,
> 통상 2~6주가 소요된다.

### 3.2 클라이언트 ID

1. **API 및 서비스 → 사용자 인증 정보 → OAuth 클라이언트 ID 만들기**
2. 애플리케이션 유형: **웹 애플리케이션**
3. **승인된 리디렉션 URI** 등록
   - 로컬: `http://localhost:8090/auth/callback`
   - 배포: `https://<service>-<project-number>.asia-northeast3.run.app/auth/callback`
4. **클라이언트 ID**와 **클라이언트 보안 비밀** 복사

---

## 4. TMDb API 키 (선택)

[TMDb 설정 → API](https://www.themoviedb.org/settings/api)에서 API Key(v3 auth)를 발급한다.

미설정 시 앱은 정상 동작하며 **TMDb 자동 보강(링크 · 공식 평점 · 원제)만 생략**된다.

---

## 5. 환경 변수

`.env.example`을 복사해 `.env`를 만든다. `.env`는 `.gitignore`에 포함되어 커밋되지 않는다.

```bash
cp .env.example .env
```

| 변수 | 필수 | 기본값 | 설명 |
|----|----|----|----|
| `GOOGLE_CLIENT_ID` | ✅ | — | OAuth 클라이언트 ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | — | OAuth 클라이언트 보안 비밀 |
| `FLASK_SECRET_KEY` | ✅ | — | 세션 서명 키. **운영 환경에서 미설정 시 앱이 시작되지 않는다** |
| `REDIRECT_URI` | ✅ | `http://localhost:8090/auth/callback` | OAuth 콜백. 3.2에 등록한 값과 정확히 일치해야 한다 |
| `APP_ENV` | | `production` | `development` 지정 시 HTTP 허용 · 디버그 로그 · 쿠키 Secure 해제 |
| `TMDB_API_KEY` | | (빈 값) | 없으면 TMDb 보강 생략 |
| `SESSION_LIFETIME_HOURS` | | `12` | Flask 세션 쿠키 수명. 장기 로그인은 `device_id`(90일)가 담당하므로 짧게 유지한다 |
| `TMDB_ENRICH_CHUNK` | | `15` | 한 요청에서 동기 보강할 항목 수. 늘리면 요청 시간이 길어져 타임아웃 위험이 커진다 |

`FLASK_SECRET_KEY` 생성:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 6. Firestore 설정

장기 로그인 유지(`refresh_token`)와 TMDb 보강 진행 상태를 저장한다.

### 6.1 데이터베이스 생성

[Firestore 콘솔](https://console.cloud.google.com/firestore) → **네이티브 모드**

| 항목 | 값 |
|----|----|
| 리전 | `asia-northeast3` |
| **데이터베이스 ID** | **`refresh-token`** |

> ⚠️ 앱이 `Client(database="refresh-token")`으로 접속하므로
> **기본 데이터베이스(`(default)`)가 아니라 이 이름으로 생성해야 한다.**

### 6.2 컬렉션

| 컬렉션 | 문서 ID | 내용 |
|----|----|----|
| `sessions` | `device_id` | `refresh_token`, 사용자 정보, 마지막 연결 시트 |
| `tmdb_jobs` | `item_id` | TMDb 보강 진행 상태(`status`), `expires_at` |

두 컬렉션 모두 앱이 자동 생성하므로 미리 만들 필요는 없다.

### 6.3 권한

Cloud Run 서비스 계정에 Firestore 접근 권한을 부여한다.

```bash
PROJECT_ID=my-favorite-watch
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/datastore.user"
```

### 6.4 로컬 개발 시 ADC

```bash
gcloud auth application-default login
```

> Firestore 미설정 상태에서도 앱은 동작한다. 다만 다음 기능이 비활성화된다.
> - 자동 로그인 유지 (세션 만료 시 재로그인 필요)
> - 액세스 토큰 자동 갱신 (`refresh_token`을 세션에 두지 않으므로)
> - TMDb 보강 진행 상태 공유 (프로세스 메모리로 폴백)

---

## 7. 로컬 실행

```bash
python3 app.py
```

→ <http://localhost:8090>

`APP_ENV=development`일 때만 HTTP 콜백이 허용된다(`OAUTHLIB_INSECURE_TRANSPORT`).
운영 환경에서는 절대 켜지 않는다.

---

## 8. 테스트

```bash
python3 -m pytest tests/ -v
```

| 파일 | 대상 |
|----|----|
| `test_google_credentials.py` | 세션 쿠키에 비밀 값이 없는지 (P0-1) |
| `test_tmdb_tracker.py` | 보강 상태가 프로세스 경계를 넘어 공유되는지 (P0-3) |
| `test_tmdb_enrich_chunk.py` | 청크 동기 보강 · 부분 실패 격리 (P0-3) |
| `test_session_lifetime.py` | 세션 수명 2계층 구조 (P0-5) |
| `test_error_sanitization.py` | 예외 원문 비노출 (P0-6) |

---

## 9. Cloud Run 배포

```bash
bash scripts/deploy.sh
```

사전 조건

1. `gcloud auth login` 완료
2. `.env`에 필수 값이 모두 채워져 있을 것
3. 3.2의 승인된 리디렉션 URI에 Cloud Run URL이 등록되어 있을 것

대상 변경은 환경 변수로 조정한다.

```bash
GOOGLE_CLOUD_PROJECT=<project> CLOUD_RUN_REGION=<region> bash scripts/deploy.sh
```

### gunicorn 구성

```
--workers 2 --threads 8 --timeout 120
```

- 보강 진행 상태를 Firestore에 두므로 **워커를 1개로 줄일 필요가 없다.**
  `--no-cpu-throttling` / `--max-instances 1` 같은 회피 설정도 불필요하다.
- `--timeout 120`은 청크 동기 보강(기본 15건)의 외부 API 지연을 감안한 값이다.
  `TMDB_ENRICH_CHUNK`를 늘린다면 이 값도 함께 검토한다.

---

## 10. 배포 후 1회성 설정

**배포 직후 한 번만** 수행한다. 재구축·프로젝트 이전 시에도 다시 필요하다.

### 10.1 `tmdb_jobs` TTL 정책 (필수)

TMDb 보강 진행 상태 문서는 완료 후 쓸모가 없다. 정리하지 않으면 계속 쌓인다.
앱은 문서에 `expires_at`(생성 + 24시간)을 기록하므로, TTL 정책만 걸어주면 자동 삭제된다.

```bash
gcloud firestore fields ttls update expires_at \
  --collection-group=tmdb_jobs \
  --database=refresh-token \
  --project=my-favorite-watch \
  --enable-ttl
```

> ⚠️ `--database=refresh-token`을 **반드시** 지정한다.
> 생략하면 `(default)` 데이터베이스에 적용되어 아무 효과가 없다.

콘솔로 설정하는 경우:

1. [Firestore Databases](https://console.cloud.google.com/firestore/databases) → **`refresh-token`** 선택
2. 왼쪽 메뉴 **Time-to-live** → **정책 만들기**
3. 컬렉션 그룹 `tmdb_jobs`, 타임스탬프 필드 `expires_at`
4. **만료 오프셋은 0으로 둔다.** 앱이 이미 `now + 24h`를 계산해 저장하므로 오프셋을 주면 이중 적용된다
5. 만들기

확인:

```bash
gcloud firestore fields ttls list --database=refresh-token
```

동작 특성

- 활성화까지 **최소 10분 이상** 걸린다
- 삭제는 즉시가 아니라 **만료 후 통상 24시간 이내**다
- 정책 적용 시점에 이미 만료된 기존 문서도 일괄 정리된다
- TTL 삭제도 document delete 과금에 포함된다 (항목당 1건이라 규모상 무시 가능)

### 10.2 `expires_at` 단일 필드 색인 면제 (권장)

Firestore는 기본적으로 모든 필드에 단일 필드 색인을 만드는데,
**타임스탬프 필드 색인은 핫스팟을 유발**한다(Google 권고사항).
`expires_at`은 쿼리에 사용하지 않으므로 면제하는 편이 좋다.

```bash
gcloud firestore indexes fields update expires_at \
  --collection-group=tmdb_jobs \
  --database=refresh-token \
  --project=my-favorite-watch \
  --disable-indexes
```

### 10.3 `sessions` 컬렉션 수명 정책 (권장)

`device_id` 쿠키는 90일이지만 Firestore `sessions` 문서는 영구 잔존한다
(`refresh_token` 포함). `updated_at` 기준 TTL을 걸어 미사용 세션을 정리한다.

```bash
gcloud firestore fields ttls update updated_at \
  --collection-group=sessions \
  --database=refresh-token \
  --project=my-favorite-watch \
  --enable-ttl \
  --expiration-offset=90d
```

> `updated_at`은 마지막 사용 시각이므로 **오프셋 90d를 지정**한다.
> `expires_at`(10.1)과 달리 앱이 만료 시각을 미리 계산해 두지 않는다.

### 10.4 참고 문서

- [Manage data retention with TTL policies — Firestore](https://cloud.google.com/firestore/native/docs/ttl)
- [gcloud firestore fields ttls update](https://cloud.google.com/sdk/gcloud/reference/firestore/fields/ttls/update)

---

## 11. 배포 후 점검

- [ ] 미등록 계정으로 로그인 → 시트 연결 플로우 정상 동작
- [ ] 로그아웃 → 재로그인 시 시트 연결 정보가 유지되는지
- [ ] 100건 이상 CSV 가져오기 → 전 항목이 완료 상태로 수렴하는지
- [ ] 보강 진행 중 새로고침 → 진행률이 유지되고 자동 재개되는지
- [ ] `gcloud firestore fields ttls list --database=refresh-token` → 정책 `ACTIVE`
- [ ] 세션 쿠키를 디코드했을 때 `client_secret` · `refresh_token`이 없는지

---

## 12. 자주 겪는 문제

| 증상 | 원인 · 조치 |
|----|----|
| `FLASK_SECRET_KEY 환경 변수가 설정되지 않았습니다` | 운영 환경에서 필수. `.env` 확인 |
| `redirect_uri_mismatch` | `REDIRECT_URI`와 OAuth 클라이언트에 등록한 URI 불일치. 프로토콜·포트·경로까지 정확히 일치해야 한다 |
| 로그인이 7일마다 풀림 | OAuth 동의 화면이 테스트 모드. 3.1 참조 |
| 매 로그인마다 동의 화면 반복 | `routes/auth.py`의 `prompt="consent"` 고정 (개선 예정) |
| 보강 진행률이 멈춤 | `TMDB_API_KEY` 미설정이거나 Firestore 권한 부족. 서버 로그 확인 |
| `tmdb_jobs` 문서가 계속 쌓임 | 10.1 TTL 정책 미설정 |
| 로컬에서 1시간 후 API 호출 실패 | Firestore 미구성으로 토큰 갱신 불가. 6.4의 ADC 설정 |

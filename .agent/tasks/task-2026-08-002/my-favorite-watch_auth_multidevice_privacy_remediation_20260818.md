# My Favorite Watch 인증·멀티 디바이스·개인정보 최소화 조치안

- 작성일: 2026-08-18
- 대상 저장소: [veggar/my-favorite-watch](https://github.com/veggar/my-favorite-watch)
- 검토 기준: `master` 브랜치 (`9a4b6666b259ff5484a0c8ab286ed059d0a9c724`)
- 대상 독자: 승인자, 개발 작업자, 운영 담당자
- 문서 성격: 기술·개인정보 보호 관점의 조치안이며, 최종 법률 판단은 개인정보 보호 담당자 또는 법률 전문가의 검토가 필요하다.

## 1. 결론 및 승인 요청

### 1.1 결론

1. **동일 Google 계정의 멀티 디바이스 접속은 현재도 구조적으로 지원한다.**
   - 기기·브라우저별 `device_id`와 refresh token을 별도 보관한다.
   - 새 기기에서는 같은 이메일의 기존 세션을 찾아 Google Sheet 연결을 복원한다.
   - 한 기기의 로그아웃은 해당 `device_id` 세션만 삭제하므로 다른 기기 세션은 유지된다.
2. **도메인 변경 후 기존 세션이 자동 유지되지 않는 것은 정상적인 쿠키 보안 동작이다.**
   - 기존 Cloud Run/Firebase 도메인의 쿠키는 새 커스텀 도메인 `mfw.worldapex.studio`로 이전되지 않는다.
   - 도메인 변경 후 각 기기에서 한 번의 재로그인이 필요하다.
3. **현재 구현은 이메일을 사용자 식별키로 사용하며 Firestore에 원문으로 중복 저장한다.**
   - `email` 필드뿐 아니라 `user.email`, 이름, 프로필 이미지 URL도 저장한다.
   - 이메일만 해시하고 `user` 객체를 그대로 남기면 개인정보 최소화 효과가 없다.
4. **단순 SHA-256 이메일 해시는 채택하지 않는다.**
   - 이메일은 후보 공간이 좁아 사전 대입으로 추정하기 쉽다.
   - Google OIDC의 안정적인 계정 식별자 `sub`를 검증한 후, 별도 서버 비밀키를 사용한 `HMAC-SHA-256(sub)`을 내부 사용자 키로 사용한다.
5. **해시 또는 HMAC 처리는 법적 의무를 제거하지 않는다.**
   - 재식별·연결 가능성이 있는 식별자는 개인정보 또는 가명정보로 취급하는 보수적 운영이 필요하다.
   - 목적·보유기간·파기·접근통제·정보주체 권리 대응은 계속 적용한다.

### 1.2 승인 요청 사항

| 번호 | 승인 항목 | 권고안 |
|---|---|---|
| A-1 | 멀티 디바이스 정책 | 동일 계정·여러 기기 동시 접속 허용, 기기별 독립 세션 유지 |
| A-2 | 도메인 전환 정책 | 기존 세션 이전 없이 새 도메인에서 기기별 1회 재로그인 |
| A-3 | 사용자 식별자 | 이메일 폐기, 검증된 Google `sub`의 HMAC 값 사용 |
| A-4 | 저장 구조 | 사용자 공통 설정과 기기별 인증 세션을 별도 컬렉션으로 분리 |
| A-5 | 개인정보 범위 | Firestore에서 이메일·이름·프로필 이미지 원문 제거 |
| A-6 | 테스트 앱 제약 | 테스트 기간에는 등록된 테스트 사용자만 허용하고 7일 토큰 만료를 수용 |
| A-7 | 운영 전 보안 게이트 | OAuth 프로덕션 게시·검증, 개인정보처리방침, 계정 삭제/전체 로그아웃 제공 |

## 2. 현재 장애 판단

### 2.1 확인된 요청 흐름

로그에는 다음 흐름이 반복된다.

```text
GET /auth/google   → 302
GET /auth/callback?code=...&state=... → 302
```

- Google이 authorization code를 콜백으로 반환하므로 계정 선택·동의·리디렉션은 완료된다.
- 같은 리비전 `my-favorite-watch-00005-rrn`에서 처리되어 리비전 간 `FLASK_SECRET_KEY` 차이 가능성은 낮다.
- 애플리케이션 예외가 없으므로 Client ID·Client Secret 불일치 가능성도 낮다.
- 콜백의 302는 성공 리디렉션과 `state` 불일치 리디렉션 모두에서 발생하므로, 다음 요청이 `/login`, `/connect`, `/` 중 어디인지 기록해야 최종 분류할 수 있다.

### 2.2 도메인 변경에 따른 예상 동작

기존 도메인에서 발급한 Flask `session` 및 `device_id` 쿠키는 새 도메인에 전송되지 않는다. 따라서 도메인 변경 후 다음 동작을 정상 기준으로 정의한다.

1. 새 도메인에서 Google OAuth 재로그인
2. 새 도메인용 `device_id` 발급
3. 안정적인 사용자 키로 기존 사용자 공통 설정 조회
4. 기존 Google Sheet 연결 복원
5. 해당 기기용 refresh token 저장

기존 도메인의 쿠키를 새 도메인으로 복사하거나 `SESSION_COOKIE_DOMAIN`으로 공유하는 방식은 채택하지 않는다. 서로 다른 등록 가능 도메인 간 쿠키 공유는 불가능하고 보안 경계도 약화시킨다.

### 2.3 즉시 확인할 요청 순서

한 번의 로그인 시도 직후 전체 요청을 확인한다.

```bash
gcloud logging read '
resource.type="cloud_run_revision"
AND resource.labels.service_name="my-favorite-watch"
AND timestamp>="<로그인 시작 UTC>"
AND timestamp<="<로그인 종료 UTC>"
' \
  --project=my-favorite-watch \
  --limit=100 \
  --order=asc \
  --format='table(timestamp,httpRequest.status,httpRequest.requestUrl)'
```

| 콜백 다음 요청 | 판정 |
|---|---|
| `/login` | `oauth_state` 또는 세션 쿠키 불일치 |
| `/connect` | 인증 성공, 연결할 시트 정보 없음 |
| `/` | 인증 및 시트 연결 복원 성공 |
| `/` 이후 Sheets API 403 | 다른 계정의 기존 시트가 잘못 복원됨 |

> Cloud Logging의 callback URL에는 일회용 authorization code와 `state`가 포함될 수 있다. 공유·티켓·문서화 시 반드시 해당 값을 마스킹하고 로그 접근권한과 보유기간을 최소화한다.

## 3. 동일 계정 멀티 디바이스 지원 판정

### 3.1 현재 상태

**지원: 조건부 지원**

현재 [`services/firestore_session.py`](https://github.com/veggar/my-favorite-watch/blob/9a4b6666b259ff5484a0c8ab286ed059d0a9c724/services/firestore_session.py#L19-L40)는 `sessions/{device_id}`에 사용자와 refresh token을 저장한다. [`lookup_saved_sheet()`](https://github.com/veggar/my-favorite-watch/blob/9a4b6666b259ff5484a0c8ab286ed059d0a9c724/services/firestore_session.py#L80-L110)은 현재 기기 문서가 없을 때 이메일이 같은 다른 기기의 시트 정보를 찾는다.

따라서 같은 계정으로 기기 A와 B에서 로그인하면 다음과 같이 동작한다.

| 항목 | 동작 |
|---|---|
| 기기 식별 | 기기·브라우저별 별도 `device_id` |
| 인증 유지 | 기기별 refresh token |
| 데이터 | 동일 Google Sheet 공유 |
| 기기 A 로그아웃 | A의 세션만 삭제, B 유지 |
| 새 브라우저·시크릿 모드 | 새 기기로 간주 |
| 동일 브라우저의 계정 변경 | 현재 구현에서 기존 계정 시트 혼입 위험 존재 |

### 3.2 테스트 상태 앱의 제한

현재 앱은 Sheets 및 Drive 범위를 요청한다. Google OAuth 앱이 `Testing` 상태이면 테스트 사용자의 승인은 동의 시점부터 7일 후 만료되고 offline refresh token도 함께 만료될 수 있다. 따라서 코드의 90일 `device_id` 정책과 무관하게 **테스트 상태에서 장기 자동 로그인은 최대 7일 수준으로 제한**된다.

테스트 단계의 멀티 디바이스 완료 기준은 다음으로 한정한다.

- 등록된 동일 테스트 계정으로 2대 이상의 기기에서 각각 로그인 가능
- 각 기기에서 동일 시트가 표시됨
- 한 기기 로그아웃 후 다른 기기는 계속 사용 가능
- 7일 장기 유지 여부는 프로덕션 게시·검증 후 재검증

## 4. 개인정보 저장 현황과 위험

### 4.1 현재 Firestore 저장 항목

현재 `sessions/{device_id}`에는 다음 값이 저장된다.

```text
email                  원문 이메일
user.email             원문 이메일 중복
user.name              사용자 이름
user.picture           프로필 이미지 URL
refresh_token          Google 장기 인증 토큰
sheet_id               사용자 Google Sheet 식별자
sheet_title            시트 제목
worksheet_name         워크시트 이름
updated_at             마지막 이용 시각
```

관련 코드:

- [`save_session()`](https://github.com/veggar/my-favorite-watch/blob/9a4b6666b259ff5484a0c8ab286ed059d0a9c724/services/firestore_session.py#L19-L40)
- [`auth_callback()`](https://github.com/veggar/my-favorite-watch/blob/9a4b6666b259ff5484a0c8ab286ed059d0a9c724/routes/auth.py#L89-L131)
- [`auto_restore_session()`](https://github.com/veggar/my-favorite-watch/blob/9a4b6666b259ff5484a0c8ab286ed059d0a9c724/app.py#L73-L109)

### 4.2 법적·보안 판단

- 이메일을 해시하더라도 서비스가 동일 사용자의 기기와 데이터를 계속 연결할 수 있으면 완전한 익명정보로 단정하기 어렵다.
- 개인정보 보호법은 다른 정보와 쉽게 결합하여 개인을 알아볼 수 있는 정보 및 가명정보도 개인정보 정의에 포함한다. [개인정보 보호법 제2조](https://www.law.go.kr/LSW//lsLawLinkInfo.do?chrClsCd=010202&lsId=011357&lsJoLnkSeq=900648197&print=print)
- 개인정보위 가명정보 처리 가이드라인은 키 없는 해시, Salt 해시, 키 있는 해시/MAC를 구분한다. 이메일처럼 추측 가능한 입력에는 키 없는 해시보다 키 기반 방식을 사용해야 한다. [가명정보 처리 가이드라인](https://www.privacy.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_000000000843428&fileSn=0)
- 가명정보 및 추가정보에는 안전성 확보, 분리 보관과 접근권한 통제 등이 요구된다. [개인정보 보호법 시행령 제29조의5](https://www.law.go.kr/lumLsLinkPop.do?chrClsCd=010202&lspttninfSeq=159009)

따라서 HMAC 적용은 유출 시 직접 식별 위험을 줄이는 안전조치이지 개인정보 처리 의무를 면제하는 수단으로 표현해서는 안 된다.

## 5. 목표 인증·저장 구조

### 5.1 사용자 식별자

Google은 이메일이 변경될 수 있으므로 사용자 고유 식별자로 사용하지 말고, ID Token의 `sub`를 사용하도록 권고한다. `sub`는 Google 계정별로 고유하고 재사용되지 않는다. [Google OpenID Connect 문서](https://developers.google.com/identity/openid-connect/openid-connect)

내부 사용자 키는 다음과 같이 생성한다.

```text
user_key = "v1_" + BASE64URL(
  HMAC-SHA-256(USER_KEY_HMAC_SECRET, google_sub)
)
```

구현 조건:

- ID Token의 서명, `iss`, `aud`, `exp`를 검증한 뒤 `sub`를 사용한다.
- `sub`는 case-sensitive 값 그대로 입력한다.
- `USER_KEY_HMAC_SECRET`은 최소 32바이트의 독립 난수로 생성한다.
- `FLASK_SECRET_KEY`와 HMAC 키를 공유하지 않는다.
- HMAC 키는 소스, `.env`, 일반 Cloud Run 환경 변수 값으로 배포하지 않고 Google Secret Manager에서 주입한다.
- 키 버전을 `user_key_version`으로 저장해 향후 회전 가능하게 한다.
- 단순 SHA-256(email), 고정 공개 Salt, 저장 레코드별 임의 Salt는 사용하지 않는다. 레코드별 Salt는 멀티 디바이스의 결정적 조회를 방해한다.

### 5.2 권장 Firestore 구조

```text
users/{user_key}
  sheet_id
  sheet_title
  worksheet_name
  created_at
  updated_at
  schema_version

device_sessions/{device_id}
  user_key
  refresh_token
  created_at
  updated_at
  expires_at
  schema_version
```

설계 효과:

- 같은 계정은 모든 기기에서 같은 `user_key`를 사용한다.
- 시트 설정은 사용자당 한 번만 저장한다.
- refresh token은 기기별로 분리한다.
- 한 기기 로그아웃은 해당 `device_sessions` 문서만 삭제한다.
- 전체 로그아웃·계정 삭제는 `user_key` 기준으로 모든 기기 세션과 사용자 설정을 삭제한다.
- 동일 브라우저에서 Google 계정을 변경해도 서로 다른 `user_key`가 되어 기존 계정의 시트가 섞이지 않는다.

### 5.3 저장 최소화

Firestore에서 제거할 필드:

- `email`
- `user.email`
- `user.name`
- `user.picture`

표시용 이름·프로필이 반드시 필요하지 않으면 OAuth `profile` 범위와 사용자정보 API 호출도 제거한다. 필요한 경우에도 서버 영구 저장은 하지 않고 로그인 세션 수명 내에서만 사용한다.

추가 보안 조치:

- refresh token 접근권한을 Cloud Run 실행 서비스 계정으로 제한
- Firestore 백업·로그·내보내기 권한 최소화
- `device_sessions`에 90일 TTL 적용
- 계정 삭제 시 Google token revoke 후 사용자·기기 문서 삭제
- 애플리케이션 로그에 이메일, `sub`, `user_key`, access/refresh token, OAuth code 및 state를 기록하지 않음

> 현재 Flask 세션 쿠키는 서명만 되고 암호화되지 않는다. access token과 사용자 표시정보를 브라우저 쿠키에 넣는 현재 구조도 프로덕션 공개 전 서버 측 세션으로 이전하는 것을 보안 게이트로 권고한다. access token은 bearer credential이므로 일반 표시 데이터로 간주해서는 안 된다.

## 6. 구현 작업 목록

### P0-1. OAuth 콜백 진단성과 도메인 고정

대상: `routes/auth.py`, `app.py`, 배포 설정

- 운영 환경에서 `mfw.worldapex.studio`가 아닌 host로 접근하면 canonical URL로 308 리디렉션
- `/auth/google` 진입 전에 host와 `REDIRECT_URI`의 host 일치 확인
- `oauth_state` 누락과 불일치를 구분해 민감정보 없이 경고 로그 기록
- callback의 `error`, `error_description`을 사용자용 코드로 정규화
- `flow.fetch_token()` 실패 유형은 서버 로그에만 기록
- callback 성공 후 목적지를 `/login`, `/connect`, `/` 중 명시적으로 기록
- OAuth code와 state는 로그에 출력하지 않음

### P0-2. Google `sub` 검증 및 HMAC 사용자 키 도입

대상: 신규 `services/user_identity.py`, `routes/auth.py`, 설정·배포 문서

- ID Token 검증 함수 구현
- 검증된 `sub`로 `user_key` 생성
- `USER_KEY_HMAC_SECRET` Secret Manager 등록
- 이메일 기반 신규 조회 중단
- 사용자 키 버전 저장

### P0-3. 사용자와 기기 세션 분리

대상: `services/firestore_session.py`, `app.py`, `routes/auth.py`, 시트 설정 경로

- `users/{user_key}` CRUD 추가
- `device_sessions/{device_id}` CRUD 추가
- 자동 세션 복원 시 device session → user config 순서로 조회
- 시트 변경 시 사용자 문서만 갱신
- 기기 로그아웃과 전체 로그아웃을 분리
- 동일 브라우저 계정 전환 시 이전 계정 시트 정보를 재사용하지 않음

### P0-4. 원문 개인정보 점진적 마이그레이션

기존 사용자에게 `sub`가 저장되어 있지 않으므로 일괄 변환이 아니라 다음 로그인 시 점진적으로 마이그레이션한다.

1. 새 로그인에서 검증된 `sub`와 `user_key` 생성
2. 신규 `user_key` 문서가 없으면 현재 로그인 이메일로 기존 `sessions` 문서를 **한 번만** 조회
3. 기존 시트 설정을 `users/{user_key}`로 이전
4. 현재 기기의 refresh token을 `device_sessions/{device_id}`에 저장
5. 이전 문서에서 `email`, `user` 등 원문 개인정보 삭제
6. 마이그레이션 완료 플래그와 시각만 기록
7. 전환 기간 종료 후 이메일 fallback 코드와 이메일 인덱스 제거
8. 미접속 레거시 문서는 정한 보유기간 종료 시 TTL 또는 승인된 정리 작업으로 삭제

마이그레이션은 기존 계정의 시트 연결을 보존하되, 다른 이메일 계정의 시트를 연결하지 않도록 현재 로그인 이메일이 기존 문서의 이메일과 정확히 일치할 때만 수행한다.

### P1-1. 개인정보처리방침 및 권리 대응

- 수집·처리 항목, 목적, 보유기간, 파기방법 문서화
- Google OAuth, Google Sheets, Firestore 사용 사실 명시
- 처리위탁·국외 이전 해당 여부를 실제 계약·리전·운영 주체 기준으로 검토
- 현재 기기 로그아웃, 전체 기기 로그아웃, 계정 연결 해제·삭제 기능 제공
- 삭제 요청 처리 절차와 담당 연락처 제공
- 테스트 사용자에서 일반 사용자로 확대하기 전에 법률 또는 개인정보 보호 담당자 검토 완료

### P1-2. 서버 측 세션 전환

- 브라우저에는 예측 불가능한 세션 ID와 필요한 쿠키 속성만 저장
- access token 및 표시용 사용자정보는 서버 측 단기 세션에 저장
- refresh token은 기기 세션 저장소에서만 관리
- 서버 측 세션 TTL과 기기 세션 TTL을 분리
- 세션 ID 회전, 로그아웃 시 폐기, 탈취 대응 구현

## 7. 테스트 계획과 완료 기준

### 7.1 인증·도메인

- [ ] 새 도메인에서 로그인 요청과 callback의 `state`가 일치한다.
- [ ] 이전 공개 주소 접근 시 새 도메인으로 이동한 후 OAuth가 시작된다.
- [ ] callback 성공 시 `/connect` 또는 `/`로 이동하고 `/login`으로 반복되지 않는다.
- [ ] callback 실패 시 사용자에게 추적 가능한 오류 코드가 표시되고 서버에는 원인이 남는다.

### 7.2 동일 계정 멀티 디바이스

- [ ] 기기 A와 B에서 같은 Google 계정으로 로그인한다.
- [ ] A와 B의 `device_id`는 다르고 `user_key`는 같다.
- [ ] 두 기기에서 같은 Google Sheet가 열린다.
- [ ] A에서 수정한 항목이 B에서 새로고침 후 보인다.
- [ ] A 로그아웃 후 B 세션은 유지된다.
- [ ] 전체 로그아웃 수행 시 A와 B 세션이 모두 무효화된다.

### 7.3 계정 분리

- [ ] 같은 브라우저에서 계정 A → 계정 B로 변경해도 A의 시트가 B에 노출되지 않는다.
- [ ] 계정 A와 B의 `user_key`가 다르다.
- [ ] 계정 B가 A의 `sheet_id`를 복원하지 않는다.

### 7.4 개인정보 최소화

- [ ] Firestore `users`, `device_sessions`에 이메일 원문이 없다.
- [ ] 중첩된 `user.email`, 이름, 프로필 이미지 원문도 없다.
- [ ] 단순 이메일 해시가 없다.
- [ ] HMAC 키는 Secret Manager에서만 제공된다.
- [ ] 로그·오류 화면·테스트 fixture에 이메일, 토큰, OAuth code/state가 없다.
- [ ] 원문 개인정보 레거시 문서가 마이그레이션 또는 보유기간 만료 후 제거된다.

### 7.5 테스트 상태 제한

- [ ] 모든 테스트 계정이 Google Auth Platform의 Test users에 등록되어 있다.
- [ ] 테스트 모드 7일 refresh token 만료를 재현하고 재로그인 안내를 검증한다.
- [ ] OAuth 프로덕션 게시·검증 후 장기 세션 유지 시험을 별도로 수행한다.

## 8. 배포·마이그레이션 순서

1. 로그인·멀티 디바이스 회귀 테스트를 먼저 추가한다.
2. OAuth 콜백 진단 로그와 canonical host 처리를 배포한다.
3. HMAC Secret을 Secret Manager에 생성하고 Cloud Run 서비스 계정에 최소 접근권한을 부여한다.
4. `users`와 `device_sessions` 신규 구조를 추가하되 기존 읽기 경로는 임시 유지한다.
5. 테스트 계정으로 도메인 변경 후 재로그인·멀티 디바이스·계정 변경을 검증한다.
6. 점진적 마이그레이션을 활성화한다.
7. 레거시 문서에서 원문 개인정보 제거 여부를 집계한다. 값 자체는 로그에 남기지 않는다.
8. 안정화 기간 후 이메일 fallback과 기존 `sessions` 읽기 경로를 제거한다.
9. 개인정보처리방침·계정 삭제·전체 로그아웃을 완료한 후 OAuth 프로덕션 게시 절차로 이동한다.

## 9. 롤백 원칙

- 새 스키마 쓰기 실패 시 로그인 전체를 실패시키지 말고 사용자에게 재시도 가능한 오류를 표시한다.
- 레거시 원문 문서를 즉시 대량 삭제하지 않는다. 신규 문서 생성과 시트 연결 검증이 끝난 레코드부터 원문 필드를 제거한다.
- HMAC 키 장애 시 이메일 원문 저장으로 되돌아가지 않는다. 로그인을 일시 제한하고 키 접근을 복구한다.
- 롤백 시에도 새로 제거한 원문 개인정보를 복원하지 않는다.

## 10. 승인 완료 기준

다음 조건을 모두 만족하면 조치 완료로 승인한다.

1. 새 도메인에서 기존 테스트 계정 로그인 성공
2. 동일 계정 2개 이상 기기의 동시 접속 성공
3. 한 기기 로그아웃 후 다른 기기 세션 유지
4. 동일 브라우저의 다른 계정 전환 시 데이터 격리
5. Firestore 신규 문서에서 이메일·이름·프로필 이미지 원문 미저장
6. 검증된 Google `sub` 기반 HMAC 사용자 키 적용
7. 레거시 개인정보 마이그레이션·파기 정책 적용
8. 테스트 상태 7일 제한 문서화 및 프로덕션 전환 계획 승인
9. 개인정보처리방침과 계정 삭제/전체 로그아웃 절차 마련

## 참고 자료

- [Google OpenID Connect: `sub`를 사용자 고유키로 사용](https://developers.google.com/identity/openid-connect/openid-connect)
- [Google OAuth Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google OAuth 앱 Audience: 테스트 승인과 7일 만료](https://support.google.com/cloud/answer/15549945)
- [개인정보 보호법](https://www.law.go.kr/LSW//lsLawLinkInfo.do?chrClsCd=010202&lsId=011357&lsJoLnkSeq=900648197&print=print)
- [개인정보 보호법 시행령 제29조의5](https://www.law.go.kr/lumLsLinkPop.do?chrClsCd=010202&lspttninfSeq=159009)
- [개인정보위 가명정보 처리 가이드라인](https://www.privacy.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_000000000843428&fileSn=0)

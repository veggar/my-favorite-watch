# My Favorite Watch — Google Picker·`drive.file` 전환 계획 (task-2026-08-004)

- 작성일: 2026-08-23
- 기준 형상: `master` `f7c6439de806`, `v1.8.0`
- 문서 성격: 구현 계획. 이 문서 작성만으로 코드 변경, Google Cloud 설정 변경,
  OAuth 검증 제출, 배포를 승인하거나 수행한 것으로 보지 않는다.
- 활성 역할: `@pm-prime`, `@architect`, `@critico`, `@memory-curator`

## 1. 배경과 문제

현재 앱은 로그인 시 아래 범위를 요청한다.

```text
openid
userinfo.email
userinfo.profile
spreadsheets
drive.metadata.readonly
```

`drive.metadata.readonly`는 `services/google_sheets.py`의
`find_spreadsheet_by_name()`이 Google Drive 전체에서 이름이
`My Favorite Watch`인 시트를 자동 검색하기 위해 사용한다. 이 기능 때문에 앱은
모든 Drive 파일의 메타데이터를 볼 수 있는 **제한된 범위**를 요청하며, Google의
제한된 범위 심사와 보안 평가 대상이 된다.

Google이 권장하는 파일 단위 접근 모델로 전환한다.

```text
drive.metadata.readonly 제거
자동 이름 검색 제거
Google Picker + drive.file 도입
```

`drive.file`은 사용자가 Picker에서 직접 선택하거나 앱이 생성한 파일만 앱과
공유하는 비민감 범위다. 사용자가 선택하지 않은 Drive 파일의 메타데이터는 앱이
조회하지 않는다.

## 2. 목표와 비목표

### 2.1 목표

1. OAuth 요청과 Google Cloud 데이터 액세스에서
   `drive.metadata.readonly`를 완전히 제거한다.
2. Drive 전체를 이름으로 검색하는 서버 기능과 API 경로를 제거한다.
3. 사용자가 Google Picker에서 Google 스프레드시트 한 개를 직접 선택하여
   연결할 수 있게 한다.
4. 기존 **Google Sheet URL 직접 연결**과 **새 시트 생성** 경로를 동일하게
   유지한다.
5. 기존 저장 시트 복원, 다기기 공유, 워크시트 초기화, 가져오기, CRUD 동작을
   회귀시키지 않는다.
6. 브라우저에는 Picker에 필요한 `drive.file` 전용 단기 토큰만 메모리에 두고,
   서버 세션의 OAuth access/refresh token은 HTML·JavaScript·로그에 노출하지 않는다.

### 2.2 비목표

- `spreadsheets` 범위 제거 또는 시트 데이터 저장소 교체
- 작품/워크시트 스키마 변경
- CSV·Excel·타 시트 가져오기 동작 변경
- Google OAuth 검증 제출 및 프로덕션 배포 자체
- Google Picker로 파일 업로드, 복수 선택, 폴더 선택 기능 추가

## 3. 목표 사용자 흐름

### 3.1 저장된 연결 정보가 있는 사용자

- 기존과 동일하게 `users/{user_key}`의 저장된 시트 정보를 복원한다.
- `/connect`와 Picker를 거치지 않고 목록으로 진입한다.

### 3.2 저장된 연결 정보가 없는 사용자

`/connect`에서 자동 Drive 검색을 실행하지 않고 다음 세 가지 방법을 명시적으로
제공한다.

1. **Google Drive에서 선택** — 기본 권장 경로
2. **시트 URL 직접 입력** — 기존 경로 유지
3. **새 시트 만들기** — 기존 경로 유지

Picker는 다음 조건으로 제한한다.

- Google 스프레드시트 MIME 유형만 표시
- 한 번에 한 파일만 선택
- 사용자가 선택을 취소하면 연결 상태를 변경하지 않음
- 선택된 문서의 `id`와 `name`만 앱에 전달
- 서버가 Sheets API로 실제 접근 권한과 문서 유형을 다시 검증한 뒤 연결

JavaScript 또는 Picker 설정을 사용할 수 없는 환경에서는 URL 직접 연결과 새 시트
생성 폼을 계속 제공한다.

## 4. 목표 권한과 토큰 구조

### 4.1 서버 OAuth 범위

`services/google_credentials.py`의 `SCOPES`를 다음으로 변경한다.

```text
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/drive.file
```

- `spreadsheets`: 사용자가 연결한 시트의 읽기·쓰기·생성·워크시트 관리
- `drive.file`: 사용자가 Picker에서 선택하거나 앱이 생성한 파일에 대한 파일 단위 권한

### 4.2 Picker 토큰 — 권장 설계

기존 Flask 서버 OAuth 흐름은 로그인·오프라인 접근·refresh token 보관을 위해
그대로 유지한다. Picker를 열 때만 Google Identity Services Token Model을 사용해
브라우저에서 아래 단일 범위의 단기 access token을 받는다.

```text
https://www.googleapis.com/auth/drive.file
```

이 토큰은 다음 원칙을 지킨다.

- 사용자 버튼 클릭으로만 발급 요청
- JavaScript 메모리에서 Picker 생성에만 사용
- DOM, `localStorage`, `sessionStorage`, 쿠키, URL, 서버 로그에 저장하지 않음
- Picker 완료·취소·오류 후 참조 제거
- 기존 서버 세션의 복합 범위 access token을 템플릿이나 JSON 엔드포인트로 노출하지 않음

### 4.3 사전 기술 검증 게이트

본 구현 전 작은 스파이크로 아래를 먼저 확인한다.

1. 동일 OAuth Web Client ID로 발급한 `drive.file` 토큰이 Picker를 정상 표시하는지
2. Picker에서 선택한 파일을 기존 서버 자격증명의 Sheets API가 열 수 있는지
3. 브라우저에서 선택한 Google 계정과 서버 로그인 계정이 다를 때 403으로 안전하게
   실패하고 재선택 안내가 표시되는지
4. 팝업 차단, 토큰 만료, 사용자가 동의를 거부한 경우 URL/생성 경로가 유지되는지

스파이크가 실패하더라도 서버 access token을 브라우저에 바로 노출하지 않는다.
필요하면 별도 Picker 인증 코드 교환 경로를 설계한 뒤 보안 검토를 다시 받는다.

## 5. Google Cloud·운영 설정 계획

### 5.1 API와 OAuth 설정

1. `Google Picker API` 활성화
2. `Google Drive API`, `Google Sheets API` 활성 상태 유지
3. OAuth 데이터 액세스에 `drive.file` 추가
4. 코드 배포와 재동의 완료 후 `drive.metadata.readonly` 제거
5. OAuth Web Client의 승인된 JavaScript 원본 확인
   - 운영: `https://mfw.worldapex.studio`
   - 로컬: `http://localhost:8090`
6. Google Cloud 프로젝트 번호를 Picker `setAppId()` 값으로 사용

### 5.2 Picker 브라우저 API 키

Picker용 브라우저 API 키를 별도로 생성하고 다음과 같이 제한한다.

- 애플리케이션 제한: HTTP 리퍼러
- 운영 허용값: `https://mfw.worldapex.studio/*`
- 개발 키는 운영 키와 분리하고 `http://localhost:8090/*`만 허용
- API 제한: Google Picker API만 허용

브라우저 API 키는 Picker 프로토콜상 사용자에게 보이는 식별자이지만 무제한 키로
취급하지 않는다. 코드에 하드코딩하지 않고 환경 변수로 주입하며, 리퍼러와 API
제한을 배포 전 필수 게이트로 둔다.

### 5.3 신규 환경 변수

```text
GOOGLE_PICKER_API_KEY=
GOOGLE_CLOUD_PROJECT_NUMBER=641162137323
```

대상 문서와 스크립트:

- `.env.example`: 용도, 운영/개발 키 분리, 제한 조건 추가
- `SETUP.md`: Picker API·키·JavaScript 원본 설정 절차 추가
- `scripts/deploy.sh`: 필수값 검사와 Cloud Run 환경 변수 주입 추가

`GOOGLE_CLIENT_SECRET`, refresh token과 달리 Picker 브라우저 키를 Secret Manager
비밀로 오인하지 않는다. 대신 제한되지 않은 키로 배포되는 것을 검증 단계에서 막는다.

## 6. 코드 변경 계획

### 6.1 `services/google_credentials.py`

- `drive.metadata.readonly`를 `drive.file`로 교체
- 범위 상수 테스트에서 정확한 집합을 검증
- 기존 refresh token의 범위 불일치를 처리할 scope version 도입 여부 결정

### 6.2 `services/google_sheets.py`

- `find_spreadsheet_by_name()` 삭제
- 서버 측 `drive.files().list()` 호출 제거
- URL 추출, Sheets API 기반 접근 확인, 생성 및 CRUD 함수는 유지
- Picker가 전달한 ID도 `_attach_spreadsheet()`에서 다시 검증하도록 기존 검증 경로 재사용

### 6.3 `routes/sheet.py`

- `find_spreadsheet_by_name` import 제거
- `POST /connect/discover` 제거
- `POST /connect/use-found` 제거
- `POST /connect/use-picked` 추가
  - 로그인 및 전역 CSRF 검증 필수
  - JSON의 `sheet_id`, `title`, `worksheet_name` 길이·형식 검증
  - 클라이언트가 보낸 제목을 신뢰하지 않고 Sheets API 응답의 실제 제목을 기준으로 저장
  - `_attach_spreadsheet()`로 접근 권한, 문서 존재, 워크시트 초기화 재검증
  - 오류 원문·토큰·파일 ID를 사용자 응답이나 로그에 노출하지 않음
- 기존 `/connect/by-url`, `/connect/create`, 폼 POST 폴백은 유지
- `connect()`가 Picker 설정 가능 여부와 공개 설정값만 템플릿에 전달

### 6.4 `templates/connect.html`

- 페이지 로드 시 자동 `/connect/discover` 호출 삭제
- `step-found`, `foundSheet`, `discover()`, `useFound()` 및 관련 이전 버튼 제거
- 첫 화면을 세 가지 명시적 연결 방식으로 재구성
- `Google Drive에서 선택` 버튼 추가
- Google Identity Services와 Google API Loader를 공식 HTTPS URL에서 지연 로드
- Picker 구성
  - `PickerBuilder.setAppId(projectNumber)`
  - `setDeveloperKey(pickerApiKey)`
  - `setOAuthToken(driveFileToken)`
  - Google Sheets MIME 유형만 허용
  - 단일 선택
  - `setOrigin(window.location.origin)`
- `PICKED`, `CANCEL`, `ERROR` 결과를 구분
- 선택 성공 시 `/connect/use-picked`로 `sheet_id`만 우선 전달하고 서버 검증 결과 표시
- Picker 설정 누락·스크립트 로드 실패·팝업 차단 시 URL 직접 연결과 생성 탭으로 유도
- 기존 로딩·성공·실패·재시도 UI와 `Now Loading` 표준 유지

인라인 JavaScript가 비대해지면 `static/js/google-picker.js`로 분리한다. 템플릿에는
환경 설정값과 초기화 호출만 남긴다.

### 6.5 인증 범위 마이그레이션

기존 사용자의 refresh token은 `drive.metadata.readonly`를 포함하고
`drive.file`을 포함하지 않을 수 있다. 새 `SCOPES`로 단순 교체하면 자동 복원 시
범위 불일치 또는 Picker 권한 실패가 발생할 수 있다.

권장안:

1. OAuth scope version을 `v2`로 정의
2. 새 로그인 콜백에서 scope version을 기기/서버 세션과 함께 저장
3. 구버전 또는 미기록 refresh token은 삭제하지 않고 자동 복원만 중단하여
   사용자에게 1회 재동의를 요청
4. 신규 동의 요청은 `drive.file`만 포함하고 `drive.metadata.readonly`는 요청하지 않음
5. `include_granted_scopes`가 기존 제한 범위를 다시 포함시키지 않는지 스파이크로 확인하고,
   필요하면 마이그레이션 기간에 `false`로 전환
6. 재동의 성공 후 새 refresh token과 scope version으로 기존 문서를 갱신

사용자 Drive 파일이나 저장 시트 설정은 삭제하지 않는다. refresh token 폐기 또는
Google 권한 철회가 필요하면 별도의 운영 승인과 사용자 안내 후 수행한다.

## 7. 문서·정책 변경 계획

### 7.1 `PRD.md`

- §4.1 필요 스코프를 `drive.file`로 교체
- §13.1.2를 자동 이름 검색에서 Picker 사용자 선택 흐름으로 재작성
- §13.1.3에 URL 직접 연결과 새 시트 생성 유지 명시
- §17에 Picker 취소·계정 불일치·팝업 차단·설정 누락 오류 처리 추가
- §18의 최소 권한 설명을 파일 단위 선택 모델로 변경
- 브라우저 공개 API 키는 리퍼러/API 제한을 전제로 하는 예외임을 명시

### 7.2 `SETUP.md`

- Google Picker API 활성화
- Picker 브라우저 API 키 생성·제한
- OAuth JavaScript 원본
- `drive.file`과 `spreadsheets`의 용도 및 검증 구분
- scope migration으로 기존 사용자가 한 번 재동의할 수 있다는 운영 안내
- 로컬·운영 Picker 수동 검증 절차 추가

### 7.3 개인정보처리방침

대상:

- `templates/privacy.html`
- `docs/legal/privacy-policy-draft.md`

변경 내용:

- `drive.metadata.readonly` 제거
- `drive.file` 추가
- “Drive 전체 메타데이터 검색”이 아니라 “사용자가 Picker에서 선택하거나 앱이 생성한
  파일에만 접근”한다고 설명
- 실제 정책 페이지를 수정하기 전 `scripts/archive_policy_snapshot.py`로 기존 공개
  버전을 보관

## 8. 테스트 계획

### 8.1 자동 테스트

신규 테스트 파일 예시:

```text
tests/test_google_picker_connection.py
```

검증 항목:

1. `SCOPES`에 `drive.file`이 있고 `drive.metadata.readonly`가 없음
2. 서버 코드에 `drive.files().list()`와 `find_spreadsheet_by_name()`이 없음
3. `/connect`가 더 이상 `/connect/discover`를 자동 호출하지 않음
4. `/connect`에 Drive 선택, URL 연결, 새 시트 생성 세 경로가 표시됨
5. Picker 미설정 환경에서도 URL/생성 폼이 동작함
6. `/connect/use-picked`
   - 비로그인 거부
   - CSRF 누락 거부
   - 빈 값·잘못된 ID 거부
   - 접근 가능한 시트 연결 성공
   - 403/404 오류 정제
   - 클라이언트 제목 대신 서버 조회 제목 저장
7. URL 직접 연결과 새 시트 생성의 기존 요청·응답 회귀 테스트
8. Picker 토큰이나 API 키가 서버 로그·오류 응답·세션 저장소에 남지 않음
9. scope version이 없는 기존 기기 세션은 안전하게 재동의 경로로 이동

전체 회귀:

```bash
.venv/bin/python -m pytest tests/ -q
```

### 8.2 수동 브라우저 검증

- 운영 도메인에서 Picker 팝업 표시
- Google Sheets만 표시되고 복수 선택이 불가능함
- 선택·취소·팝업 차단·잘못된 계정·토큰 만료 처리
- 선택한 시트에만 연결되고 다른 Drive 파일을 자동 조회하지 않음
- URL 직접 연결과 새 시트 생성 정상
- 모바일 폭과 키보드 탐색에서 버튼·오류 UI가 겹치지 않음
- 로그아웃·재로그인·다른 기기에서 저장 시트 복원 정상

### 8.3 정적·배포 검증

```bash
bash -n scripts/deploy.sh
git diff --check
.venv/bin/python -m pytest tests/ -q
```

배포 후 Cloud Run 로그에서 토큰, Picker 키, 시트 ID 원문이 출력되지 않는지 확인한다.

## 9. 구현 순서

| 단계 | 작업 | 완료 기준 |
|---|---|---|
| P0 | Picker 토큰·계정 일치 스파이크 | 서버 토큰 노출 없이 선택 파일을 연결할 수 있음 |
| P1 | OAuth scope·scope version 변경 | 신규 동의에 `drive.file`만 포함, 제한 범위 미요청 |
| P2 | 서버 자동 검색 제거 | Drive 목록 API 호출과 관련 엔드포인트가 없음 |
| P3 | Picker UI·연결 엔드포인트 구현 | 선택·취소·실패·재시도 흐름 통과 |
| P4 | URL·생성 경로 회귀 보강 | JS·비JS 환경 모두 기존 기능 유지 |
| P5 | PRD·SETUP·방침 현행화 | 코드·콘솔·공개 문서의 범위가 일치 |
| P6 | 전체 테스트·수동 검증 | 자동 테스트 및 운영 전 체크리스트 통과 |
| P7 | Google Cloud 설정·재동의·배포 | 제한 범위 제거 확인 후 OAuth 검증 재제출 가능 |

소스 기능 추가이므로 구현 커밋 전 `version.py`를 `v1.9.0`으로 올리는 것을
권장한다. 비trivial 변경이므로 `claude/google-picker-drive-file` 브랜치에서 작업하고,
머지 시 프로젝트 규칙에 맞는 날짜 태그를 생성한다.

## 10. 배포·OAuth 검증 순서

1. 별도 브랜치·로컬 환경에서 구현 및 전체 테스트
2. Google Picker API·제한된 브라우저 키·JavaScript 원본 준비
3. Google Cloud 데이터 액세스에 `drive.file` 추가
4. 앱 배포 후 새 OAuth 요청과 Picker 흐름 확인
5. 기존 사용자 1회 재동의 및 scope version 전환 확인
6. 코드·라이브 요청에서 `drive.metadata.readonly`가 사라졌음을 확인
7. Google Cloud 데이터 액세스에서 `drive.metadata.readonly` 제거
8. 개인정보처리방침·PRD·SETUP과 콘솔 범위 최종 대조
9. `spreadsheets` 민감 범위 검증을 제출하고 승인 전까지 미확인 앱 경고를 예상 상태로 관리

단계 3~9는 외부 상태 변경이므로 구현 완료 후 별도 승인을 받아 수행한다.

## 11. 완료 기준

- [ ] 코드·문서·OAuth 요청 어디에도 `drive.metadata.readonly`가 없음
- [ ] 서버가 Drive 전체 파일 목록이나 메타데이터를 검색하지 않음
- [ ] Picker는 `drive.file`, 단일 Google Sheet 선택만 사용
- [ ] 서버 access/refresh token이 브라우저나 로그에 노출되지 않음
- [ ] 선택한 시트 ID를 서버가 Sheets API로 재검증함
- [ ] 시트 URL 직접 연결이 이전과 동일하게 동작함
- [ ] 새 시트 생성이 이전과 동일하게 동작함
- [ ] 저장 시트 자동 복원과 다기기 흐름이 유지됨
- [ ] 기존 사용자의 1회 재동의 경로가 검증됨
- [ ] 개인정보처리방침과 Google Cloud 데이터 액세스 범위가 실제 코드와 일치함
- [ ] `.venv/bin/python -m pytest tests/ -q` 전체 통과
- [ ] Google OAuth 검증 제출용 데모에 Picker 선택과 시트 읽기·쓰기 흐름이 포함됨

## 12. 주요 리스크와 결정 필요 사항

1. **이중 OAuth UX**: 기존 서버 로그인 뒤 Picker가 `drive.file` 토큰을 요청하면서
   계정 선택 또는 동의를 한 번 더 표시할 수 있다. 스파이크에서 최소화 방법을 확정한다.
2. **계정 불일치**: Picker 계정과 서버 로그인 계정이 다르면 연결이 실패해야 하며,
   계정을 바꾸라는 명확한 안내가 필요하다.
3. **기존 refresh token**: 제한 범위가 남아 있는 기존 권한을 파괴적으로 일괄 삭제하지
   않는다. scope version 기반 1회 재동의를 우선한다.
4. **브라우저 API 키 노출**: 키는 공개가 전제지만 제한 설정 누락 시 남용될 수 있다.
   리퍼러·API 제한 확인을 배포 게이트로 둔다.
5. **검증 일정**: `drive.file`은 비민감 범위지만 `spreadsheets`는 계속 민감 범위이므로
   Google OAuth 민감 범위 검증 자체는 여전히 필요하다.

## 13. 참고 근거

- Google Drive API: `drive.file`은 앱에서 열거나 Picker로 공유한 파일에 대한
  비민감·파일 단위 접근 범위다.
- Google Picker Web Guide: Picker 생성에는 OAuth token, Browser API key,
  Cloud project number(`setAppId`)와 callback이 필요하다.
- 현재 코드 근거:
  - `services/google_credentials.py` — OAuth 범위
  - `services/google_sheets.py` — 이름 기반 Drive 검색과 Sheets CRUD
  - `routes/sheet.py` — discover/use-found/URL/생성 연결 경로
  - `templates/connect.html` — 자동 검색 중심 UI
  - `PRD.md` §4.1, §13.1, §18
  - `SETUP.md` §2~3

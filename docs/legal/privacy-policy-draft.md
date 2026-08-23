# My Favorite Watch 개인정보처리방침 콘텐츠 초안

> 상태: 콘텐츠 검토용 초안. `/privacy` 라우트(`routes/site.py`, `templates/privacy.html`)는
> 구현되어 있으나, 아래 "배포 전 필수 확인" 항목과 법률 전문가 검토가 끝나기
> 전에는 실제 서비스로 공개하지 않는다. 화면에 반영되는 값은
> `SERVICE_OPERATOR` / `PRIVACY_CONTACT_EMAIL` / `SERVICE_URL` /
> `POLICY_EFFECTIVE_DATE` 4개 환경 변수뿐이며, 그 밖의 `[확인 필요]` 표시는
> 이 문서를 갱신해 템플릿에 반영해야 한다.  
> 기준일: 2026-08-20  
> 시행일: [운영자 입력 필요]  
> 이 문서는 법률 자문이 아니며, 실제 공개 전 운영자 정보·국외 이전 현황·보유기간을 확정하고 법률 전문가의 검토를 받아야 합니다.

이 초안은 기준일 현재 개인정보보호위원회의 2026년 4월 작성지침을 참고했습니다.
2026년 9월 11일 시행 예정인 개정 개인정보 보호법(법률 제21445호)의 사업주·
개인정보 보호책임자 책임 강화 등은 실제 시행일과 서비스 규모에 맞춰 공개 전에
다시 확인해야 합니다.

My Favorite Watch 운영자(이하 "운영자")는 이용자의 개인정보를 중요하게 여기며,
「개인정보 보호법」 등 적용되는 법령을 준수합니다. 이 방침은 서비스가 어떤
정보를 어떤 목적으로 처리하고, 이용자가 어떻게 권리를 행사할 수 있는지
설명합니다.

## 1. 개인정보처리자

- 서비스명: My Favorite Watch
- 운영 주체(상호 또는 성명): [운영자 입력 필요]
- 대표자: [해당하는 경우 운영자 입력 필요]
- 주소: [운영자 입력 필요]
- 문의 이메일: [운영자 입력 필요]

운영 주체와 문의 수단이 확정되기 전에는 이 초안을 운영 서비스에 공개하지 않습니다.

## 2. 처리하는 개인정보, 목적 및 보유기간

| 구분 | 처리 항목 | 처리 목적 | 보유기간 |
|---|---|---|---|
| Google 로그인 | Google OIDC `sub`, 이메일, 이름, 프로필 이미지 | 본인 확인, 로그인 화면 및 설정 화면의 계정 정보 표시 | 표시 정보는 서버 세션에서 마지막 사용 후 최대 90일. 인증 신선도가 12시간을 넘은 뒤 다음 요청이 발생하면 제거 |
| 내부 사용자 식별 | 검증된 Google `sub`에 서버 비밀키 HMAC을 적용한 `user_key`, 키 버전 | 계정별 시트 설정 분리, 여러 기기에서 동일 계정 확인 | 시트 연결 설정 삭제 또는 이용자 삭제 요청 시까지 |
| OAuth 인증 | access token, refresh token, 토큰 만료 시각, 인증 시각 | Google Sheets·Drive API 접근, 로그인 자동 복원 | access token과 서버 세션은 마지막 사용 후 최대 90일, refresh token이 포함된 기기 세션은 마지막 사용 후 최대 90일. 로그아웃 시 대상 세션을 즉시 삭제 |
| 기기·서버 세션 | 임의 `device_id`, 임의 session ID의 SHA-256 문서 키, OAuth state, PKCE verifier, CSRF 값 | 로그인 유지, OAuth·CSRF 요청 검증, 기기별·전체 로그아웃 | 쿠키와 Firestore 세션 문서는 마지막 사용 후 최대 90일. OAuth·CSRF 임시 값은 해당 요청 완료 또는 세션 종료 시까지 |
| 시트 연결 정보 | Google Sheet ID, 문서명, 워크시트명 | 이용자가 선택한 Google Sheet 연결과 자동 복원 | 시트 연결 해제 또는 이용자 삭제 요청 시까지 |
| 작품 기록 | 제목, 원제, 장르, 분류, 관람 여부·날짜, 개인·공식 평점, 후기, 줄거리, TMDb 링크, 등록·수정·삭제 시각 | 이용자 본인의 영상 작품 기록 조회·등록·수정·삭제·복구 | 운영자 서버에 영구 저장하지 않고 이용자 본인의 Google Sheet에 저장. 삭제 시에도 `삭제` 워크시트로 이동하므로 완전 삭제는 이용자가 Google Sheet에서 직접 수행 |
| 파일 가져오기 | 이용자가 업로드한 CSV·Excel 내용과 파싱 결과 | 미리보기와 Google Sheet 일괄 등록 | 서버 측 단기 저장소(Firestore `csv_import_staging`, 로컬 폴백 시 프로세스 메모리)에 최대 30분 보관하며, 등록 완료 시 즉시 삭제한다. 등록하지 않고 이탈해도 TTL로 만료된다 |
| TMDb 보강 상태 | 작품 item ID, 처리 상태, 만료 시각 | 여러 서버 인스턴스에서 TMDb 검색 진행률 공유 | 작업 완료 후 TTL 삭제 대상. 실제 TTL 정책 `ACTIVE` 여부를 배포 전 확인 |
| 접속 기록 | IP 주소, User-Agent, 접속 일시, 요청 URL·응답 상태 등 호스팅 과정에서 생성될 수 있는 기술 정보 | 장애 대응, 보안 및 부정 이용 방지 | [Google Cloud 로그 설정과 실제 보존기간 확인 후 운영자 입력 필요] |

서비스는 주민등록번호, 결제정보, 건강정보 등 민감정보나 고유식별정보의 입력을
요구하지 않습니다. 이용자는 후기·줄거리·파일에 타인의 개인정보 또는 민감정보를
입력하지 않아야 합니다.

## 3. Google API 정보의 이용과 저장

- 서비스는 `openid`, `userinfo.email`, `userinfo.profile`, `spreadsheets`,
  `drive.file` 권한을 요청합니다.
- `drive.file` 권한은 이용자가 Google Picker에서 직접 선택하거나 서비스가
  생성한 파일에만 적용됩니다. 서비스는 이용자의 Google Drive 전체 파일
  목록이나 메타데이터를 조회하지 않습니다.
- 이메일·이름·프로필 이미지는 로그인한 이용자에게 계정을 표시하기 위해 사용하며,
  Firestore `users` 또는 `device_sessions` 컬렉션에는 저장하지 않습니다.
- Google Sheet 내용은 이용자가 요청한 조회·등록·수정·삭제·복구 기능을 수행할
  때만 접근합니다.
- Google API에서 받은 정보를 광고, 신용평가, 데이터 판매 또는 사람에 의한
  일반적 열람 목적으로 사용하지 않습니다.
- Google API 정보의 이용은
  [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)와
  [Google OAuth 2.0 정책](https://developers.google.com/identity/protocols/oauth2/policies)을 준수해야 합니다.

## 4. 개인정보의 제3자 제공

운영자는 이용자의 개인정보를 원칙적으로 제3자에게 판매하거나 제공하지 않습니다.
다만 이용자가 기능을 요청할 때 다음 외부 API로 필요한 정보가 전송됩니다.

| 제공받는 자 | 제공 항목 | 목적 | 보유·이용기간 |
|---|---|---|---|
| Google LLC | OAuth 인증 요청, Google 계정 식별·표시 정보, 이용자가 선택한 Google Sheet의 ID와 작품 기록 | Google 로그인, Sheets·Drive API 기능 수행 | Google 정책과 이용자 Google 계정 설정에 따름 |
| The Movie Database(TMDB) 운영 주체 [정확한 법인명 확인 필요] | 작품 제목과 검색 유형(movie 또는 tv). 서비스의 `user_key`, 이메일 및 Google 토큰은 전송하지 않음 | 작품 링크·공식 평점·원제 검색 | TMDB 정책에 따름 |

이용자가 Google 로그인 또는 TMDb 자동 보강을 사용하지 않으면 해당 기능을 제공할
수 없습니다. TMDb API 키가 비활성화된 환경에서는 TMDb로 작품 제목을 전송하지 않습니다.

## 5. 개인정보 처리업무의 위탁

| 수탁자 | 위탁업무 | 처리 항목 | 보유기간 |
|---|---|---|---|
| Google LLC 및 Google Cloud 재수탁자 | Firebase Hosting, Cloud Run, Firestore, 로그·비밀정보 관리 등 서비스 인프라 제공 | 서버 세션, 내부 사용자 키, 시트 연결정보, OAuth 토큰, TMDb 작업 상태 및 기술 로그 | 서비스 설정과 Google Cloud 계약·정책에 따름 |

실제 수탁자·재수탁자와 계약 주체는 운영 Google Cloud 계정의 계약 및
[Google Cloud 하위처리자 목록](https://cloud.google.com/terms/subprocessors)을
기준으로 배포 전에 확인합니다.

## 6. 개인정보의 국외 이전

Google OAuth·API 및 Google Cloud 서비스는 국외 사업자가 제공하며, Google Cloud의
계약 조건상 고객 데이터가 Google 또는 하위처리자의 시설이 있는 국가에서 처리될
수 있습니다. TMDb 검색 요청도 국외 서버로 전송될 수 있습니다.

공개 전 아래 표를 실제 계약·리전·네트워크 구성에 맞게 확정해야 합니다.

| 이전받는 자·연락처 | 이전 국가 | 이전 항목 | 이전 목적 | 이전 시점·방법 | 보유기간 | 거부 방법과 영향 |
|---|---|---|---|---|---|---|
| Google LLC [연락처 확인 필요] | 대한민국(`asia-northeast3`) 저장 설정 및 국외 처리 가능 국가 [확인 필요] | 제5조 수탁 처리 항목 | 호스팅, 인증, Google API 제공 | 서비스 이용 시 암호화된 네트워크 전송 | 계약·설정에 따름 | Google 로그인을 거부하거나 Google 계정 권한을 철회할 수 있으나 서비스 이용 불가 |
| TMDB 운영 주체 [법인명·연락처 확인 필요] | [운영자 확인 필요] | 작품 제목, 검색 유형 | 작품 메타데이터 검색 | TMDb 보강 요청 시 암호화된 네트워크 전송 | TMDb 정책에 따름 | TMDb 기능을 사용하지 않을 수 있으며 작품 기록의 기본 기능은 이용 가능 |

국외 이전의 법적 근거, 국가, 연락처와 보유기간이 확정되지 않은 현재 상태에서는
이 절을 완성된 고지로 간주하지 않습니다.

## 7. 개인정보의 파기

- 보유기간이 끝나거나 처리 목적이 달성된 개인정보는 복구하기 어렵게 삭제합니다.
- `/logout`은 현재 기기의 기기 세션과 서버 세션을 삭제합니다.
- `/logout-all`은 같은 계정의 모든 기기 세션과 서버 세션을 삭제합니다.
- 로그아웃만으로 `users/{user_key}`의 시트 연결정보 또는 이용자 Google Sheet의
  작품 기록이 삭제되지는 않습니다.
- 시트 연결 해제는 `users/{user_key}`의 시트 연결 값을 비우지만 Google Sheet
  원본은 삭제하지 않습니다.
- 서비스에 저장된 사용자 설정의 완전 삭제는 아래 문의처로 요청해야 합니다.
  계정 삭제 기능이 구현되면 이 문구와 실제 동작을 함께 갱신합니다.
- Google Sheet의 작품 기록과 `삭제` 워크시트는 이용자가 Google Sheets에서 직접
  삭제할 수 있습니다.
- Google 계정의 서비스 연결 페이지에서 접근 권한을 철회할 수 있습니다.

## 8. 이용자와 법정대리인의 권리 및 행사 방법

이용자는 자신의 개인정보에 대해 열람, 정정·삭제, 처리정지 및 동의 철회를 요청할
수 있습니다. 요청은 제11조의 문의처로 접수하며, 운영자는 본인 확인 후 법령에서
정한 기간 안에 처리합니다.

- Google 계정 정보: Google 계정에서 직접 수정하거나 권한 철회
- 작품 기록: 연결된 본인 Google Sheet에서 직접 열람·정정·삭제
- 시트 연결정보: 설정 화면의 "시트 연결 해제" 사용
- 현재 기기 세션: "이 기기에서 로그아웃" 사용
- 모든 기기 세션: "모든 기기에서 로그아웃" 사용
- 그 밖의 서버 저장정보 삭제: [운영자 문의 이메일 입력 필요]로 요청

**운영자 결정(2026-08-20)**: 서비스는 별도의 연령 제한을 두지 않으며,
Google 계정을 보유한 누구나 이용할 수 있습니다. 별도의 법정대리인 동의
절차는 두지 않고, Google 계정 생성·이용에 적용되는 Google 자체의 최소
연령 정책에 위임합니다.

## 9. 개인정보의 안전성 확보조치

- Google OAuth 2.0과 PKCE, ID Token 서명·발급자·대상·만료 검증
- 이메일 대신 검증된 Google `sub`에 비밀키 HMAC을 적용한 내부 사용자 키 사용
- refresh token과 서버 비밀키를 브라우저 쿠키에 저장하지 않음
- 서버 세션 문서 키에 원본 session ID 대신 SHA-256 해시 사용
- HTTPS, HttpOnly, Secure, SameSite=Lax 쿠키와 CSRF 검증 적용
- 운영 비밀정보를 환경 변수와 Secret Manager로 분리
- 로그에서 이메일, 토큰, OAuth code·state 및 내부 사용자 키 원문 제외
- 화면에는 정제된 오류만 표시하고 상세 예외는 접근이 통제된 서버 로그에 기록

## 10. 쿠키 및 자동 수집 정보

서비스는 로그인 유지와 보안을 위해 `__session` 쿠키 하나를 사용합니다. 쿠키에는
서버 세션 식별자, 기기 식별자, OAuth·CSRF 임시 값과 UI 상태가 들어갑니다.
CSV·Excel 가져오기 미리보기 결과도 현재 이 서명 쿠키에 임시 저장될 수 있습니다.
서명은 위변조를 막지만 내용을 암호화하지 않으므로, 이 가져오기 데이터는 공개 전
서버 측 단기 저장으로 옮기는 것을 보안 요구사항으로 관리합니다.

이 쿠키는 광고나 이용자 행동 추적을 위한 것이 아니며, 현재 서비스는 맞춤형 광고·
광고 SDK·제3자 웹 분석 도구를 사용하지 않습니다.

브라우저 설정에서 쿠키를 거부하거나 삭제할 수 있지만, 이 경우 Google 로그인과
서비스 이용이 불가능하거나 다시 로그인해야 할 수 있습니다.

## 11. 개인정보 보호책임자 및 권익침해 구제

- 개인정보 보호책임자: [운영자 입력 필요]
- 직위 또는 역할: [운영자 입력 필요]
- 이메일: [운영자 입력 필요]
- 전화번호: [선택 입력]

개인정보 침해에 관한 상담이나 신고가 필요한 경우 다음 기관에 문의할 수 있습니다.

- 개인정보침해신고센터: 국번 없이 118, <https://privacy.kisa.or.kr>
- 개인정보분쟁조정위원회: 1833-6972, <https://www.kopico.go.kr>
- 대검찰청: 국번 없이 1301, <https://www.spo.go.kr>
- 경찰청: 국번 없이 182, <https://ecrm.police.go.kr>

## 12. 개인정보처리방침의 변경

이 방침이 변경되면 시행 전에 서비스 화면에서 변경 내용과 시행일을 알립니다.
이용자의 권리에 중대한 영향을 주는 변경은 개정 전 또는 개정 즉시 별도로
안내하고, 이전 버전을 확인할 수 있도록 보관합니다.

- 공고일: [운영자 입력 필요]
- 시행일: [운영자 입력 필요]

## 배포 전 필수 확인

- [ ] 운영 주체, 주소, 문의처, 개인정보 보호책임자 확정 (운영 주체명·문의 이메일은 `SERVICE_OPERATOR`/`PRIVACY_CONTACT_EMAIL` 환경 변수로 2026-08-20 확정. 물리 주소·대표자·개인정보 보호책임자 지정은 아직 미확정 — `services/site_info.py`가 다루지 않는 항목)
- [ ] 한국 사용자 대상 여부 및 운영 주체 소재지 확정
- [x] 만 14세 미만 이용 정책 확정 — 2026-08-20 운영자 결정: 별도 연령 제한 없이 Google 계정 보유자 누구나 이용 가능. Google 계정 자체의 최소 연령 정책에 위임 (본문 8절, `templates/privacy.html` 반영 완료)
- [x] Google Cloud 실제 로그 항목·보존기간과 Firestore TTL `ACTIVE` 확인 — 2026-08-21 확인·적용 완료. Cloud Logging `_Default` 30일/`_Required` 400일(GCP 기본값, 별도 연장 없음). Firestore `refresh-token` DB의 `tmdb_jobs`·`device_sessions`·`server_sessions`·`csv_import_staging` 4개 컬렉션 모두 `expires_at` 기준 TTL `ACTIVE` (`gcloud firestore fields ttls list --database=refresh-token`로 확인 가능)
- [x] `csv_import_data`를 서명 쿠키에서 서버 측 단기 저장으로 이전하고 만료·삭제 검증 — 2026-08-20 `services/csv_import_staging.py`(Firestore `csv_import_staging` 컬렉션, 30분 TTL, 등록 시 1회 소비 후 즉시 삭제)로 이전 완료. 쿠키에는 `csv_staging_id`만 남는다
- [ ] Google·TMDb의 정확한 수탁·제공·국외 이전 법인명, 국가, 연락처, 보유기간 확인
- [ ] 계정·서버 저장정보 삭제 요청 처리 절차와 처리기한 확정
- [x] 로그인 화면 링크, 이전 버전 보관 기능 구현 — 2026-08-20 완료. `services/policy_history.py` + `/privacy/history`, `/privacy/history/<시행일>`. 콘텐츠를 바꾸기 전에 `python3 scripts/archive_policy_snapshot.py privacy`로 현재 라이브 화면을 얼려 보관한 뒤 수정한다 (아직 실행한 적 없음 — 최초 버전이라 보관된 이전 버전은 없음)
- [ ] `/privacy` 실제 공개 (로그인 없이 열람 가능한 상태로 두는 것과 별개로, 홍보·Google 앱 검증 제출 등 "공개"로 취급하는 행위는 위 항목들이 모두 끝난 뒤 진행)
- [ ] 2026-09-11 시행 개인정보 보호법 및 하위 법령의 적용 여부 재검토
- [ ] 법률 전문가 최종 검토

## 작성 기준

- [개인정보보호위원회 개인정보 처리방침 작성지침(2026.4 개정)](https://www.pipc.go.kr/np/cop/bbs/selectBoardList.do?bbsId=BS217&mCode=D010030030)
- [개인정보 보호법 2026-09-11 시행 개정문](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=283839&viewCls=lsRvsDocInfoR)
- [Google OAuth 2.0 정책](https://developers.google.com/identity/protocols/oauth2/policies)
- [Google Cloud Data Processing Addendum](https://cloud.google.com/terms/data-processing-addendum)
- [TMDB API 이용약관](https://www.themoviedb.org/api-terms-of-use)

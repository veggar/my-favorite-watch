# Firebase Hosting 구성

`mfw.worldapex.studio` → Firebase Hosting → Cloud Run(`my-favorite-watch`) 경로의
구성 사본이다. 실제 배포는 별도 관리 디렉터리에서 수행하며, 이 디렉터리는
**구성이 유실되거나 재현이 필요할 때의 기준**이다.

```text
브라우저 ──HTTPS──▶ Firebase Hosting(CDN) ──rewrite──▶ Cloud Run
mfw.worldapex.studio        my-favorite-watch.web.app        asia-northeast3
```

DNS(Porkbun): `mfw` → CNAME `my-favorite-watch.web.app`

## 파일

| 파일 | 용도 |
|----|----|
| `firebase.json` | Cloud Run rewrite 구성. 운영 값과 동일하게 유지한다 |
| `.firebaserc.example` | 프로젝트 연결 예시. 실제 `.firebaserc`는 배포 디렉터리에 둔다 |

## 애플리케이션이 반드시 지켜야 하는 제약

Firebase Hosting을 경유하기 때문에 생기는 제약이다. 위반하면 조용히 깨진다.

1. **백엔드로 전달되는 쿠키는 `__session` 하나뿐이다.**
   다른 이름의 쿠키는 요청에서 제거되어 Cloud Run에 도달하지 않는다.
   그래서 세션 쿠키 이름이 `__session`이고, `device_id`는 별도 쿠키가 아니라
   세션 내부 필드다. **쿠키를 새로 추가하지 말 것.**
2. **동적 응답은 CDN에 캐시되면 안 된다.**
   앱이 정적 파일 외 모든 응답에 `Cache-Control: private, no-store`를 붙인다.
3. **`firebase-public/`은 비어 있어야 한다.**
   rewrite는 정적 파일이 없을 때만 적용되므로, `index.html`이 있으면 `/`가
   Cloud Run에 도달하지 않는다.
4. **Cloud Run 서비스는 공개(`--allow-unauthenticated`)여야 한다.**
   따라서 `run.app` 기본 URL로 Firebase를 우회하는 경로가 항상 열려 있다.
   앱의 canonical host 리디렉션(308)이 이를 커버한다.
5. **백엔드 응답 대기 한도는 60초다.** `TMDB_ENRICH_CHUNK` 기본값 15를 유지한다.

## 배포

Cloud Run 배포(`scripts/deploy.sh`)와 Hosting 배포는 **서로 독립**이다.
Cloud Run 리비전이 바뀌어도 서비스 이름과 리전이 그대로면 Hosting을 다시
배포할 필요가 없다. `serviceId`나 `region`을 바꾼 경우에만 재배포한다.

```bash
cd ~/worldapex-hosting/my-favorite-watch     # 실제 배포 디렉터리
cp /path/to/repo/hosting/firebase.json .     # 구성 변경 시에만

firebase projects:list                       # my-favorite-watch 가 보이는지 확인
firebase deploy --only hosting --project my-favorite-watch
```

**alias를 쓰지 않는다.** 배포는 항상 Project ID(`my-favorite-watch`)를 명시한다.
과거에 삭제된 프로젝트의 alias(`mfw`)가 `.firebaserc`에 남아 CLI가
`projects/mfw`를 조회하다 403으로 실패한 사례가 있다. `mfw`는 도메인
prefix로만 사용한다.

문제가 생기면 다음을 확인한다.

```bash
cat .firebaserc          # default 가 my-favorite-watch 인지
firebase use             # Active Project 확인
ls firebase-public/      # 비어 있는지 (index.html 이 있으면 삭제)
```

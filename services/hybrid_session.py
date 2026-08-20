"""하이브리드 세션 인터페이스 — 민감 값은 서버, 나머지는 쿠키 (task-2026-08-003).

Flask 의 `session["key"] = value` API 를 쓰는 라우트 코드는 한 줄도 바꾸지
않고, `SessionInterface` 교체만으로 저장 위치를 나눈다.

    쿠키(__session, 서명됨)    : session_id(`_sid`) · device_id · oauth_state ·
                                 code_verifier · _csrf_token 등 비민감 값
    Firestore(server_sessions) : SERVER_SIDE_KEYS (credentials · user_key ·
                                 user · 시트 캐시 · auth_at)

동작
    - `open_session`  : 쿠키를 복호화해 `_sid` 를 꺼내고, Firestore 문서를
      읽어 SERVER_SIDE_KEYS 를 세션에 병합한다. 문서가 없으면(만료·전체
      로그아웃) `_sid` 를 버려 재인증을 요구한다.
    - `save_session`  : `session.modified` 일 때만 Firestore 에 쓴다(전체
      치환). 쿠키에는 서버 측 키를 제거하고 `_sid` 만 남긴다.
    - **폴백**: Firestore 미구성 시 표준 쿠키 세션과 100% 동일하게 동작한다.
      로컬 개발이 그대로 돌고, 배포 직후 구 형식 쿠키(값이 최상위에 직접
      존재)도 계속 읽히며, 세션이 변경되는 다음 요청에서 자연스럽게 신규
      구조로 옮겨진다 — 강제 재로그인이 없다.

쿠키 서명 · SameSite/Secure/HttpOnly 설정은 부모 클래스
(`SecureCookieSessionInterface`)의 것을 그대로 재사용하므로 기존과 동일하다.
"""
import logging

from flask.sessions import SecureCookieSessionInterface

from services import server_session

logger = logging.getLogger(__name__)

# 서버 측에만 보관하는 키 (task-003 §3.2 — 이 프로젝트의 실제 세션 필드명)
SERVER_SIDE_KEYS = frozenset({
    "credentials", "user_key", "user",
    "sheet_id", "sheet_title", "worksheet_name",
    "auth_at",
})

# 쿠키 안에서 session_id 를 담는 키
SESSION_ID_KEY = "_sid"


class HybridSessionInterface(SecureCookieSessionInterface):
    def open_session(self, app, request):
        session = super().open_session(app, request)
        if session is None or not server_session.is_configured():
            return session

        sid = session.get(SESSION_ID_KEY)
        if not sid:
            # 신규 방문이거나 구 형식 쿠키. 그대로 반환하면 구 쿠키의 값도
            # 계속 읽히고, 다음 쓰기에서 save_session 이 신규 구조로 옮긴다.
            return session

        data = server_session.get_session(sid)
        if data is None:
            # 만료 · 로그아웃 · 전체 로그아웃으로 문서가 사라졌다.
            # session_id 를 버려 로그인 필요 라우트가 재인증을 요구하게 한다.
            session.pop(SESSION_ID_KEY, None)  # modified=True → 쿠키도 정리됨
            return session

        session._server_sid = sid
        for key in SERVER_SIDE_KEYS:
            if key in data:
                # CallbackDict 추적을 우회해 병합이 modified 로 잡히지 않게 한다.
                dict.__setitem__(session, key, data[key])
        session.modified = False
        return session

    def save_session(self, app, session, response):
        if not server_session.is_configured():
            return super().save_session(app, session, response)

        sid = getattr(session, "_server_sid", None) or session.get(SESSION_ID_KEY)

        if not session:
            # session.clear() (개별 로그아웃 포함) → 서버 문서도 삭제.
            if sid:
                server_session.delete_session(sid)
            return super().save_session(app, session, response)

        server_payload = {k: session[k] for k in SERVER_SIDE_KEYS if k in session}

        if session.modified:
            if server_payload and not sid:
                sid = server_session.new_session_id()
            if sid and not server_session.save_session(sid, server_payload):
                # 저장 실패 시 이번 요청의 값을 잃지 않도록 쿠키 폴백으로 둔다.
                logger.warning("server session write failed; falling back to cookie")
                return super().save_session(app, session, response)

        if sid:
            # 쿠키에는 서버 측 키를 남기지 않는다. (modified 오염을 피하기
            # 위해 CallbackDict 추적을 우회한다)
            for key in SERVER_SIDE_KEYS:
                dict.pop(session, key, None)
            dict.__setitem__(session, SESSION_ID_KEY, sid)
            session._server_sid = sid

        return super().save_session(app, session, response)

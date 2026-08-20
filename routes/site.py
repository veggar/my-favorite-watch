"""로그인 없이 접근 가능한 공개 리소스.

- `/privacy`, `/terms` (P0-4): 일반 사용자 공개 요건이자 Google OAuth 앱 검증(P0-2)
  제출 시 필수 항목이다. 미인증 상태에서 열려야 하므로 `login_required` 를 붙이지
  않는다.
- `/manifest.webmanifest` (P2-1): 정적 파일로 두면 서버 환경에 따라 MIME 타입이
  달라질 수 있어 라우트로 직접 응답한다. `start_url` 등은 `url_for` 로 만든다.
"""

import logging

from flask import (
    Blueprint, Response, abort, current_app, jsonify, render_template,
    send_from_directory, url_for,
)

from services import policy_history
from services.site_info import policy_context

logger = logging.getLogger(__name__)

site_bp = Blueprint("site", __name__)


@site_bp.route("/privacy")
def privacy():
    ctx = policy_context()
    if not ctx["is_complete"]:
        logger.warning(
            "개인정보처리방침 운영자 정보 미설정: %s",
            ", ".join(m["env"] for m in ctx["missing"]),
        )
    versions = policy_history.list_versions("privacy")
    return render_template("privacy.html", policy=ctx, history_versions=versions)


@site_bp.route("/terms")
def terms():
    ctx = policy_context()
    versions = policy_history.list_versions("terms")
    return render_template("terms.html", policy=ctx, history_versions=versions)


@site_bp.route("/<any(privacy, terms):doc_type>/history")
def policy_history_list(doc_type):
    """이전 버전 목록 (PRD §5.1 "이전 버전 보관"). 콘텐츠 변경 전 스냅샷이
    없으면 빈 목록을 그대로 보여준다 — 최초 버전에는 이전 버전이 없는 것이
    정상이다."""
    versions = policy_history.list_versions(doc_type)
    title = "개인정보처리방침" if doc_type == "privacy" else "이용약관"
    return render_template(
        "legal_history_list.html",
        doc_type=doc_type, title=title, versions=versions,
    )


@site_bp.route("/<any(privacy, terms):doc_type>/history/<slug>")
def policy_history_view(doc_type, slug):
    """특정 시행일의 스냅샷 원문을 그대로 서빙한다."""
    html = policy_history.read_version(doc_type, slug)
    if html is None:
        abort(404)
    return Response(html, mimetype="text/html")


@site_bp.route("/favicon.ico")
def favicon():
    """브라우저는 <link> 태그와 무관하게 루트의 /favicon.ico 를 요청한다."""
    return send_from_directory(
        current_app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


@site_bp.route("/manifest.webmanifest")
def manifest():
    resp = jsonify({
        "name": "My Favorite Watch",
        "short_name": "MFW",
        "description": "나의 영상 작품 기록 관리",
        "lang": "ko",
        "dir": "ltr",
        "start_url": url_for("main.index"),
        "scope": "/",
        "id": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f9fafb",
        "theme_color": "#4f46e5",
        "icons": [
            {
                "src": url_for("static", filename="icons/icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": url_for("static", filename="icons/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": url_for("static", filename="icons/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    })
    resp.mimetype = "application/manifest+json"
    # 아이콘·이름 변경이 즉시 반영되지 않아도 되므로 짧게 캐시한다.
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

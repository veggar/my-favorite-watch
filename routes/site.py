"""로그인 없이 접근 가능한 공개 리소스.

- `/privacy`, `/terms` (P0-4): 일반 사용자 공개 요건이자 Google OAuth 앱 검증(P0-2)
  제출 시 필수 항목이다. 미인증 상태에서 열려야 하므로 `login_required` 를 붙이지
  않는다.
- `/manifest.webmanifest` (P2-1): 정적 파일로 두면 서버 환경에 따라 MIME 타입이
  달라질 수 있어 라우트로 직접 응답한다. `start_url` 등은 `url_for` 로 만든다.
"""

import logging

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory, url_for

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
    return render_template("privacy.html", policy=ctx)


@site_bp.route("/terms")
def terms():
    ctx = policy_context()
    return render_template("terms.html", policy=ctx)


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

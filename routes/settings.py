import logging

from flask import Blueprint, render_template, request, session, redirect, url_for
from routes.auth import sheet_required, get_credentials
from services import tmdb as tmdb_service
from services.errors import friendly_error
from services.firestore_session import clear_user_sheet
from services.google_sheets import rename_spreadsheet, rename_worksheet, DEFAULT_WORKSHEET_NAME

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)

SORT_OPTIONS_LABELS = {
    "registered_desc": "최근 등록일순",
    "registered_asc": "오래된 등록일순",
    "updated_desc": "최근 수정일순",
    "title_asc": "제목 오름차순",
    "title_desc": "제목 내림차순",
    "watched_desc": "관람일 최신순",
    "rating_desc": "평점 높은순",
    "rating_asc": "평점 낮은순",
}


@settings_bp.route("/settings", methods=["GET", "POST"])
@sheet_required
def settings():
    error = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_defaults":
            session["default_sort"] = request.form.get("default_sort", "registered_desc")
            session["default_category"] = request.form.get("default_category", "전체")
            session["default_watched"] = request.form.get("default_watched", "all")
        elif action == "disconnect_sheet":
            session.pop("sheet_id", None)
            session.pop("sheet_title", None)
            session.pop("worksheet_name", None)
            # 사용자 문서도 비워야 다음 자동 복원에서 다시 연결되지 않는다.
            clear_user_sheet(session.get("user_key", ""))
            return redirect(url_for("sheet.connect"))
        elif action == "rename_doc":
            new_title = request.form.get("new_doc_title", "").strip()
            if new_title:
                try:
                    credentials = get_credentials()
                    rename_spreadsheet(credentials, session["sheet_id"], new_title)
                    session["sheet_title"] = new_title
                except Exception as e:
                    error = friendly_error(e, "문서 이름을 변경하지 못했습니다",
                                           context="rename_doc", log=logger)
        elif action == "rename_worksheet":
            new_ws = request.form.get("new_worksheet_name", "").strip()
            if new_ws:
                try:
                    credentials = get_credentials()
                    old_ws = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
                    rename_worksheet(credentials, session["sheet_id"], old_ws, new_ws)
                    session["worksheet_name"] = new_ws
                except Exception as e:
                    error = friendly_error(e, "워크시트 이름을 변경하지 못했습니다",
                                           context="rename_worksheet", log=logger)
        if not error:
            return redirect(url_for("settings.settings"))

    return render_template(
        "settings.html",
        user=session.get("user"),
        sheet_title=session.get("sheet_title", ""),
        sheet_id=session.get("sheet_id", ""),
        worksheet_name=session.get("worksheet_name", DEFAULT_WORKSHEET_NAME),
        default_sort=session.get("default_sort", "registered_desc"),
        default_category=session.get("default_category", "전체"),
        default_watched=session.get("default_watched", "all"),
        sort_options=SORT_OPTIONS_LABELS,
        categories=["전체", "영화", "드라마", "다큐", "애니", "기타"],
        # TMDB_API_KEY 미설정 시 자동 보강이 조용히 건너뛰어지므로,
        # 사용자가 원인을 알 수 있도록 상태를 노출한다 (P1-7).
        tmdb_enabled=bool(tmdb_service.TMDB_API_KEY),
        error=error,
    )

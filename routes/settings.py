from flask import Blueprint, render_template, request, session, redirect, url_for
from routes.auth import sheet_required

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
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_defaults":
            session["default_sort"] = request.form.get("default_sort", "registered_desc")
            session["default_category"] = request.form.get("default_category", "전체")
            session["default_watched"] = request.form.get("default_watched", "all")
        elif action == "disconnect_sheet":
            session.pop("sheet_id", None)
            session.pop("sheet_title", None)
            return redirect(url_for("sheet.connect"))
        return redirect(url_for("settings.settings"))

    return render_template(
        "settings.html",
        user=session.get("user"),
        sheet_title=session.get("sheet_title", ""),
        sheet_id=session.get("sheet_id", ""),
        default_sort=session.get("default_sort", "registered_desc"),
        default_category=session.get("default_category", "전체"),
        default_watched=session.get("default_watched", "all"),
        sort_options=SORT_OPTIONS_LABELS,
        categories=["전체", "영화", "드라마", "다큐", "애니", "기타"],
    )

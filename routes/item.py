from flask import Blueprint, request, session, redirect, url_for, jsonify
from routes.auth import sheet_required, get_credentials
from services.google_sheets import append_item, update_item, delete_item, update_watched
from services.tmdb import fetch_title_info

item_bp = Blueprint("item", __name__)


def _parse_form(form):
    watched = form.get("watched") == "true"
    rating = form.get("rating", "").strip()
    official_rating = form.get("officialRating", "").strip()
    return {
        "title": form.get("title", "").strip(),
        "category": form.get("category", "").strip(),
        "genre": form.get("genre", "").strip(),
        "watched": watched,
        "rating": rating,
        "officialRating": official_rating,
        "watchedAt": form.get("watchedAt", "").strip() if watched else "",
        "review": form.get("review", "").strip(),
        "synopsis": form.get("synopsis", "").strip(),
        "titleLink": form.get("titleLink", "").strip(),
    }


@item_bp.route("/item/create", methods=["POST"])
@sheet_required
def create():
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    data = _parse_form(request.form)

    # titleLink가 없으면 TMDb 자동 검색
    if not data["titleLink"] and data["title"]:
        tmdb = fetch_title_info(data["title"], data.get("category", ""))
        data["titleLink"] = tmdb.get("titleLink", "")
        if not data["officialRating"]:
            data["officialRating"] = tmdb.get("officialRating", "")

    append_item(credentials, sheet_id, data)
    return redirect(url_for("main.index"))


@item_bp.route("/item/<item_id>/update", methods=["POST"])
@sheet_required
def update(item_id):
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    data = _parse_form(request.form)

    # title 변경 + titleLink 재검색 요청 시
    if request.form.get("refresh_link") == "true" and data["title"]:
        tmdb = fetch_title_info(data["title"], data.get("category", ""))
        data["titleLink"] = tmdb.get("titleLink", "") or data["titleLink"]
        if not data["officialRating"]:
            data["officialRating"] = tmdb.get("officialRating", "")

    update_item(credentials, sheet_id, item_id, data)
    return redirect(url_for("main.index"))


@item_bp.route("/item/<item_id>/delete", methods=["POST"])
@sheet_required
def delete(item_id):
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    delete_item(credentials, sheet_id, item_id)
    return redirect(url_for("main.index"))


@item_bp.route("/item/<item_id>/toggle-watched", methods=["POST"])
@sheet_required
def toggle_watched(item_id):
    """관람 여부 토글 (AJAX용)."""
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    data = request.get_json(silent=True) or {}
    watched = bool(data.get("watched", False))
    success = update_watched(credentials, sheet_id, item_id, watched)
    return jsonify({"ok": success})


@item_bp.route("/item/tmdb-search", methods=["GET"])
@sheet_required
def tmdb_search():
    """TMDb 검색 결과 미리보기 (AJAX용)."""
    title = request.args.get("title", "").strip()
    category = request.args.get("category", "").strip()
    if not title:
        return jsonify({"titleLink": "", "officialRating": ""})
    result = fetch_title_info(title, category)
    return jsonify(result)

from flask import Blueprint, request, session, redirect, url_for, jsonify
from routes.auth import sheet_required, get_credentials
from services.google_sheets import append_item, update_item, delete_item, update_watched, DEFAULT_WORKSHEET_NAME
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
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
    data = _parse_form(request.form)

    if not data["titleLink"] and data["title"]:
        tmdb = fetch_title_info(data["title"], data.get("category", ""))
        data["titleLink"] = tmdb.get("titleLink", "")
        if not data["officialRating"]:
            data["officialRating"] = tmdb.get("officialRating", "")

    append_item(credentials, sheet_id, data, worksheet_name)
    return redirect(url_for("main.index"))


@item_bp.route("/item/<item_id>/update", methods=["POST"])
@sheet_required
def update(item_id):
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
    data = _parse_form(request.form)

    if request.form.get("refresh_link") == "true" and data["title"]:
        tmdb = fetch_title_info(data["title"], data.get("category", ""))
        data["titleLink"] = tmdb.get("titleLink", "") or data["titleLink"]
        if not data["officialRating"]:
            data["officialRating"] = tmdb.get("officialRating", "")

    update_item(credentials, sheet_id, item_id, data, worksheet_name)
    return redirect(url_for("main.index"))


@item_bp.route("/item/<item_id>/delete", methods=["POST"])
@sheet_required
def delete(item_id):
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
    delete_item(credentials, sheet_id, item_id, worksheet_name)
    return redirect(url_for("main.index"))


@item_bp.route("/item/<item_id>/toggle-watched", methods=["POST"])
@sheet_required
def toggle_watched(item_id):
    """관람 여부 토글 (AJAX용)."""
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
    data = request.get_json(silent=True) or {}
    watched = bool(data.get("watched", False))
    success = update_watched(credentials, sheet_id, item_id, watched, worksheet_name)
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


@item_bp.route("/item/<item_id>/tmdb-update", methods=["POST"])
@sheet_required
def tmdb_update(item_id):
    """기존 항목의 titleLink / officialRating을 TMDb로 덮어쓰기 (AJAX용)."""
    from services.google_sheets import get_all_items
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)

    # 해당 항목 조회
    all_items = get_all_items(credentials, sheet_id, worksheet_name)
    item = next((it for it in all_items if it.get("id") == item_id), None)
    if not item:
        return jsonify({"ok": False, "error": "항목을 찾을 수 없습니다."})

    result = fetch_title_info(item.get("title", ""), item.get("category", ""))
    if not result.get("titleLink") and not result.get("officialRating"):
        return jsonify({"ok": False, "error": "TMDb에서 작품을 찾지 못했습니다."})

    # 업데이트할 데이터 구성
    data = dict(item)
    data["watched"] = item.get("watched", "").lower() == "true"
    if result.get("titleLink"):
        data["titleLink"] = result["titleLink"]
    if result.get("officialRating"):
        data["officialRating"] = result["officialRating"]

    update_item(credentials, sheet_id, item_id, data, worksheet_name)
    return jsonify({
        "ok": True,
        "titleLink": data.get("titleLink", ""),
        "officialRating": data.get("officialRating", ""),
    })

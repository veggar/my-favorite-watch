from flask import Blueprint, request, session, redirect, url_for, jsonify
from routes.auth import sheet_required, get_credentials
from services.google_sheets import append_item, update_item, delete_item, restore_item, update_watched, DEFAULT_WORKSHEET_NAME
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
        "originalTitle": form.get("originalTitle", "").strip(),
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

    # Optimistic locking: 폼 제출 시점의 updatedAt과 현재 시트 값 비교
    original_updated_at = request.form.get("original_updated_at", "").strip()
    if original_updated_at:
        from services.google_sheets import get_item_by_id
        current = get_item_by_id(credentials, sheet_id, item_id, worksheet_name)
        if current and current.get("updatedAt", "").strip() != original_updated_at:
            from flask import flash
            flash("다른 곳에서 먼저 수정되었습니다. 최신 내용을 확인 후 다시 시도해주세요.", "error")
            return redirect(url_for("main.index"))

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


@item_bp.route("/item/<item_id>/restore", methods=["POST"])
@sheet_required
def restore(item_id):
    """삭제된 항목을 원래 워크시트로 복구."""
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
    success = restore_item(credentials, sheet_id, item_id, worksheet_name)
    if not success:
        return jsonify({"ok": False, "error": "항목을 찾을 수 없습니다."}), 404
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


@item_bp.route("/item/tmdb-status", methods=["GET"])
@sheet_required
def tmdb_status():
    """TMDb 보강 상태 조회 (AJAX용)."""
    from services.tmdb_tracker import get_statuses
    ids = [i for i in request.args.get("ids", "").split(",") if i]
    return jsonify(get_statuses(ids))


@item_bp.route("/item/tmdb-enrich-chunk", methods=["POST"])
@sheet_required
def tmdb_enrich_chunk():
    """대기 중인 항목 중 일부를 **이 요청 안에서 동기적으로** 보강한다.

    백그라운드 스레드를 쓰지 않으므로 Cloud Run 이 응답 후 CPU 를
    스로틀링해도 작업이 유실되지 않는다. 브라우저가 done=false 인 동안
    반복 호출하여 전체를 완료시킨다. 진행 상태는 Firestore 에 남으므로
    페이지를 새로고침하거나 다른 워커/인스턴스로 라우팅되어도 이어진다.
    """
    from services.google_sheets import get_all_items
    from services.tmdb import enrich_items_chunk, ENRICH_CHUNK_SIZE
    from services.tmdb_tracker import set_statuses, clear

    remaining = [i for i in session.get("tmdb_pending_ids", []) if i]
    if not remaining:
        return jsonify({"ok": True, "done": True, "remaining": 0, "statuses": {}})

    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)

    target_ids = remaining[:ENRICH_CHUNK_SIZE]
    target_set = set(target_ids)

    all_items = get_all_items(credentials, sheet_id, worksheet_name)
    targets = [it for it in all_items if it.get("id") in target_set]

    # 시트에서 사라진 id(삭제 등)는 대기열에서 제거한다.
    missing = [i for i in target_ids if i not in {it.get("id") for it in targets}]
    if missing:
        clear(missing)

    statuses = enrich_items_chunk(credentials, sheet_id, worksheet_name, targets)
    if statuses:
        set_statuses({k: v for k, v in statuses.items() if v})

    rest = remaining[len(target_ids):]
    if rest:
        session["tmdb_pending_ids"] = rest
    else:
        session.pop("tmdb_pending_ids", None)

    return jsonify({
        "ok": True,
        "done": not rest,
        "processed": len(target_ids),
        "remaining": len(rest),
        "statuses": statuses,
    })


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
    if result.get("originalTitle"):
        data["originalTitle"] = result["originalTitle"]

    update_item(credentials, sheet_id, item_id, data, worksheet_name)
    return jsonify({
        "ok": True,
        "titleLink": data.get("titleLink", ""),
        "officialRating": data.get("officialRating", ""),
        "originalTitle": data.get("originalTitle", ""),
    })

import logging

from flask import Blueprint, render_template, request, session
from routes.auth import sheet_required, get_credentials
from services.errors import friendly_error
from services.google_sheets import get_all_items, get_deleted_items, DEFAULT_WORKSHEET_NAME

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)

SORT_OPTIONS = {
    "registered_desc": ("최근 등록일순", lambda x: x.get("registeredAt", ""), True),
    "registered_asc": ("오래된 등록일순", lambda x: x.get("registeredAt", ""), False),
    "updated_desc": ("최근 수정일순", lambda x: x.get("updatedAt", ""), True),
    "title_asc": ("제목 오름차순", lambda x: x.get("title", "").lower(), False),
    "title_desc": ("제목 내림차순", lambda x: x.get("title", "").lower(), True),
    "watched_desc": ("관람일 최신순", lambda x: x.get("watchedAt", ""), True),
    "rating_desc": ("평점 높은순", lambda x: float(x.get("rating") or 0), True),
    "rating_asc": ("평점 낮은순", lambda x: float(x.get("rating") or 0), False),
}


def _apply_filters_and_sort(items, query, scope, category_filter, watched_filter, sort_key):
    # 검색
    if query:
        q = query.lower()
        if scope == "all":
            fields = ["title", "genre", "review", "synopsis"]
        else:
            fields = ["title"]
        items = [
            it for it in items
            if any(q in (it.get(f) or "").lower() for f in fields)
        ]

    # 카테고리 필터
    if category_filter and category_filter != "전체":
        items = [it for it in items if it.get("category") == category_filter]

    # 관람 여부 필터
    if watched_filter == "watched":
        items = [it for it in items if it.get("watched", "").lower() == "true"]
    elif watched_filter == "want":
        items = [it for it in items if it.get("watched", "").lower() != "true"]

    # 정렬
    sort_info = SORT_OPTIONS.get(sort_key, SORT_OPTIONS["registered_desc"])
    key_fn = sort_info[1]
    reverse = sort_info[2]
    items = sorted(items, key=key_fn, reverse=reverse)

    return items


PAGE_SIZE = 50  # 한 페이지에 보여줄 최대 항목 수


@main_bp.route("/")
@sheet_required
def index():
    credentials = get_credentials()
    sheet_id = session.get("sheet_id")
    worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)
    tab = request.args.get("tab", "active")
    if tab not in ("active", "deleted"):
        tab = "active"

    offset = max(0, request.args.get("offset", 0, type=int))

    load_error = None
    if tab == "deleted":
        try:
            deleted_items = get_deleted_items(credentials, sheet_id)
        except Exception as e:
            deleted_items = []
            load_error = friendly_error(e, "삭제 목록을 불러오지 못했습니다",
                                        context="get_deleted_items", log=logger)
        page_items = deleted_items[offset: offset + PAGE_SIZE]
        return render_template(
            "list.html",
            items=page_items,
            total=len(deleted_items),
            filtered_count=len(deleted_items),
            tab=tab,
            offset=offset,
            page_size=PAGE_SIZE,
            user=session.get("user"),
            sheet_title=session.get("sheet_title", ""),
            query="", scope="title",
            category_filter="전체", watched_filter="all",
            sort_key="registered_desc",
            sort_options=SORT_OPTIONS,
            load_error=load_error,
            categories=["전체", "영화", "드라마", "다큐", "애니", "기타"],
            import_success=None,
            tmdb_pending_ids=[],
        )

    try:
        items = get_all_items(credentials, sheet_id, worksheet_name)
    except Exception as e:
        items = []
        load_error = friendly_error(e, "목록을 불러오지 못했습니다",
                                    context="get_all_items", log=logger)

    query = request.args.get("q", "").strip()
    scope = request.args.get("scope", "title")
    category_filter = request.args.get("category", "전체")
    watched_filter = request.args.get("watched", "all")
    sort_key = request.args.get("sort", session.get("default_sort", "registered_desc"))

    filtered = _apply_filters_and_sort(items, query, scope, category_filter, watched_filter, sort_key)

    # 페이지네이션
    page_items = filtered[offset: offset + PAGE_SIZE]

    import_success = session.pop("import_success", None)
    # 대기열은 pop 하지 않는다. 청크 보강이 완료될 때까지 세션에 남겨 두어야
    # 새로고침하거나 도중에 중단해도 이어서 처리할 수 있다.
    # (완료 시 item.tmdb_enrich_chunk 가 제거한다)
    tmdb_pending_ids = session.get("tmdb_pending_ids", [])

    return render_template(
        "list.html",
        items=page_items,
        total=len(items),
        filtered_count=len(filtered),
        tab=tab,
        offset=offset,
        page_size=PAGE_SIZE,
        user=session.get("user"),
        sheet_title=session.get("sheet_title", ""),
        query=query,
        scope=scope,
        category_filter=category_filter,
        watched_filter=watched_filter,
        sort_key=sort_key,
        sort_options=SORT_OPTIONS,
        load_error=load_error,
        categories=["전체", "영화", "드라마", "다큐", "애니", "기타"],
        import_success=import_success,
        tmdb_pending_ids=tmdb_pending_ids,
    )

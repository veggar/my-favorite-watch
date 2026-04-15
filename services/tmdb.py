import os
import time
import requests

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"


def _search(title: str, media_type: str) -> dict | None:
    """TMDb에서 title로 작품 검색. 첫 번째 결과 반환."""
    if not TMDB_API_KEY:
        return None
    try:
        resp = requests.get(
            f"{TMDB_BASE}/search/{media_type}",
            params={"api_key": TMDB_API_KEY, "query": title, "language": "ko-KR"},
            timeout=3,
        )
        data = resp.json()
        results = data.get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def fetch_title_info(title: str, category: str = "") -> dict:
    """
    작품 제목으로 TMDb에서 링크, 공식 평점, 원제를 조회.
    반환: {"titleLink": str, "officialRating": str, "originalTitle": str}
    """
    result = {"titleLink": "", "officialRating": "", "originalTitle": ""}

    if not TMDB_API_KEY:
        return result

    # category에 따라 검색 순서 결정
    if category in ("드라마",):
        order = ["tv", "movie"]
    else:
        order = ["movie", "tv"]

    found = None
    media_type_found = None
    for mt in order:
        found = _search(title, mt)
        if found:
            media_type_found = mt
            break

    if not found:
        return result

    tmdb_id = found.get("id")
    if media_type_found and tmdb_id:
        result["titleLink"] = f"https://www.themoviedb.org/{media_type_found}/{tmdb_id}"
        vote = found.get("vote_average")
        if vote is not None:
            result["officialRating"] = f"{vote:.1f}"
        # TV는 original_name, 영화는 original_title
        orig = found.get("original_name") or found.get("original_title") or ""
        result["originalTitle"] = orig

    return result


def enrich_item(item: dict) -> bool:
    """
    단일 항목의 빈 titleLink / officialRating / originalTitle을 TMDb로 채움.
    변경된 필드가 있으면 True 반환.
    """
    if not TMDB_API_KEY:
        return False
    need_link = not item.get("titleLink")
    need_rating = not item.get("officialRating")
    need_orig = not item.get("originalTitle")
    if not need_link and not need_rating and not need_orig:
        return False

    result = fetch_title_info(item.get("title", ""), item.get("category", ""))
    changed = False
    if need_link and result.get("titleLink"):
        item["titleLink"] = result["titleLink"]
        changed = True
    if need_rating and result.get("officialRating"):
        item["officialRating"] = result["officialRating"]
        changed = True
    if need_orig and result.get("originalTitle"):
        item["originalTitle"] = result["originalTitle"]
        changed = True
    return changed


def enrich_items_background(creds_data: dict, sheet_id: str, worksheet_name: str,
                             items: list[dict]) -> None:
    """
    백그라운드 스레드용: items를 TMDb로 보강 후 시트 업데이트.
    creds_data: session["credentials"] 딕셔너리 (스레드에서 세션 접근 불가)
    """
    from services.tmdb_tracker import set_status, clear
    from services.google_sheets import update_item
    from google.oauth2.credentials import Credentials
    import google.auth.transport.requests

    if not TMDB_API_KEY:
        clear([item["id"] for item in items if item.get("id")])
        return

    try:
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
    except Exception:
        for item in items:
            if item.get("id"):
                set_status(item["id"], "not_found")
        return

    for i, item in enumerate(items):
        item_id = item.get("id")
        if not item_id:
            continue
        if i > 0:
            time.sleep(0.1)
        set_status(item_id, "searching")
        try:
            changed = enrich_item(item)
            if changed:
                data = dict(item)
                watched_val = data.get("watched", False)
                data["watched"] = watched_val is True or str(watched_val).lower() == "true"
                update_item(creds, sheet_id, item_id, data, worksheet_name)
            set_status(item_id, "done" if changed else "not_found")
        except Exception:
            set_status(item_id, "not_found")


def enrich_items_batch(items: list[dict], rate_limit_sec: float = 0.1) -> int:
    """
    여러 항목을 TMDb로 일괄 보강 (in-place 수정).
    변경된 항목 수 반환. TMDb 키 없으면 즉시 0 반환.
    """
    if not TMDB_API_KEY:
        return 0
    updated = 0
    for i, item in enumerate(items):
        if i > 0:
            time.sleep(rate_limit_sec)
        if enrich_item(item):
            updated += 1
    return updated

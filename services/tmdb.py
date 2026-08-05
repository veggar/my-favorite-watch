import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

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


# 한 요청에서 동기 처리할 항목 수.
# 요청 수명 안에서 끝내야 하므로(Cloud Run CPU 스로틀링 회피) gunicorn
# --timeout 안에 확실히 들어오는 크기로 제한한다.
ENRICH_CHUNK_SIZE = int(os.environ.get("TMDB_ENRICH_CHUNK", "15"))


def enrich_items_chunk(creds, sheet_id: str, worksheet_name: str,
                       items: list[dict], rate_limit_sec: float = 0.1) -> dict[str, str]:
    """items 를 **요청 수명 안에서 동기적으로** 보강하고 시트에 반영한다.

    백그라운드 데몬 스레드를 쓰지 않으므로 Cloud Run 이 응답 후 CPU 를
    스로틀링해도 작업이 중단되지 않는다(계획서 P0-3 원인 2).
    호출부는 ENRICH_CHUNK_SIZE 단위로 나눠 반복 호출한다.

    반환: {item_id: "done" | "not_found"}
    """
    from services.google_sheets import update_item

    statuses: dict[str, str] = {}
    if not items:
        return statuses

    if not TMDB_API_KEY:
        # TMDb 미설정 시 보강 대상이 아니므로 대기 상태를 남기지 않는다.
        return {item["id"]: "" for item in items if item.get("id")}

    for i, item in enumerate(items):
        item_id = item.get("id")
        if not item_id:
            continue
        if i > 0:
            time.sleep(rate_limit_sec)
        try:
            changed = enrich_item(item)
            if changed:
                data = dict(item)
                watched_val = data.get("watched", False)
                data["watched"] = watched_val is True or str(watched_val).lower() == "true"
                update_item(creds, sheet_id, item_id, data, worksheet_name)
            statuses[item_id] = "done" if changed else "not_found"
        except Exception:
            logger.warning("TMDb 보강 실패 (item_id=%s)", item_id, exc_info=True)
            statuses[item_id] = "not_found"

    return statuses


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

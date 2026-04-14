import os
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
            timeout=5,
        )
        data = resp.json()
        results = data.get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def fetch_title_info(title: str, category: str = "") -> dict:
    """
    작품 제목으로 TMDb에서 링크와 공식 평점을 조회.
    반환: {"titleLink": str, "officialRating": str}
    """
    result = {"titleLink": "", "officialRating": ""}

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

    return result

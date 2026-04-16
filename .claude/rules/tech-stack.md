# Technical Stack Guidelines

## Rendering Strategy
* Prefer Server-Side Rendering (SSR) using Flask and Jinja2 unless stated otherwise.

## Google Sheets API (v4)
* **Batch Operations:** Use batch updates for CSV/Sheet imports to minimize API calls.
* **Soft Delete:** Move deleted rows to the `삭제` worksheet with a `deletedAt` timestamp.

## TMDb Integration Logic
* **Search Priority:** * Category '드라마': Search TV first, then Movie.
    * Other Categories: Search Movie first, then TV.
* **Rate Limiting:** Maintain a 0.1s delay between items during batch processing (40 req/10s limit).
* **Status Tracking:** Use `services/tmdb_tracker.py` to manage `pending/searching/done/not_found` states.

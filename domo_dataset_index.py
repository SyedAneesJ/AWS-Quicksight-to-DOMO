import os
import time
from typing import Dict, List, Any

import requests

from domo_auth import get_domo_access_token

DATASET_INDEX_TTL_SECONDS = int(os.environ.get("DATASET_INDEX_TTL_SECONDS", "300"))
DATASET_INDEX_MAX = int(os.environ.get("DATASET_INDEX_MAX", "15000"))
DATASET_INDEX_PAGE_SIZE = int(os.environ.get("DATASET_INDEX_PAGE_SIZE", "50"))

_CACHE: Dict[str, Any] = {
    "data": [],
    "fetched_at": 0.0
}


def _get_domo_token() -> str:
    client_id = os.environ.get("DOMO_CLIENT_ID")
    client_secret = os.environ.get("DOMO_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("DOMO_CLIENT_ID and DOMO_CLIENT_SECRET must be set")
    return get_domo_access_token(client_id, client_secret)


def _fetch_dataset_page(token: str, limit: int, offset: int) -> List[Dict[str, Any]]:
    url = f"https://api.domo.com/v1/datasets?limit={limit}&offset={offset}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Domo dataset list failed: {resp.status_code} {resp.text}")
    payload = resp.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("data") or payload.get("datasets") or []
    return []


def _normalize_dataset(ds: Dict[str, Any]) -> Dict[str, str]:
    ds_id = ds.get("id") or ds.get("dataSourceId") or ds.get("datasetId")
    name = ds.get("name") or ds.get("displayName") or ds.get("title") or "Unnamed Dataset"
    return {"id": ds_id, "name": name}


def _build_index() -> List[Dict[str, str]]:
    token = _get_domo_token()
    limit = max(1, min(DATASET_INDEX_PAGE_SIZE, 500))
    max_items = max(1, DATASET_INDEX_MAX)

    results: List[Dict[str, str]] = []
    offset = 0

    while len(results) < max_items:
        page = _fetch_dataset_page(token, limit, offset)
        if not page:
            break
        for ds in page:
            normalized = _normalize_dataset(ds)
            if normalized.get("id"):
                results.append(normalized)
                if len(results) >= max_items:
                    break
        if len(page) < limit:
            break
        offset += limit

    return results


def _is_cache_fresh() -> bool:
    fetched_at = _CACHE.get("fetched_at", 0.0)
    return (time.time() - fetched_at) <= DATASET_INDEX_TTL_SECONDS


def get_domo_dataset_index(force_refresh: bool = False) -> List[Dict[str, str]]:
    if not force_refresh and _CACHE.get("data") and _is_cache_fresh():
        return _CACHE["data"]

    data = _build_index()
    _CACHE["data"] = data
    _CACHE["fetched_at"] = time.time()
    return data


def search_domo_datasets(query: str, limit: int | None = None) -> List[Dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []

    max_limit = None if limit is None else max(1, int(limit))
    data = get_domo_dataset_index(force_refresh=False)
    q = query.lower()

    results = [ds for ds in data if q in (ds.get("name") or "").lower()]
    return results if max_limit is None else results[:max_limit]


def refresh_domo_dataset_index() -> List[Dict[str, str]]:
    return get_domo_dataset_index(force_refresh=True)


def get_domo_dataset_index_status() -> Dict[str, Any]:
    return {
        "fetched_at": _CACHE.get("fetched_at", 0.0),
        "ttl_seconds": DATASET_INDEX_TTL_SECONDS,
        "count": len(_CACHE.get("data") or [])
    }

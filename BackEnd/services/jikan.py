import threading
import time

import requests


BASE_URL = "https://api.jikan.moe/v4"

TIMEOUT = 5
MAX_ATTEMPTS = 2
CACHE_TTL = 300
_cache = {}
_cache_lock = threading.Lock()


def _cache_key(path, params):
    return path, tuple(sorted((params or {}).items()))


def _cached(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < CACHE_TTL:
            return entry[1]
    return None


def _store(key, data):
    with _cache_lock:
        _cache[key] = (time.monotonic(), data)


def _stale(key):
    with _cache_lock:
        entry = _cache.get(key)
        return entry[1] if entry else None


def _request(path, params=None):
    key = _cache_key(path, params)
    cached = _cached(key)
    if cached is not None:
        return cached, None

    last_error = "No se pudo consultar la API externa"
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.get(
                f"{BASE_URL}{path}",
                params=params,
                timeout=TIMEOUT
            )

            if response.status_code == 429:
                last_error = "Jikan alcanzó temporalmente su límite de solicitudes"
            elif response.status_code >= 500:
                last_error = "Jikan no está disponible temporalmente"
            else:
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    return None, "La API externa devolvió una respuesta inválida"
                _store(key, data)
                return data, None
        except requests.exceptions.Timeout:
            last_error = "La API externa tardó demasiado en responder"
        except ValueError:
            return None, "La API externa devolvió JSON inválido"
        except requests.exceptions.RequestException as error:
            print(f"Error Jikan: {error}")
            last_error = "No se pudo consultar la API externa"

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(0.4 * (2 ** attempt))

    stale = _stale(key)
    if stale is not None:
        return stale, None
    return None, last_error


def search_anime(query, page=1, limit=12):
    data, error = _request(
        "/anime",
        {
            "q": query,
            "page": page,
            "limit": limit,
            "sfw": "true"
        }
    )

    if error:
        return None, error

    return data, None


def get_anime(anime_id):
    data, error = _request(
        f"/anime/{anime_id}/full"
    )

    if error:
        return None, error

    return data, None


def get_top_anime(page=1, limit=12):
    data, error = _request(
        "/top/anime",
        {
            "page": page,
            "limit": limit
        }
    )

    if error:
        return None, error

    return data, None


def get_genres():
    data, error = _request(
        "/genres/anime"
    )

    if error:
        return None, error

    return data, None


def get_season_now(page=1, limit=12):
    data, error = _request(
        "/seasons/now",
        {
            "page": page,
            "limit": limit
        }
    )

    if error:
        return None, error

    return data, None
import requests


BASE_URL = "https://api.jikan.moe/v4"

TIMEOUT = 10


def _request(path, params=None):
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 429:
            return None, "Jikan alcanzó temporalmente su límite de solicitudes"

        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            return None, "La API externa devolvió una respuesta inválida"

        return data, None

    except requests.exceptions.Timeout:
        return None, "La API externa tardó demasiado en responder"

    except ValueError:
        return None, "La API externa devolvió JSON inválido"

    except requests.exceptions.RequestException as error:
        print(f"Error Jikan: {error}")

        return None, "No se pudo consultar la API externa"


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
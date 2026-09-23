from config.sqlserver import get_connection


def _anime(row):
    return {
        "mal_id": int(row.anime_id) if row.anime_id is not None else None,
        "title": row.title,
        "title_english": row.title_english,
        "images": {"jpg": {"image_url": row.image_url}} if row.image_url else {},
        "type": row.type,
        "source": row.source,
        "episodes": int(row.episodes) if row.episodes is not None else None,
        "status": row.status,
        "score": float(row.score) if row.score is not None else None,
        "rank": float(row.rank) if row.rank is not None else None,
        "popularity": int(row.popularity) if row.popularity is not None else None,
        "synopsis": None
    }


def _query(sql, *parameters):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, *parameters)
        rows = cursor.fetchall()
        cursor.close()
        return [_anime(row) for row in rows]
    finally:
        connection.close()


def top_anime(page=1, limit=12):
    offset = (page - 1) * limit
    items = _query(
        f"""
        SELECT anime_id, title, title_english, image_url, type, source,
               episodes, status, score, rank, popularity
        FROM Animes
        ORDER BY popularity ASC, score DESC
        OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """
    )
    return {"data": items, "pagination": {"last_visible_page": page, "has_next_page": bool(items)}}


def search_anime(query, page=1, limit=12):
    offset = (page - 1) * limit
    items = _query(
        f"""
        SELECT anime_id, title, title_english, image_url, type, source,
               episodes, status, score, rank, popularity
        FROM Animes
        WHERE title LIKE ? OR title_english LIKE ?
        ORDER BY score DESC, popularity ASC
        OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """,
        f"%{query}%",
        f"%{query}%"
    )
    return {"data": items, "pagination": {"last_visible_page": page, "has_next_page": bool(items)}}


def anime_detail(anime_id):
    items = _query(
        """
        SELECT anime_id, title, title_english, image_url, type, source,
               episodes, status, score, rank, popularity
        FROM Animes
        WHERE anime_id = ?
        """,
        anime_id
    )
    return {"data": items[0]} if items else None


def anime_titles(anime_ids):
    if not anime_ids:
        return {}

    placeholders = ",".join("?" for _ in anime_ids)
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT anime_id, title, title_english
            FROM Animes
            WHERE anime_id IN ({placeholders})
            """,
            *anime_ids
        )
        titles = {
            int(row.anime_id): row.title_english or row.title
            for row in cursor.fetchall()
        }
        cursor.close()
        return titles
    finally:
        connection.close()

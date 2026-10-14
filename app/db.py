"""MySQL access. One short-lived connection per request keeps things simple and safe."""

from __future__ import annotations

from contextlib import contextmanager

import pymysql

from .config import DB


@contextmanager
def connection():
    conn = pymysql.connect(
        host=DB.host,
        port=DB.port,
        user=DB.user,
        password=DB.password,
        database=DB.name,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=120,
    )
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple | list = ()) -> list[dict]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())

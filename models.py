import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    uid TEXT PRIMARY KEY,
    calendar_path TEXT NOT NULL,      -- 例如 RES/M1_RES
    course_key TEXT NOT NULL,         -- 课程分组键，例如 UM4IN002-RTEL
    session_type TEXT NOT NULL,       -- 具体场次/分组标签，例如 TD2 / CS / TME1
    summary TEXT NOT NULL,            -- 原始标题
    location TEXT,
    description TEXT,
    dtstart TEXT NOT NULL,            -- ISO8601
    dtend TEXT NOT NULL,              -- ISO8601
    ical_raw TEXT NOT NULL,           -- 原始 VEVENT 文本，直接复用避免时区手工处理
    last_synced TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS selection (
    course_key TEXT NOT NULL,
    session_type TEXT NOT NULL,
    PRIMARY KEY (course_key, session_type)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def replace_events(events: list[dict]):
    """全量覆盖式写入本次同步抓到的事件（course_key/session_type 已在 caldav_client 中解析好）"""
    with get_conn() as conn:
        conn.execute("DELETE FROM events")
        conn.executemany(
            """INSERT INTO events
               (uid, calendar_path, course_key, session_type, summary, location,
                description, dtstart, dtend, ical_raw, last_synced)
               VALUES (:uid, :calendar_path, :course_key, :session_type, :summary,
                       :location, :description, :dtstart, :dtend, :ical_raw, :last_synced)""",
            events,
        )


def get_course_groups():
    """返回按 course_key 分组的课程列表，每个课程下附所有 session_type 选项"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT course_key, session_type, calendar_path
               FROM events ORDER BY course_key, session_type"""
        ).fetchall()

    groups: dict[str, dict] = {}
    for r in rows:
        key = r["course_key"]
        if key not in groups:
            groups[key] = {"course_key": key, "calendar_path": r["calendar_path"], "sessions": []}
        groups[key]["sessions"].append(r["session_type"])
    return list(groups.values())


def get_selection() -> set[tuple[str, str]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT course_key, session_type FROM selection").fetchall()
    return {(r["course_key"], r["session_type"]) for r in rows}


def save_selection(pairs: list[tuple[str, str]]):
    with get_conn() as conn:
        conn.execute("DELETE FROM selection")
        conn.executemany(
            "INSERT INTO selection (course_key, session_type) VALUES (?, ?)", pairs
        )


def get_selected_events() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.* FROM events e
               JOIN selection s
                 ON e.course_key = s.course_key AND e.session_type = s.session_type
               ORDER BY e.dtstart"""
        ).fetchall()
    return rows

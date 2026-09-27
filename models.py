from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    uid TEXT PRIMARY KEY,
    calendar_path TEXT NOT NULL,      -- 例如 RES/M1_RES
    master_group TEXT NOT NULL,       -- 顶层分类，例如 RES / SESI / SAR（对应官网左侧 Master 分类）
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

-- owner：每个使用者的空间标识（URL 里 /u/<owner>/ 的那个slug），课程数据(events)全站共享，
-- 只有 selection（谁选了什么课）按 owner 隔离，这样多个朋友互不干扰。
CREATE TABLE IF NOT EXISTS selection (
    owner TEXT NOT NULL,
    course_key TEXT NOT NULL,
    session_key TEXT NOT NULL,        -- 归一化后的 session_type（trim + lower），用于去重匹配
    PRIMARY KEY (owner, course_key, session_key)
);
"""

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def normalize_owner(raw: str) -> str:
    """把用户输入的名字变成安全的 slug（只留小写字母数字和短横线，最长32位）。
    用作 URL 路径段和 ics 文件名，绝不能包含 / \\ .. 等危险字符。
    """
    slug = re.sub(r"[^a-z0-9-]+", "-", (raw or "").strip().lower()).strip("-")
    slug = slug[:32]
    if not slug or not SLUG_RE.match(slug):
        raise ValueError("Nom invalide : lettres, chiffres et tirets uniquement.")
    return slug


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
        # 兼容旧数据库：如果是从没有 master_group / owner 字段的旧版本升级上来的，
        # 这里自动补上，避免用户手动删库重来。
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(events)")]
        if "master_group" not in cols:
            conn.execute("ALTER TABLE events ADD COLUMN master_group TEXT NOT NULL DEFAULT ''")

        sel_cols = [row["name"] for row in conn.execute("PRAGMA table_info(selection)")]
        if "owner" not in sel_cols:
            # 旧版本的 selection 表没有 owner 概念，没法安全地加主键列，
            # 直接重建成新结构，旧的（无主人的）选课记录只能作废。
            conn.execute("ALTER TABLE selection RENAME TO selection_old")
            conn.execute(
                """CREATE TABLE selection (
                    owner TEXT NOT NULL,
                    course_key TEXT NOT NULL,
                    session_key TEXT NOT NULL,
                    PRIMARY KEY (owner, course_key, session_key)
                )"""
            )
            conn.execute("DROP TABLE selection_old")


def replace_events(events: list[dict]):
    """全量覆盖式写入本次同步抓到的事件（course_key/session_type/master_group 已解析好）"""
    with get_conn() as conn:
        conn.execute("DELETE FROM events")
        conn.executemany(
            """INSERT INTO events
               (uid, calendar_path, master_group, course_key, session_type, summary,
                location, description, dtstart, dtend, ical_raw, last_synced)
               VALUES (:uid, :calendar_path, :master_group, :course_key, :session_type,
                       :summary, :location, :description, :dtstart, :dtend, :ical_raw,
                       :last_synced)""",
            events,
        )


def get_course_groups():
    """按 Master 分类 -> 课程 -> 场次 的三层结构返回全部课程（全站共享，与 owner 无关），
    供选课页面渲染。同一门课如果因跨系互选出现在多个日历里，这里按 course_key 合并去重；
    场次标签按 trim+小写 去重（避免 'Cours' / 'cours' 被当成两个不同的场次）。
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT master_group, course_key, session_type,
                      TRIM(LOWER(session_type)) AS session_key
               FROM events
               ORDER BY course_key, session_type"""
        ).fetchall()

    sessions_by_course: dict[str, dict[str, str]] = {}
    group_session_counts: dict[str, dict[str, int]] = {}

    for r in rows:
        key = r["course_key"]
        sessions_by_course.setdefault(key, {})
        sessions_by_course[key].setdefault(r["session_key"], r["session_type"])

        counts = group_session_counts.setdefault(key, {})
        counts[r["master_group"]] = counts.get(r["master_group"], 0) + 1

    home_group: dict[str, str] = {}
    for key, counts in group_session_counts.items():
        home_group[key] = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    grouped: dict[str, list] = {}
    for key, sessions in sessions_by_course.items():
        grouped.setdefault(home_group[key], []).append(
            {
                "course_key": key,
                "sessions": sorted(sessions.items(), key=lambda kv: kv[1]),
            }
        )

    result = []
    for master_group in sorted(grouped.keys()):
        courses_list = sorted(grouped[master_group], key=lambda c: c["course_key"])
        result.append({"master_group": master_group, "courses": courses_list})
    return result


def get_all_owners() -> list[str]:
    """返回目前有选课记录的所有 owner，供批量重新生成每个人的 .ics"""
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT owner FROM selection ORDER BY owner").fetchall()
    return [r["owner"] for r in rows]
def get_selection(owner: str) -> set[tuple[str, str]]:
    """返回某个 owner 的 (course_key, session_key) 归一化后已选集合"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT course_key, session_key FROM selection WHERE owner = ?", (owner,)
        ).fetchall()
    return {(r["course_key"], r["session_key"]) for r in rows}


def save_selection(owner: str, pairs: list[tuple[str, str]]):
    """pairs: [(course_key, session_type_raw), ...]，这里统一归一化后存储，只影响这个 owner 自己的选课"""
    normalized = [(owner, ck, st.strip().lower()) for ck, st in pairs]
    with get_conn() as conn:
        conn.execute("DELETE FROM selection WHERE owner = ?", (owner,))
        conn.executemany(
            "INSERT INTO selection (owner, course_key, session_key) VALUES (?, ?, ?)", normalized
        )


def get_selected_events(
    owner: str, start: str | None = None, end: str | None = None
) -> list[sqlite3.Row]:
    """start/end: ISO8601 字符串，按 dtstart 过滤范围（都不传则返回全部，用于生成完整 .ics）"""
    query = """SELECT e.* FROM events e
               JOIN selection s
                 ON e.course_key = s.course_key
                AND TRIM(LOWER(e.session_type)) = s.session_key
               WHERE s.owner = ?"""
    params: list = [owner]
    if start:
        query += " AND e.dtstart >= ?"
        params.append(start)
    if end:
        query += " AND e.dtstart <= ?"
        params.append(end)
    query += " ORDER BY e.dtstart"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    # 同一门课因跨系互选会在多个系的日历里被重复抓到；如果时间、课程、场次完全一致，
    # 大概率是同一节课的重复副本（哪怕标题大小写不同，比如 'Cours' / 'cours'），
    # 只保留一份，避免日历里同一节课出现两次。
    seen = set()
    deduped = []
    for row in rows:
        dedup_key = (
            row["course_key"],
            row["dtstart"],
            row["dtend"],
            row["session_type"].strip().lower(),
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        deduped.append(row)
    return deduped

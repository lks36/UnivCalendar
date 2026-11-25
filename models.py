from __future__ import annotations

import re

from sqlalchemy import create_engine, text

from config import DATABASE_URL
from matching import classify, ue_codes

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

# pool_pre_ping: 云端 Postgres 连接可能因为空闲被服务器断开，这个选项让 SQLAlchemy
# 每次用连接前先探测一下，断了就自动换一条新连接，避免"连接已失效"的报错。
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS events (
        uid TEXT PRIMARY KEY,
        calendar_path TEXT NOT NULL,
        master_group TEXT NOT NULL,
        course_key TEXT NOT NULL,
        session_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        location TEXT,
        description TEXT,
        dtstart TEXT NOT NULL,
        dtend TEXT NOT NULL,
        ical_raw TEXT NOT NULL,
        last_synced TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS selection (
        owner TEXT NOT NULL,
        course_key TEXT NOT NULL,
        session_key TEXT NOT NULL,
        PRIMARY KEY (owner, course_key, session_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dismissed (
        owner TEXT NOT NULL,
        course_key TEXT NOT NULL,
        session_key TEXT NOT NULL,
        PRIMARY KEY (owner, course_key, session_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_course ON events (course_key)",
    "CREATE INDEX IF NOT EXISTS idx_events_dtstart ON events (dtstart)",
]


def normalize_owner(raw: str) -> str:
    """把用户输入的名字变成安全的 slug（只留小写字母数字和短横线，最长32位）。
    用作 URL 路径段和 ics 文件名，绝不能包含 / \\ .. 等危险字符。
    """
    slug = re.sub(r"[^a-z0-9-]+", "-", (raw or "").strip().lower()).strip("-")
    slug = slug[:32]
    if not slug or not SLUG_RE.match(slug):
        raise ValueError("Nom invalide : lettres, chiffres et tirets uniquement.")
    return slug


def init_db():
    with engine.begin() as conn:
        for stmt in SCHEMA_STATEMENTS:
            conn.execute(text(stmt))

        # 兼容从旧版 SQLite 库升级上来的情况（旧表没有 master_group / owner 字段）。
        # 只在 SQLite 下做这个检查——全新的云端 Postgres 库从一开始就是新结构，不需要迁移。
        if engine.dialect.name == "sqlite":
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(events)"))]
            if "master_group" not in cols:
                conn.execute(text("ALTER TABLE events ADD COLUMN master_group TEXT NOT NULL DEFAULT ''"))

            sel_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(selection)"))]
            if "owner" not in sel_cols:
                conn.execute(text("ALTER TABLE selection RENAME TO selection_old"))
                conn.execute(text(SCHEMA_STATEMENTS[1]))
                conn.execute(text("DROP TABLE selection_old"))


def replace_events(events: list[dict]):
    """全量覆盖式写入本次同步抓到的事件（course_key/session_type/master_group 已解析好）"""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM events"))
        if events:
            conn.execute(
                text(
                    """INSERT INTO events
                       (uid, calendar_path, master_group, course_key, session_type, summary,
                        location, description, dtstart, dtend, ical_raw, last_synced)
                       VALUES (:uid, :calendar_path, :master_group, :course_key, :session_type,
                               :summary, :location, :description, :dtstart, :dtend, :ical_raw,
                               :last_synced)"""
                ),
                events,
            )


# ------------------------------------------------------------------
# 分批同步：每抓完一个日历就写进临时表 events_staging（不在内存里堆几万条），
# 全部抓完后在一个事务里替换 events。中途失败的话 events 完全不受影响。
# ------------------------------------------------------------------
_EVENT_COLS = ("uid, calendar_path, master_group, course_key, session_type, summary, "
               "location, description, dtstart, dtend, ical_raw, last_synced")


def staging_reset():
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_STATEMENTS[0].replace("CREATE TABLE IF NOT EXISTS events",
                                                       "CREATE TABLE IF NOT EXISTS events_staging")))
        conn.execute(text("DELETE FROM events_staging"))


def staging_add(events: list[dict]):
    if not events:
        return
    with engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO events_staging ({_EVENT_COLS}) VALUES "
                 "(:uid, :calendar_path, :master_group, :course_key, :session_type, :summary, "
                 ":location, :description, :dtstart, :dtend, :ical_raw, :last_synced)"),
            events,
        )


def get_event_paths() -> set[str]:
    """正式表里目前有数据的日历路径"""
    with engine.begin() as conn:
        return {r[0] for r in conn.execute(text("SELECT DISTINCT calendar_path FROM events"))}


def staging_commit(keep_old_paths: list[str]) -> tuple[int, int]:
    """用临时表替换正式表。
    keep_old_paths：这次没抓到任何数据的日历（请求失败、或整个日历凭空消失），保留它们的旧数据。
    课程数量变少（比如罢课期间大量取消）是正常情况，照常替换。"""
    with engine.begin() as conn:
        for path in keep_old_paths:
            conn.execute(text(f"INSERT INTO events_staging ({_EVENT_COLS}) SELECT {_EVENT_COLS} "
                              "FROM events WHERE calendar_path = :p"), {"p": path})
        new = conn.execute(text("SELECT COUNT(*) FROM events_staging")).scalar()
        old = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
        if new == 0:
            raise RuntimeError("没有任何数据，已保留旧数据")
        conn.execute(text("DELETE FROM events"))
        conn.execute(text(f"INSERT INTO events ({_EVENT_COLS}) SELECT {_EVENT_COLS} FROM events_staging"))
        conn.execute(text("DELETE FROM events_staging"))
    return new, old


def get_course_groups():
    """按 Master 分类 -> 课程 -> 场次 的三层结构返回全部课程（全站共享，与 owner 无关）"""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """SELECT DISTINCT master_group, course_key, session_type,
                          TRIM(LOWER(session_type)) AS session_key
                   FROM events
                   ORDER BY course_key, session_type"""
            )
        ).mappings().all()

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
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT DISTINCT owner FROM selection ORDER BY owner")).all()
    return [r[0] for r in rows]


def get_selection(owner: str) -> set[tuple[str, str]]:
    """返回某个 owner 的 (course_key, session_key) 归一化后已选集合"""
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT course_key, session_key FROM selection WHERE owner = :owner"),
            {"owner": owner},
        ).all()
    return {(r[0], r[1]) for r in rows}


def save_selection(owner: str, pairs: list[tuple[str, str]]):
    """pairs: [(course_key, session_type_raw), ...]，只影响这个 owner 自己的选课"""
    normalized = [
        {"owner": owner, "course_key": ck, "session_key": st.strip().lower()} for ck, st in pairs
    ]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM selection WHERE owner = :owner"), {"owner": owner})
        if normalized:
            conn.execute(
                text(
                    "INSERT INTO selection (owner, course_key, session_key) "
                    "VALUES (:owner, :course_key, :session_key)"
                ),
                normalized,
            )


def get_dismissed(owner: str) -> set[tuple[str, str]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT course_key, session_key FROM dismissed WHERE owner = :owner"), {"owner": owner}
        ).all()
    return {(r[0], r[1]) for r in rows}


def add_selection_item(owner: str, course_key: str, session_type: str):
    key = {"owner": owner, "course_key": course_key, "session_key": session_type.strip().lower()}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM selection WHERE owner = :owner AND course_key = :course_key "
                          "AND session_key = :session_key"), key)
        conn.execute(text("INSERT INTO selection (owner, course_key, session_key) "
                          "VALUES (:owner, :course_key, :session_key)"), key)
        conn.execute(text("DELETE FROM dismissed WHERE owner = :owner AND course_key = :course_key "
                          "AND session_key = :session_key"), key)


def dismiss_item(owner: str, course_key: str, session_type: str):
    key = {"owner": owner, "course_key": course_key, "session_key": session_type.strip().lower()}
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM dismissed WHERE owner = :owner AND course_key = :course_key "
                          "AND session_key = :session_key"), key)
        conn.execute(text("INSERT INTO dismissed (owner, course_key, session_key) "
                          "VALUES (:owner, :course_key, :session_key)"), key)


def get_owner_events(owner: str, start: str | None = None, end: str | None = None,
                     include_suggested: bool = True) -> list[dict]:
    """这个人课表里的课（status='selected'），以及需要他确认的疑似新场次（status='suggested'）。
    匹配规则见 matching.py：老师改了场次名（如 TME → CS/TME）也能自动认出来。"""
    selection = get_selection(owner)
    if not selection:
        return []
    dismissed = get_dismissed(owner)

    # 候选：用户选过的课程，以及同一课程代码（UM4IN101-...）下的所有课
    conds, params = [], {}
    for i, ck in enumerate(sorted({ck for ck, _ in selection})):
        conds.append(f"course_key = :ck{i}")
        params[f"ck{i}"] = ck
    for i, ue in enumerate(sorted(ue_codes(selection))):
        conds.append(f"course_key LIKE :ue{i}")
        params[f"ue{i}"] = f"{ue}-%"
    query = f"SELECT * FROM events WHERE ({' OR '.join(conds)})"
    if start:
        query += " AND dtstart >= :start"
        params["start"] = start
    if end:
        query += " AND dtstart <= :end"
        params["end"] = end
    query += " ORDER BY dtstart"

    with engine.begin() as conn:
        rows = [dict(r) for r in conn.execute(text(query), params).mappings().all()]

    result, seen = [], set()
    for row in rows:
        status = classify(row["course_key"], row["session_type"], selection, dismissed)
        if status == "hidden" or (status == "suggested" and not include_suggested):
            continue
        # 同一节课因跨系互选会被重复抓到（时间、课程、场次都一样），只保留一份
        dedup_key = (row["course_key"], row["dtstart"], row["dtend"], row["session_type"].strip().lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        row["status"] = status
        result.append(row)
    return result


def get_selected_events(owner: str, start: str | None = None, end: str | None = None) -> list[dict]:
    """只要确定属于这个人的课（生成 .ics 订阅用，不含待确认的场次）"""
    return get_owner_events(owner, start, end, include_suggested=False)


def get_last_synced() -> str | None:
    """课程数据最近一次同步的时间（ISO 字符串），没有数据时返回 None"""
    with engine.begin() as conn:
        return conn.execute(text("SELECT MAX(last_synced) FROM events")).scalar()

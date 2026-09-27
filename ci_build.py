"""GitHub Actions 里跑的构建脚本，不依赖本地 sqlite（Actions runner 每次都是全新环境）：

    读取 selection.json（选课结果） -> 从 CalDAV 抓全量最新数据 -> 按选课过滤 ->
    跨系重复去重 -> 生成 docs/mon_emploi_du_temps.ics + docs/calendar-data.json

docs/ 整个目录就是要发布到 GitHub Pages 的静态站点内容。
"""

from __future__ import annotations

import json
import os
import datetime

from caldav_client import sync_all
from ics_generator import build_ics

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SELECTION_PATH = os.path.join(BASE_DIR, "selection.json")
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def load_selection() -> set[tuple[str, str]]:
    with open(SELECTION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {(item["course_key"], item["session_type"].strip().lower()) for item in data}


def dedupe(events: list[dict]) -> list[dict]:
    """同一门课因跨系互选可能被抓到重复副本（同一时间同一场次），只保留一份"""
    seen = set()
    deduped = []
    for e in sorted(events, key=lambda e: e["dtstart"]):
        key = (e["course_key"], e["session_type"].strip().lower(), e["dtstart"], e["dtend"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def main():
    selection = load_selection()
    if not selection:
        raise SystemExit(
            "selection.json 是空的，先在本地跑 export_selection.py 导出你选的课再提交。"
        )

    print(f"读取到 {len(selection)} 个已选场次，开始从 CalDAV 抓取最新数据...")
    all_events = sync_all()
    if not all_events:
        raise SystemExit("本次没有从 CalDAV 抓到任何事件，可能是网络/凭证问题，终止构建。")

    matched = [
        e for e in all_events
        if (e["course_key"], e["session_type"].strip().lower()) in selection
    ]
    deduped = dedupe(matched)
    print(f"匹配到 {len(deduped)} 个事件（去重后）")

    os.makedirs(DOCS_DIR, exist_ok=True)

    # .ics
    ics_bytes = build_ics(deduped)
    with open(os.path.join(DOCS_DIR, "mon_emploi_du_temps.ics"), "wb") as f:
        f.write(ics_bytes)

    # calendar-data.json，字段跟本地 Flask 版 /api/calendar 保持一致，
    # 静态页面的 JS 可以直接复用同一套渲染逻辑
    payload = {
        "events": [
            {
                "course_key": e["course_key"],
                "session_type": e["session_type"],
                "location": e["location"],
                "start": e["dtstart"],
                "end": e["dtend"],
            }
            for e in deduped
        ],
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(os.path.join(DOCS_DIR, "calendar-data.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("构建完成，docs/ 已更新。")


if __name__ == "__main__":
    main()

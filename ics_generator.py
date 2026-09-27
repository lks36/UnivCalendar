"""把选中的事件（原始 VEVENT 文本）合并成一份标准 .ics 文件。
直接复用官方服务器给出的 VEVENT 原文，包括其中的 VTIMEZONE 定义，
避免自己重新计算时区/夏令时。
"""

import os

from icalendar import Calendar, Event

from config import ICS_DIR


def build_ics(event_rows) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Sorbonne Cal Sync//mon-emploi-du-temps//FR")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Mon emploi du temps")
    cal.add("x-wr-timezone", "Europe/Paris")

    for row in event_rows:
        # row["ical_raw"] 是单个 VEVENT 的原始文本，重新解析后加入总日历，
        # 这样时区信息、换行格式都严格遵循 RFC5545，不需要手工拼装。
        event = Event.from_ical(row["ical_raw"])
        cal.add_component(event)

    return cal.to_ical()


def ics_path_for(owner: str) -> str:
    return os.path.join(ICS_DIR, f"{owner}.ics")


def write_ics_file(owner: str, event_rows) -> str:
    os.makedirs(ICS_DIR, exist_ok=True)
    path = ics_path_for(owner)
    data = build_ics(event_rows)
    with open(path, "wb") as f:
        f.write(data)
    return path

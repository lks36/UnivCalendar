"""
负责和学校 CalDAV 服务器打交道：
1. 递归 PROPFIND 发现所有系/方向下的真正"日历"collection（叶子节点）
   —— 注意：不能用 caldav 库的 principal.calendars()，那只会返回
   student.master 这个账号自己名下的日历，不会遍历 RES/、SESI/ 这些
   属于其他账号、但允许匿名只读的目录。必须像浏览器一样手动逐层 PROPFIND。
2. 抓取每个日历近期范围内的事件（原始 VEVENT，时区由服务器给出，不做手工处理）
3. 从课程标题里解析出 course_key（课程本体）和 session_type（具体场次/分组）
"""

import datetime
import logging
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import caldav
import requests
from icalendar import Calendar as ICalendar

from config import (
    CALDAV_BASE_URL,
    CALDAV_USERNAME,
    CALDAV_PASSWORD,
    SYNC_MONTHS_AHEAD,
    SYNC_MONTHS_BEHIND,
)

logger = logging.getLogger(__name__)

DAV_NS = "DAV:"
CALDAV_NS = "urn:ietf:params:xml:ns:caldav"

_PROPFIND_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
  </D:prop>
</D:propfind>"""


def get_client() -> caldav.DAVClient:
    return caldav.DAVClient(
        url=CALDAV_BASE_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD
    )


def _propfind_children(url: str, auth) -> list[dict]:
    """对一个目录发 Depth:1 的 PROPFIND，返回它的直接子节点，
    每个子节点标注是"日历"还是普通目录。"""
    resp = requests.request(
        "PROPFIND",
        url,
        data=_PROPFIND_BODY,
        auth=auth,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        timeout=20,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    base_path = urlparse(url).path.rstrip("/")
    children = []
    for response in root.findall(f"{{{DAV_NS}}}response"):
        href_el = response.find(f"{{{DAV_NS}}}href")
        if href_el is None:
            continue
        href = href_el.text
        href_path = urlparse(href).path.rstrip("/")
        if href_path == base_path:
            continue  # 跳过节点自身（PROPFIND Depth:1 会把自己也列进去）

        propstat = response.find(f"{{{DAV_NS}}}propstat")
        prop = propstat.find(f"{{{DAV_NS}}}prop") if propstat is not None else None
        resourcetype = prop.find(f"{{{DAV_NS}}}resourcetype") if prop is not None else None

        is_calendar = (
            resourcetype is not None
            and resourcetype.find(f"{{{CALDAV_NS}}}calendar") is not None
        )
        is_collection = (
            resourcetype is not None
            and resourcetype.find(f"{{{DAV_NS}}}collection") is not None
        )
        if not is_collection:
            continue  # 不是目录/日历（比如单个 .ics 事件文件），跳过

        children.append({"href": href, "is_calendar": is_calendar})
    return children


def discover_leaf_calendars(max_depth: int = 6) -> list[str]:
    """从根路径开始递归 PROPFIND，返回所有真正"日历"collection 的完整 URL 列表。
    是普通目录（如 RES/）就继续往下钻；是日历（如 RES/M1_RES/）就收集起来不再深入。
    """
    auth = (CALDAV_USERNAME, CALDAV_PASSWORD)
    visited: set[str] = set()
    leaves: list[str] = []

    def _walk(url: str, depth: int):
        path_key = urlparse(url).path.rstrip("/")
        if path_key in visited or depth > max_depth:
            return
        visited.add(path_key)

        try:
            children = _propfind_children(url, auth)
        except Exception as e:
            logger.warning("PROPFIND 失败 %s: %s", url, e)
            return

        for child in children:
            child_url = urljoin(url, child["href"])
            if child["is_calendar"]:
                leaves.append(child_url)
            else:
                _walk(child_url, depth + 1)

    _walk(CALDAV_BASE_URL, 0)
    return leaves


def parse_course_key_and_session(summary: str) -> tuple[str, str]:
    """把 'UM4IN002-RTEL-TD2' 拆成 ('UM4IN002-RTEL', 'TD2')。
    没有 '-' 的标题整体当作 course_key，session_type 固定为 '默认场次'。
    这是启发式规则：学校课程命名基本遵循 <课程代码>-<课程名>-<场次/分组> 的格式，
    如果后续发现有例外情况，在这里调整即可。
    """
    summary = (summary or "").strip()
    if "-" in summary:
        course_key, session_type = summary.rsplit("-", 1)
        return course_key.strip(), session_type.strip()
    return summary, "默认场次"


def fetch_calendar_events(calendar: caldav.Calendar, calendar_path: str) -> list[dict]:
    """抓取单个日历在配置时间窗口内的所有事件，解析成待入库的 dict 列表"""
    start = datetime.datetime.now() - datetime.timedelta(days=30 * SYNC_MONTHS_BEHIND)
    end = datetime.datetime.now() + datetime.timedelta(days=30 * SYNC_MONTHS_AHEAD)

    try:
        results = calendar.date_search(start=start, end=end, expand=True)
    except Exception as e:
        logger.warning("跳过日历 %s（请求失败: %s）", calendar_path, e)
        return []

    events = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for item in results:
        try:
            ical_raw = item.data
            cal = ICalendar.from_ical(ical_raw)
            for component in cal.walk("VEVENT"):
                uid = str(component.get("UID"))
                summary = str(component.get("SUMMARY", ""))
                location = str(component.get("LOCATION", "") or "")
                description = str(component.get("DESCRIPTION", "") or "")
                dtstart = component.get("DTSTART").dt
                dtend = component.get("DTEND").dt if component.get("DTEND") else dtstart

                course_key, session_type = parse_course_key_and_session(summary)

                events.append(
                    {
                        "uid": f"{calendar_path}:{uid}:{dtstart.isoformat()}",
                        "calendar_path": calendar_path,
                        "course_key": course_key,
                        "session_type": session_type,
                        "summary": summary,
                        "location": location,
                        "description": description,
                        "dtstart": dtstart.isoformat(),
                        "dtend": dtend.isoformat(),
                        "ical_raw": component.to_ical().decode("utf-8"),
                        "last_synced": now_iso,
                    }
                )
        except Exception as e:
            logger.warning("解析事件失败，已跳过: %s", e)
            continue

    return events


def sync_all() -> list[dict]:
    """主入口：递归发现所有日历 + 抓取全部事件，返回待入库列表"""
    client = get_client()
    leaf_urls = discover_leaf_calendars()
    logger.info("递归发现 %d 个日历", len(leaf_urls))

    all_events = []
    for leaf_url in leaf_urls:
        calendar_path = leaf_url.split("/caldav.php/")[-1].strip("/")
        cal = caldav.Calendar(client=client, url=leaf_url)
        events = fetch_calendar_events(cal, calendar_path)
        logger.info("  %s -> %d 个事件", calendar_path, len(events))
        all_events.extend(events)

    return all_events

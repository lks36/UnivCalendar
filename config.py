import os

# ---- CalDAV 服务器配置 ----
CALDAV_BASE_URL = os.environ.get(
    "CALDAV_BASE_URL", "https://cal.ufr-info-p6.jussieu.fr/caldav.php/"
)
CALDAV_USERNAME = os.environ.get("CALDAV_USERNAME", "student.master")
CALDAV_PASSWORD = os.environ.get("CALDAV_PASSWORD", "guest")

# ---- 本地存储 ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
ICS_OUTPUT_PATH = os.path.join(BASE_DIR, "static", "mon_emploi_du_temps.ics")

# ---- 同步范围 ----
# 只抓取这几个未来月份内的事件，避免拉取过多历史数据
SYNC_MONTHS_AHEAD = 6
SYNC_MONTHS_BEHIND = 1

# ---- 内容过滤 ----
# 标题中包含这些关键词（不区分大小写）的事件视为"非课程"活动，直接丢弃：
# 答辩、实习、就业活动、行政注册、开学会议、假期等。按需增删。
JUNK_KEYWORDS = [
    "stage",
    "soutenance",
    "atrium",
    "inscription",
    "réunion",
    "reunion",
    "vacances",
    "rentrée",
    "rentree",
    "jury",
    "pédagogique",
    "pedagogique",
]

# 标题中包含这些关键词时，即使被上面的规则判定为"非课程"或格式不标准，也强制保留。
# 比如想保留命名不规范的英语课，就填 ["Anglais"]。
ALLOWLIST_KEYWORDS: list[str] = []

# 日历路径中某一段等于/以这些开头（不区分大小写）的，整个日历跳过不抓取
# （默认只保留 M1，不需要任何 M2 的课程）
SKIP_CALENDAR_SEGMENT_PREFIXES = ["m2"]

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

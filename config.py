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

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

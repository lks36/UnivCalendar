import os

# ---- CalDAV 服务器配置 ----
CALDAV_BASE_URL = (
    os.environ.get("CALDAV_BASE_URL") or "https://cal.ufr-info-p6.jussieu.fr/caldav.php/"
)
# 用 `or` 兜底而不是 os.environ.get(key, default)：GitHub Actions 里如果没配置对应
# Secret，环境变量会被设成空字符串而不是完全不存在，.get 的 default 值就不会生效。
CALDAV_USERNAME = os.environ.get("CALDAV_USERNAME") or "student.master"
CALDAV_PASSWORD = os.environ.get("CALDAV_PASSWORD") or "guest"

# ---- 本地存储 ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
# 没配置 DATABASE_URL 时用本地 SQLite（方便本地开发/测试）；
# 部署到云端时设置 DATABASE_URL 指向 Neon/Supabase 这类免费云端 Postgres，
# 数据就不会因为服务器重启/休眠而丢失。
_raw_database_url = os.environ.get("DATABASE_URL") or f"sqlite:///{DB_PATH}"
# Neon/Render/Heroku 这类平台给出的连接串常常是旧式的 postgres://，
# SQLAlchemy 需要 postgresql:// 前缀，这里做个兼容转换。
# 根据环境里实际装了哪个 Postgres 驱动，自动选择（psycopg 3 优先，其次 psycopg2），
# 显式写进连接串，避免 SQLAlchemy 默认驱动和实际安装的包对不上
# （报错 "No module named 'psycopg'" / "'psycopg2'" 就是这个原因）。
def _pick_pg_driver() -> str:
    try:
        import psycopg  # noqa: F401
        return "psycopg"
    except ImportError:
        pass
    try:
        import psycopg2  # noqa: F401
        return "psycopg2"
    except ImportError:
        pass
    raise RuntimeError(
        "DATABASE_URL 指向 Postgres，但没有安装任何驱动：请在 requirements.txt 里加上 psycopg[binary]"
    )


for _prefix in ("postgres://", "postgresql://"):
    if _raw_database_url.startswith(_prefix):
        _raw_database_url = f"postgresql+{_pick_pg_driver()}://" + _raw_database_url[len(_prefix):]
        break
DATABASE_URL = _raw_database_url

# 每个使用者(owner)各自的 .ics 文件放这个目录下，文件名是 <owner>.ics
ICS_DIR = os.path.join(BASE_DIR, "static", "ics")

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

import datetime
import logging
import os
import secrets
import subprocess
import sys
import threading
import time

from flask import Flask, Response, g, abort, jsonify, make_response, redirect, render_template, request, url_for
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix

from config import SECRET_KEY
import models
from models import (
    init_db,
    get_course_groups,
    get_selection,
    save_selection,
    get_selected_events,
    get_last_synced,
    normalize_owner,
)
from ics_generator import build_ics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY
# Render 在前面有一层代理：让 Flask 知道原始请求是 https，生成的链接才对
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# 静态文件让浏览器缓存一年；文件名后面带版本号，每次部署版本号会变，浏览器自动拿新文件
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 365
ASSET_VERSION = str(int(time.time()))
Compress(app)  # gzip/br 压缩 HTML、JSON、CSS、JS，传输量通常减少 70~85%

init_db()

_sync_lock = threading.Lock()
_sync_status = {"running": False, "last_result": None}


# ==================================================================
# 内存缓存：课程列表全站共享、只在同步后才会变，没必要每个请求都查数据库
# ==================================================================
_cache_lock = threading.Lock()
_cache = {"courses": None, "last_synced": None, "loaded": False}


def _cached_courses():
    with _cache_lock:
        if not _cache["loaded"]:
            groups = get_course_groups()
            _cache["courses"] = {
                "groups": groups,
                "total": sum(len(g["courses"]) for g in groups),
            }
            _cache["last_synced"] = get_last_synced()
            _cache["loaded"] = True
        return _cache["courses"], _cache["last_synced"]


def _invalidate_cache():
    with _cache_lock:
        _cache["loaded"] = False
        _owner_cache.clear()


# 每个用户的"已选场次 + 日历数据"也放内存：老用户再次打开网站时完全不用查数据库，
# 这样 Neon 免费版休眠了也不会拖慢页面。保存选课、课表同步后会自动更新。
_owner_cache = {}  # owner -> {"day": date, "selection": set, "events": list}


def _owner_data(owner):
    today = datetime.date.today()
    with _cache_lock:
        entry = _owner_cache.get(owner)
        if entry and entry["day"] == today:
            return entry
    entry = {"day": today, "selection": get_selection(owner), "events": _calendar_events_db(owner)}
    with _cache_lock:
        _owner_cache[owner] = entry
    return entry


@app.before_request
def _start_timer():
    g._t0 = time.perf_counter()


@app.after_request
def _server_timing(response):
    t0 = getattr(g, "_t0", None)
    if t0 is not None:
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - t0) * 1000:.1f}"
    return response


@app.context_processor
def _inject_asset_version():
    return {"asset_version": ASSET_VERSION}


# ==================================================================
# 身份识别：第一次访问自动生成随机 ID 存进 cookie；换设备用个人链接 /u/<id>/
# ==================================================================
COOKIE_NAME = "sc_uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # 2 年


def _set_owner_cookie(response, owner):
    response.set_cookie(
        COOKIE_NAME, owner, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax", secure=request.is_secure
    )
    return response


def _current_owner():
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        return normalize_owner(raw)
    except ValueError:
        return None


@app.before_request
def _validate_owner_in_path():
    owner = request.view_args.get("owner") if request.view_args else None
    if owner is not None:
        try:
            normalize_owner(owner)
        except ValueError:
            abort(404)


def _calendar_events_db(owner):
    """这个人已选课程的事件（过去5周 ~ 未来5个月），前端周/日/月视图用"""
    today = datetime.date.today()
    start = datetime.datetime.combine(today - datetime.timedelta(days=35), datetime.time.min).isoformat()
    end = datetime.datetime.combine(today + datetime.timedelta(days=150), datetime.time.min).isoformat()
    return [
        {
            "course_key": r["course_key"],
            "session_type": r["session_type"],
            "location": r["location"],
            "start": r["dtstart"],
            "end": r["dtend"],
        }
        for r in get_selected_events(owner, start=start, end=end)
    ]


# ==================================================================
# 页面
# ==================================================================
@app.route("/health")
def health():
    """给 cron-job.org 保持唤醒用：只返回 ok，不渲染页面、不查数据库"""
    return Response("ok", mimetype="text/plain")


@app.route("/")
def home():
    _safe_auto_sync_check()  # 不阻塞：需要时只是启动后台同步
    owner = _current_owner()
    is_new = owner is None
    if is_new:
        owner = secrets.token_hex(8)

    # 首页只带"日历数据"，不再把几百门课程全部渲染进 HTML：
    # 课程列表等用户真的点开"选课"时才去 /api/courses 加载。
    if is_new:
        has_selection, events = False, []  # 新用户：一次数据库都不用查
    else:
        data = _owner_data(owner)
        has_selection, events = bool(data["selection"]), data["events"]
    _, last_synced = _cached_courses()

    response = make_response(
        render_template(
            "index.html",
            owner=owner,
            initial_tab="calendar" if has_selection else "select",
            initial_events=events,
            last_synced=last_synced,
            sync_running=_sync_status["running"],
            ics_https=f"{request.host_url}u/{owner}/mon_emploi_du_temps.ics",
            ics_webcal=f"webcal://{request.host}/u/{owner}/mon_emploi_du_temps.ics",
        )
    )
    response.headers["Cache-Control"] = "no-store"
    if is_new:
        _set_owner_cookie(response, owner)
    return response


@app.route("/u/<owner>/")
def personal_link(owner):
    """个人链接：在新设备上打开一次，把 ID 写进 cookie 再回首页（也兼容旧的 /u/<名字>/）"""
    return _set_owner_cookie(make_response(redirect(url_for("home"))), owner)


# ==================================================================
# API
# ==================================================================
@app.route("/u/<owner>/api/courses")
def api_courses(owner):
    """全部课程（内存缓存）+ 这个人已勾选的场次"""
    courses, _ = _cached_courses()
    selected = [[ck, sk] for ck, sk in _owner_data(owner)["selection"]]
    return jsonify({"groups": courses["groups"], "total": courses["total"], "selected": selected})


@app.route("/u/<owner>/api/save-selection", methods=["POST"])
def api_save_selection(owner):
    """保存勾选结果，并直接返回新的日历数据，前端不用再请求一次"""
    payload = request.get_json(force=True)
    pairs = [(item["course_key"], item["session_type"]) for item in payload.get("selection", [])]
    save_selection(owner, pairs)
    entry = {
        "day": datetime.date.today(),
        "selection": {(ck, st.strip().lower()) for ck, st in pairs},
        "events": _calendar_events_db(owner),
    }
    with _cache_lock:
        _owner_cache[owner] = entry
    return jsonify({"ok": True, "count": len(pairs), "events": entry["events"]})


@app.route("/u/<owner>/api/calendar")
def api_calendar(owner):
    return jsonify({"events": _owner_data(owner)["events"]})


@app.route("/u/<owner>/mon_emploi_du_temps.ics")
def serve_ics(owner):
    """日历订阅入口：每次请求直接从数据库现生成。
    以前是存成文件，但 Render 免费版重启就会清空磁盘，订阅链接会变 404。"""
    _safe_auto_sync_check()  # 苹果日历定期来拉时，顺便检查要不要更新
    data = build_ics(get_selected_events(owner))
    resp = Response(data, mimetype="text/calendar")
    resp.headers["Content-Disposition"] = "inline; filename=mon_emploi_du_temps.ics"
    resp.headers["Cache-Control"] = "max-age=300"
    return resp


# ==================================================================
# 课程数据同步（全站共享一份）
# ==================================================================
SYNC_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync.py")
SYNC_TIMEOUT = 15 * 60


def _run_sync_background():
    """在独立进程里跑 sync.py：解析几万条课程很吃 CPU，放在网站进程里会把网站卡住（之前一直转圈的原因）。
    独立进程 + 低优先级，网站照常响应；同步进程就算内存爆了被系统杀掉，网站也不受影响。"""
    _sync_status["running"] = True
    _sync_status["started_at"] = time.time()
    try:
        proc = subprocess.run([sys.executable, SYNC_SCRIPT], timeout=SYNC_TIMEOUT)
        if proc.returncode == 0:
            _invalidate_cache()
            _sync_status["last_result"] = "ok"
        else:
            _sync_status["last_result"] = "error"
            logger.error("同步进程失败，退出码 %s（详情见上面 [sync] 开头的日志）", proc.returncode)
    except subprocess.TimeoutExpired:
        _sync_status["last_result"] = "error"
        logger.error("同步超过 %d 分钟，已中止", SYNC_TIMEOUT // 60)
    except Exception:
        _sync_status["last_result"] = "error"
        logger.exception("启动同步进程失败")
    finally:
        _sync_status["running"] = False


def _start_sync_thread():
    def _target():
        with _sync_lock:
            _run_sync_background()

    threading.Thread(target=_target, daemon=True).start()


def _last_synced_age_minutes():
    _, last_synced = _cached_courses()
    if not last_synced:
        return float("inf")
    try:
        delta = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last_synced)
        return delta.total_seconds() / 60
    except ValueError:
        return float("inf")


# ==================================================================
# 自动同步：网站自己每 10 分钟检查一次，课表超过 AUTO_SYNC_HOURS 小时没更新就在后台更新。
# 有人打开网站、或苹果日历来拉 .ics 时也会顺便检查。不需要任何外部定时任务。
# ==================================================================
AUTO_SYNC_HOURS = float(os.environ.get("AUTO_SYNC_HOURS", "3"))
AUTO_SYNC_RETRY_MINUTES = 30   # 学校服务器出问题时，最多每 30 分钟重试一次
MANUAL_MIN_MINUTES = 10        # 手动更新按钮：10 分钟内同步过就不再重复
_last_auto_attempt = 0.0


def _auto_sync_enabled():
    return os.environ.get("DISABLE_AUTO_SYNC") != "1"


def _maybe_auto_sync():
    global _last_auto_attempt
    if not _auto_sync_enabled() or _sync_lock.locked() or _sync_status["running"]:
        return
    if time.time() - _last_auto_attempt < AUTO_SYNC_RETRY_MINUTES * 60:
        return
    if _last_synced_age_minutes() < AUTO_SYNC_HOURS * 60:
        return
    _last_auto_attempt = time.time()
    logger.info("课表数据已超过 %.0f 小时未更新，自动在后台同步", AUTO_SYNC_HOURS)
    _start_sync_thread()


def _safe_auto_sync_check():
    try:
        _maybe_auto_sync()
    except Exception:
        logger.exception("自动同步检查失败")


def _scheduler_loop():
    time.sleep(20)  # 等网站先启动好
    while True:
        _safe_auto_sync_check()
        time.sleep(600)


threading.Thread(target=_scheduler_loop, daemon=True).start()


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """网页上的"Actualiser"按钮：任何人可点，但 10 分钟内同步过就直接告诉对方已是最新"""
    if _sync_lock.locked() or _sync_status["running"]:
        return jsonify({"ok": True, "running": True})
    age = _last_synced_age_minutes()
    started_ago = (time.time() - _sync_status.get("started_at", 0)) / 60
    if min(age, started_ago) < MANUAL_MIN_MINUTES:
        return jsonify({"ok": True, "running": False, "fresh": True})
    _start_sync_thread()
    return jsonify({"ok": True, "running": True})


@app.route("/api/sync", methods=["GET", "POST"])
def api_sync():
    """强制同步（给管理员/外部定时任务用）。设置了环境变量 SYNC_TOKEN 时需要 ?token=口令"""
    expected = os.environ.get("SYNC_TOKEN")
    if expected and request.args.get("token") != expected:
        return jsonify({"ok": False, "message": "Token invalide"}), 403
    if _sync_lock.locked() or _sync_status["running"]:
        return jsonify({"ok": False, "message": "Synchronisation déjà en cours"}), 409
    _start_sync_thread()
    return jsonify({"ok": True, "message": "Synchronisation lancée"})


@app.route("/api/sync-status")
def api_sync_status():
    _, last_synced = _cached_courses()
    return jsonify({
        "running": _sync_status["running"],
        "last_result": _sync_status["last_result"],
        "last_synced": last_synced,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)

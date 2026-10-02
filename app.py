import datetime
import logging
import os
import secrets
import threading
import time

from flask import Flask, Response, abort, jsonify, make_response, redirect, render_template, request, url_for
from flask_compress import Compress

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
from caldav_client import sync_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY
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


def _calendar_events(owner):
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
    owner = _current_owner()
    is_new = owner is None
    if is_new:
        owner = secrets.token_hex(8)

    # 首页只带"日历数据"，不再把几百门课程全部渲染进 HTML：
    # 课程列表等用户真的点开"选课"时才去 /api/courses 加载。
    has_selection = bool(get_selection(owner)) if not is_new else False
    events = _calendar_events(owner) if has_selection else []
    _, last_synced = _cached_courses()

    response = make_response(
        render_template(
            "index.html",
            owner=owner,
            initial_tab="calendar" if has_selection else "select",
            initial_events=events,
            last_synced=last_synced,
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
    selected = [[ck, sk] for ck, sk in get_selection(owner)]
    return jsonify({"groups": courses["groups"], "total": courses["total"], "selected": selected})


@app.route("/u/<owner>/api/save-selection", methods=["POST"])
def api_save_selection(owner):
    """保存勾选结果，并直接返回新的日历数据，前端不用再请求一次"""
    payload = request.get_json(force=True)
    pairs = [(item["course_key"], item["session_type"]) for item in payload.get("selection", [])]
    save_selection(owner, pairs)
    return jsonify({"ok": True, "count": len(pairs), "events": _calendar_events(owner)})


@app.route("/u/<owner>/api/calendar")
def api_calendar(owner):
    return jsonify({"events": _calendar_events(owner)})


@app.route("/u/<owner>/mon_emploi_du_temps.ics")
def serve_ics(owner):
    """日历订阅入口：每次请求直接从数据库现生成。
    以前是存成文件，但 Render 免费版重启就会清空磁盘，订阅链接会变 404。"""
    data = build_ics(get_selected_events(owner))
    resp = Response(data, mimetype="text/calendar")
    resp.headers["Content-Disposition"] = "inline; filename=mon_emploi_du_temps.ics"
    resp.headers["Cache-Control"] = "max-age=900"
    return resp


# ==================================================================
# 课程数据同步（全站共享一份）
# ==================================================================
def _run_sync_background():
    _sync_status["running"] = True
    try:
        events = sync_all()
        if events:
            models.replace_events(events)
            _invalidate_cache()
            _sync_status["last_result"] = f"ok: {len(events)} événements"
        else:
            _sync_status["last_result"] = "Échec : aucun événement récupéré"
    except Exception as e:
        logger.exception("同步出错")
        _sync_status["last_result"] = f"Erreur : {e}"
    finally:
        _sync_status["running"] = False


@app.route("/api/sync", methods=["GET", "POST"])
def api_sync():
    """触发一次全量同步（后台线程）。设置了环境变量 SYNC_TOKEN 时需要 ?token=口令"""
    expected = os.environ.get("SYNC_TOKEN")
    if expected and request.args.get("token") != expected:
        return jsonify({"ok": False, "message": "Token invalide"}), 403
    if _sync_lock.locked() or _sync_status["running"]:
        return jsonify({"ok": False, "message": "Synchronisation déjà en cours"}), 409

    def _target():
        with _sync_lock:
            _run_sync_background()

    threading.Thread(target=_target, daemon=True).start()
    return jsonify({"ok": True, "message": "Synchronisation lancée"})


@app.route("/api/sync-status")
def api_sync_status():
    return jsonify(_sync_status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)

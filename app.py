import logging
import threading
import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, abort

from config import SECRET_KEY, ICS_DIR
import models
from models import (
    init_db,
    get_course_groups,
    get_selection,
    save_selection,
    get_selected_events,
    normalize_owner,
)
from ics_generator import write_ics_file
from caldav_client import sync_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY

init_db()

_sync_lock = threading.Lock()
_sync_status = {"running": False, "last_result": None}


# ==================================================================
# 入口页：输入/选择一个名字，进入自己的空间 /u/<owner>/
# 多人共用同一个服务时，每个人用不同的名字（slug）来区分各自的选课，
# 不需要注册登录，纯靠"知道自己叫什么"这个约定——朋友之间用足够了。
# ==================================================================
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/go", methods=["POST"])
def go_to_owner():
    raw_name = request.form.get("name", "")
    try:
        owner = normalize_owner(raw_name)
    except ValueError as e:
        return render_template("landing.html", error=str(e)), 400
    return redirect(url_for("index", owner=owner))


@app.before_request
def _validate_owner_in_path():
    """/u/<owner>/... 的请求先校验 owner 格式，避免奇怪字符进到文件路径里"""
    owner = request.view_args.get("owner") if request.view_args else None
    if owner is not None:
        try:
            normalize_owner(owner)
        except ValueError:
            abort(404)


@app.route("/u/<owner>/")
def index(owner):
    groups = get_course_groups()
    total_courses = sum(len(d["courses"]) for d in groups)
    selected = get_selection(owner)
    return render_template(
        "index.html",
        owner=owner,
        groups=groups,
        total_courses=total_courses,
        selected=selected,
        sync_status=_sync_status,
    )


@app.route("/u/<owner>/api/save-selection", methods=["POST"])
def api_save_selection(owner):
    """前端提交勾选结果：[{course_key, session_type}, ...]，只影响这个 owner 自己的选课"""
    payload = request.get_json(force=True)
    pairs = [(item["course_key"], item["session_type"]) for item in payload.get("selection", [])]
    save_selection(owner, pairs)

    # 保存后立即根据最新勾选重新生成这个人的 ics，能马上验证效果
    selected_events = get_selected_events(owner)
    write_ics_file(owner, selected_events)

    return jsonify({"ok": True, "count": len(pairs), "event_count": len(selected_events)})


@app.route("/u/<owner>/api/calendar")
def api_calendar(owner):
    """返回从今天起到未来约4个月的这个人已选课程事件，供前端渲染可视化日历"""
    today = datetime.date.today()
    start = datetime.datetime.combine(today, datetime.time.min).isoformat()
    end = datetime.datetime.combine(
        today + datetime.timedelta(days=4 * 30), datetime.time.min
    ).isoformat()

    rows = get_selected_events(owner, start=start, end=end)
    events = [
        {
            "course_key": r["course_key"],
            "session_type": r["session_type"],
            "location": r["location"],
            "start": r["dtstart"],
            "end": r["dtend"],
        }
        for r in rows
    ]
    return jsonify({"events": events, "range_start": start, "range_end": end})


@app.route("/u/<owner>/mon_emploi_du_temps.ics")
def serve_ics(owner):
    """日历订阅入口：手机/电脑日历 App 订阅这个地址（每个人自己的链接不一样）"""
    return send_from_directory(ICS_DIR, f"{owner}.ics", mimetype="text/calendar")


# ==================================================================
# 课程数据同步：全站共享一份，谁都能触发，不区分 owner
# ==================================================================
def _run_sync_background():
    global _sync_status
    _sync_status["running"] = True
    try:
        events = sync_all()
        if events:
            models.replace_events(events)
            for owner in models.get_all_owners():
                selected = get_selected_events(owner)
                write_ics_file(owner, selected)
            _sync_status["last_result"] = f"Synchronisation réussie : {len(events)} événements récupérés"
        else:
            _sync_status["last_result"] = "Échec : aucun événement récupéré, vérifiez la connexion/les identifiants"
    except Exception as e:
        logger.exception("同步出错")
        _sync_status["last_result"] = f"Erreur de synchronisation : {e}"
    finally:
        _sync_status["running"] = False


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """手动触发一次全量同步（后台线程执行，避免网页卡住）——全站共用，任何一个 owner 页面都能点"""
    if _sync_lock.locked() or _sync_status["running"]:
        return jsonify({"ok": False, "message": "Une synchronisation est déjà en cours, veuillez patienter"}), 409

    def _target():
        with _sync_lock:
            _run_sync_background()

    threading.Thread(target=_target, daemon=True).start()
    return jsonify({"ok": True, "message": "Synchronisation lancée en arrière-plan, actualisez la page pour voir le résultat"})


@app.route("/api/sync-status")
def api_sync_status():
    return jsonify(_sync_status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)

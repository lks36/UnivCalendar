import logging
import threading
import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory

from config import SECRET_KEY, BASE_DIR
import models
from models import (
    init_db,
    get_course_groups,
    get_selection,
    save_selection,
    get_selected_events,
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


@app.route("/")
def index():
    groups = get_course_groups()
    total_courses = sum(len(d["courses"]) for d in groups)
    selected = get_selection()
    return render_template(
        "index.html",
        groups=groups,
        total_courses=total_courses,
        selected=selected,
        sync_status=_sync_status,
    )


@app.route("/api/save-selection", methods=["POST"])
def api_save_selection():
    """前端提交勾选结果：[{course_key, session_type}, ...]"""
    payload = request.get_json(force=True)
    pairs = [(item["course_key"], item["session_type"]) for item in payload.get("selection", [])]
    save_selection(pairs)

    # 保存后立即根据最新勾选重新生成 ics，用户能马上验证效果
    selected_events = get_selected_events()
    write_ics_file(selected_events)

    return jsonify({"ok": True, "count": len(pairs), "event_count": len(selected_events)})


def _run_sync_background():
    global _sync_status
    _sync_status["running"] = True
    try:
        events = sync_all()
        if events:
            models.replace_events(events)
            selected = get_selected_events()
            write_ics_file(selected)
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
    """手动触发一次全量同步（后台线程执行，避免网页卡住）"""
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


@app.route("/api/calendar")
def api_calendar():
    """返回从今天起到未来约4个月的已选课程事件，供前端渲染可视化日历。
    前端自己再把最近14天当"日程表"、剩下的当"月份总览"来分开展示。
    """
    today = datetime.date.today()
    start = datetime.datetime.combine(today, datetime.time.min).isoformat()
    end = datetime.datetime.combine(
        today + datetime.timedelta(days=4 * 30), datetime.time.min
    ).isoformat()

    rows = get_selected_events(start=start, end=end)
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


@app.route("/mon_emploi_du_temps.ics")
def serve_ics():
    """日历订阅入口：手机/电脑日历 App 订阅这个地址"""
    return send_from_directory(
        f"{BASE_DIR}/static", "mon_emploi_du_temps.ics", mimetype="text/calendar"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)

import logging
import threading

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
    selected = get_selection()
    return render_template(
        "index.html", groups=groups, selected=selected, sync_status=_sync_status
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
            _sync_status["last_result"] = f"成功，抓到 {len(events)} 条事件"
        else:
            _sync_status["last_result"] = "同步失败：没有抓到任何事件，请检查网络/凭证"
    except Exception as e:
        logger.exception("同步出错")
        _sync_status["last_result"] = f"同步出错：{e}"
    finally:
        _sync_status["running"] = False


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """手动触发一次全量同步（后台线程执行，避免网页卡住）"""
    if _sync_lock.locked() or _sync_status["running"]:
        return jsonify({"ok": False, "message": "已经有一个同步任务在跑，请稍候"}), 409

    def _target():
        with _sync_lock:
            _run_sync_background()

    threading.Thread(target=_target, daemon=True).start()
    return jsonify({"ok": True, "message": "同步已在后台开始，刷新页面查看结果"})


@app.route("/api/sync-status")
def api_sync_status():
    return jsonify(_sync_status)


@app.route("/mon_emploi_du_temps.ics")
def serve_ics():
    """日历订阅入口：手机/电脑日历 App 订阅这个地址"""
    return send_from_directory(
        f"{BASE_DIR}/static", "mon_emploi_du_temps.ics", mimetype="text/calendar"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)

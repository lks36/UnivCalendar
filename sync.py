"""课表同步：python3 sync.py
网站会在独立进程里调用它（不占用网站进程的 CPU），也可以手动在命令行运行。
逐个日历抓取并写入临时表，全部成功后再一次性替换，过程中网站照常显示旧数据。"""

import logging
import os
import sys

from models import init_db, staging_reset, staging_add, staging_commit, get_event_paths
from caldav_client import iter_calendar_events, is_excluded_calendar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [sync] %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        os.nice(10)  # 降低优先级，CPU 优先让给网站的请求
    except (AttributeError, OSError):
        pass

    init_db()
    staging_reset()
    old_paths = get_event_paths()
    failed, got, total = [], set(), 0
    for path, events in iter_calendar_events():
        if events is None:
            failed.append(path)
            continue
        if events:
            got.add(path)
        staging_add(events)
        total += len(events)

    # 上次有课、这次一条都没拿到的日历：多半是抓取出错（取消课程不会让整个日历清零），保留旧数据
    missing = sorted(p for p in old_paths - got - set(failed) if not is_excluded_calendar(p))
    for p in missing:
        logger.warning("日历 %s 这次没有任何数据，保留上次的内容", p)

    if total == 0:
        logger.error("没有抓到任何事件（学校服务器可能暂时不可用），保留旧数据")
        return 1
    try:
        new, old = staging_commit(failed + missing)
    except RuntimeError as e:
        logger.error("%s", e)
        return 1
    logger.info("同步完成：%d 条事件（之前 %d 条）%s", new, old,
                f"，{len(failed) + len(missing)} 个日历未取到、已保留旧数据" if failed or missing else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())

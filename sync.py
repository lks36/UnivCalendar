"""独立可运行的同步脚本：
    python3 sync.py
拉取官方 CalDAV 全量数据 -> 写入本地数据库 -> 给每个已经选过课的人重新生成各自的 .ics。
适合放进 cron / launchd 定时任务，每天跑一到两次。
"""

import logging
import sys

from models import init_db, replace_events, get_selected_events, get_all_owners
from caldav_client import sync_all
from ics_generator import write_ics_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    init_db()

    logger.info("开始从学校 CalDAV 服务器同步全量课程数据...")
    events = sync_all()
    if not events:
        logger.error("本次同步没有抓到任何事件，请检查网络/服务器地址/凭证是否正确。已保留旧数据，不覆盖。")
        sys.exit(1)

    replace_events(events)
    logger.info("已写入 %d 条事件到本地数据库", len(events))

    owners = get_all_owners()
    for owner in owners:
        selected = get_selected_events(owner)
        path = write_ics_file(owner, selected)
        logger.info("[%s] 已生成 %s（共 %d 个场次）", owner, path, len(selected))

    if not owners:
        logger.info("目前还没有任何人选过课，暂不生成 .ics。")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()

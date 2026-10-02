"""命令行同步：python3 sync.py
从学校 CalDAV 拉取全量课程写入数据库。.ics 订阅文件是访问时现生成的，不需要在这里生成。"""

import logging
import sys

from models import init_db, replace_events
from caldav_client import sync_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    init_db()
    logger.info("开始从学校 CalDAV 服务器同步全量课程数据...")
    events = sync_all()
    if not events:
        logger.error("没有抓到任何事件，请检查网络/凭证。已保留旧数据。")
        sys.exit(1)
    replace_events(events)
    logger.info("已写入 %d 条事件。", len(events))


if __name__ == "__main__":
    main()

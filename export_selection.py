"""在本地导出某个人的选课结果为 selection.json，供提交到 GitHub 给 CI 用（云端单人版）。

用法：
    1. 先跑 python3 app.py，在本地网页 /u/<owner>/ 上选好课
    2. 跑 python3 export_selection.py [owner]（不传 owner 默认是 "me"）
    3. git add selection.json && git commit && git push
       之后 GitHub Actions 会按这份配置定期重新抓取、过滤、生成 .ics
"""

import json
import sys

from models import init_db, get_selection, get_course_groups

OUTPUT_PATH = "selection.json"


def main():
    owner = sys.argv[1] if len(sys.argv) > 1 else "me"

    init_db()
    selected = get_selection(owner)  # {(course_key, session_key_normalized), ...}

    if not selected:
        print(f"「{owner}」目前没有任何勾选的课程，先在本地网页 /u/{owner}/ 上选课再导出。")
        return

    # 从课程列表里找回好看的展示文本（比如 'Cours' 而不是归一化后的 'cours'），
    # 这样 selection.json 打开来看也认得出来是哪个场次
    label_lookup = {}
    for g in get_course_groups():
        for c in g["courses"]:
            for session_key, session_label in c["sessions"]:
                label_lookup[(c["course_key"], session_key)] = session_label

    data = [
        {
            "course_key": course_key,
            "session_type": label_lookup.get((course_key, session_key), session_key),
        }
        for course_key, session_key in sorted(selected)
    ]

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"已导出「{owner}」的 {len(data)} 个场次到 {OUTPUT_PATH}")
    for item in data:
        print(f"  {item['course_key']} - {item['session_type']}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()

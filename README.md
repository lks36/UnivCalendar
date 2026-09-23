# 索邦课表同步助手 — 使用说明

## 1. 安装

```bash
cd sorbonne-cal
python3 -m venv venv
source venv/bin/activate      # Windows 用 venv\Scripts\activate
pip install -r requirements.txt
```

## 2. 首次同步官方课表数据

```bash
python3 sync.py
```

这一步会连接学校 CalDAV 服务器（`cal.ufr-info-p6.jussieu.fr`），拉取所有系/方向的课程，存进本地 `data.db`。
第一次运行日历较多，可能需要一点时间，耐心等。如果报错连不上，检查：

* 网络是否能访问 `cal.ufr-info-p6.jussieu.fr`（部分校外网络可能需要连 VPN）
* `config.py` 里的账号密码是否还是 `student.master` / `guest`（如果学校后续改了访客凭证，需要更新这里）

## 3. 启动选课网页

```bash
python3 app.py
```

然后浏览器打开 **http://localhost:5050**，就能看到全部课程列表，搜索、勾选你实际要上的课和分组，点击"保存并生成 .ics"。

也可以直接在网页上点右上角"重新抓取官方课表"按钮触发同步，不用回到命令行敲 `sync.py`。

## 4. 订阅到手机/电脑日历

网页右侧会显示订阅地址，形如：

```
http://localhost:5050/mon_emploi_du_temps.ics
```

**注意**：这是本机地址，只有这台电脑上的日历 App 能直接订阅。如果想让手机也能订阅：

* **同一个局域网内**（比如宿舍 wifi）：把 `localhost` 换成这台电脑的局域网 IP（如 `192.168.1.23`），手机和电脑连同一个 wifi 时可以访问，但电脑必须一直开着服务。
* **想随时随地都能同步（推荐长期方案）**：把这台电脑设置成开机自动启动这个服务（见下），或者后续升级成部署到云端（如云服务器、树莓派常驻），这样手机在校外也能同步。MVP 阶段先在自己电脑上跑起来验证体验即可。

## 5. 设置自动定时刷新（macOS 示例）

想让课表数据每天自动更新（不用每次手动点"重新抓取"），可以用 macOS 的 `launchd` 或最简单的 `cron`：

```bash
crontab -e
```

加入这一行（每天早上 7 点和中午 12 点各同步一次，按需修改路径）：

```
0 7,12 * * * cd /完整路径/sorbonne-cal && /完整路径/sorbonne-cal/venv/bin/python3 sync.py >> sync.log 2>&1
```

这样即使网页服务没开着，数据也会定时更新；下次打开网页会看到最新数据，且订阅出去的 `.ics` 文件也会自动跟着刷新（只要之前保存过一次选课结果）。

## 6. 项目结构

```
sorbonne-cal/
├── app.py              # Flask 网页服务（选课界面 + API）
├── sync.py             # 独立同步脚本，供命令行/定时任务调用
├── caldav_client.py    # 连接学校 CalDAV、抓取解析课程数据
├── models.py            # SQLite 存储（全量课程 + 用户选课结果）
├── ics_generator.py    # 根据选课结果生成 .ics 文件
├── config.py            # 服务器地址、账号密码等配置
├── templates/index.html # 选课页面
├── static/style.css     # 样式
├── static/app.js        # 前端交互逻辑
└── static/mon_emploi_du_temps.ics  # 生成的订阅文件（运行后才会出现）
```

## 7. 已知限制 / 后续可以做的事

* 课程分组的识别规则是"标题按最后一个 `-` 拆开"，如果发现某些课程标题格式特殊导致分组不对（比如识别出来的 course_key/session 很奇怪），把具体标题发给我，我再调整 `caldav_client.py` 里的 `parse_course_key_and_session` 规则。
* 现在是单用户、无登录，网页直接暴露在 `localhost:5050`，如果以后想给同学也用，需要加多用户支持（当前 PRD 里 v2 范围）。
* 目前没做"云端常驻+随时随地手机同步"，如果确定长期要用，可以考虑把这个 Flask 服务部署到一台常开的小型云服务器上。

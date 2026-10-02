# gunicorn 启动时会自动读取这个文件（不用改 Render 的启动命令）。
# 1 个进程 + 8 个线程：内存缓存和同步状态只有一份，同时一个慢请求也不会堵住其他人。
workers = 1
threads = 8
worker_class = "gthread"
timeout = 120

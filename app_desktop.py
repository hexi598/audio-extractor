#!/usr/bin/env python3
"""
视频音频提取 - 原生桌面应用
使用 pywebview 创建原生窗口，Flask 后台运行
"""

import os
import sys
import time
import socket
import threading
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# 确保依赖路径
PYTHON_SCRIPTS = os.path.join(
    os.path.expandvars(r"%APPDATA%"), "Python", "Python314", "Scripts"
)
if os.path.isdir(PYTHON_SCRIPTS):
    os.environ["PATH"] = PYTHON_SCRIPTS + os.pathsep + os.environ.get("PATH", "")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("114.114.114.114", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def kill_port(port=5000):
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    except Exception:
        pass


def start_flask():
    """在后台线程启动 Flask"""
    from app import app
    app.run(host="0.0.0.0", port=5000, debug=False)


def main():
    # 清理端口
    kill_port(5000)
    time.sleep(0.3)

    # 后台启动 Flask
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    time.sleep(0.8)  # 等 Flask 启动

    # 获取地址
    local_ip = get_local_ip()
    local_url = "http://127.0.0.1:5000"
    lan_url = f"http://{local_ip}:5000" if local_ip != "127.0.0.1" else local_url

    print(f"\n  桌面端: {local_url}")
    if lan_url != local_url:
        print(f"  手机端: {lan_url}")
    print()

    # 创建原生窗口
    try:
        import webview

        window = webview.create_window(
            title="视频音频提取",
            url=local_url,
            width=480,
            height=720,
            min_size=(380, 580),
            resizable=True,
            easy_drag=False,
            background_color="#0f0f1a",
        )
        webview.start(debug=False)
    except Exception as e:
        print(f"\n原生窗口启动失败: {e}")
        print(f"自动回退到浏览器: {local_url}")
        import webbrowser
        webbrowser.open(local_url)
        # 保持 Flask 运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
一键启动器 - 双击此文件或运行 python start.py
- 自动打开桌面浏览器
- 生成手机扫码二维码
- 支持局域网内所有设备访问
"""

import os
import sys
import time
import socket
import webbrowser
import subprocess
import threading
import urllib.parse

# 强制 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("114.114.114.114", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_port_used(port=5000):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False


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


def show_qr(url):
    """在终端打印二维码"""
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:
        pass


def show_startup_info(local_url, lan_url):
    """打印启动信息"""
    box_width = 52
    print()
    print("=" * box_width)
    print("      视频音频提取工具".center(box_width - 4))
    print("=" * box_width)
    print()
    print("  💻  桌面端".center(box_width + 2))
    print(f"      {local_url}".center(box_width + 2))
    print()
    if lan_url != local_url:
        print("  📱  手机端 (同 WiFi 下)".center(box_width + 2))
        print(f"      {lan_url}".center(box_width + 2))
        print()
        # 二维码
        print("  [ 手机扫码访问 ]".center(box_width))
        show_qr(lan_url)

    print()
    print("-" * box_width)
    print("  关闭此窗口即可停止服务".center(box_width - 4))
    print("-" * box_width)
    print()


def main():
    os.chdir(SCRIPT_DIR)

    # 检查依赖
    for lib, name in [("flask", "Flask"), ("yt_dlp", "yt-dlp"),
                       ("mutagen", "mutagen"), ("qrcode", "qrcode")]:
        try:
            __import__(lib)
        except ImportError:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", name],
                capture_output=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    # 清理端口
    if is_port_used(5000):
        kill_port(5000)
        time.sleep(0.5)

    # 获取地址
    local_ip = get_local_ip()
    local_url = "http://127.0.0.1:5000"
    lan_url = f"http://{local_ip}:5000" if local_ip != "127.0.0.1" else local_url

    # 启动信息
    show_startup_info(local_url, lan_url)

    # 延迟打开浏览器
    def open_browser():
        time.sleep(1.2)
        webbrowser.open(local_url)

    threading.Thread(target=open_browser, daemon=True).start()

    # 启动服务
    from app import app
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    except Exception as e:
        print(f"\n[错误] {e}")
        input("\n按 Enter 键退出...")

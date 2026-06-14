#!/usr/bin/env python3
"""
打包脚本 - 将应用编译为单个 .exe 文件
运行: python build_exe.py
输出: dist/视频音频提取.exe
"""

import os
import sys
import subprocess
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# 生成图标
print(">>> 生成应用图标...")
from PIL import Image, ImageDraw
for size in [48, 64, 128, 256]:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 8
    d.rounded_rectangle([m, m, size - m, size - m], radius=size // 5, fill=(124, 58, 237))
    img.save(f"static/icon-{size}.png")
# 生成 .ico (多尺寸)
icon_256 = Image.open("static/icon-256.png")
icon_128 = Image.open("static/icon-128.png").resize((128, 128))
icon_64 = Image.open("static/icon-64.png").resize((64, 64))
icon_48 = Image.open("static/icon-48.png").resize((48, 48))
icon_32 = Image.open("static/icon-128.png").resize((32, 32))
icon_16 = Image.open("static/icon-128.png").resize((16, 16))
icon_256.save(
    "static/app_icon.ico", format="ICO",
    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
)
print("  [OK] app_icon.ico")

# 数据文件收集
PY_SCRIPTS = os.path.expandvars(r"%APPDATA%\Python\Python314\Scripts")
DATA_FILES = [
    ("templates", "templates"),
    ("static", "static"),
    ("bilibili_api.py", "."),
    ("lyrics.py", "."),
    ("app.py", "."),
]

# 隐藏导入
HIDDEN_IMPORTS = [
    "flask", "jinja2", "markupsafe", "werkzeug", "click",
    "yt_dlp", "mutagen", "qrcode", "PIL",
    "json", "re", "hashlib", "urllib",
    "webview", "clr_loader",
]

# PyInstaller 参数
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "AudioExtractor",
    "--icon", "static/app_icon.ico",
    "--add-data", f"templates{os.pathsep}templates",
    "--add-data", f"static{os.pathsep}static",
    "--add-data", f"bilibili_api.py{os.pathsep}.",
    "--add-data", f"lyrics.py{os.pathsep}.",
    "--add-data", f"app.py{os.pathsep}.",
    "--clean",
    "--noconfirm",
]

# 嵌入 ffmpeg
for root, dirs, files in os.walk(
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
):
    for f in files:
        if f == "ffmpeg.exe":
            ffmpeg_dir = root
            cmd.extend([
                "--add-binary", f"{ffmpeg_dir}/ffmpeg.exe{os.pathsep}.",
            ])
            print(f"  [OK] 嵌入 ffmpeg: {ffmpeg_dir}/ffmpeg.exe")
            break
    else:
        continue
    break

# 嵌入 yt-dlp
ytdlp_path = os.path.join(PY_SCRIPTS, "yt-dlp.exe")
if os.path.exists(ytdlp_path):
    cmd.extend([
        "--add-binary", f"{ytdlp_path}{os.pathsep}.",
    ])
    print(f"  [OK] 嵌入 yt-dlp")

for imp in HIDDEN_IMPORTS:
    cmd.extend(["--hidden-import", imp])

cmd.append("app_desktop.py")

print()
print(">>> 开始打包 (可能需要几分钟)...")
print(" ".join(cmd))
print()

result = subprocess.run(cmd, cwd=SCRIPT_DIR)
if result.returncode == 0:
    exe_path = os.path.join(SCRIPT_DIR, "dist", "AudioExtractor.exe")
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print()
    print("=" * 55)
    print(f"  打包成功！")
    print(f"  文件: dist\\AudioExtractor.exe")
    print(f"  大小: {size_mb:.1f} MB")
    print("=" * 55)
else:
    print("\n打包失败")
    sys.exit(1)

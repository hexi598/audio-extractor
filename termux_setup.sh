#!/bin/bash
# ==============================================
#  视频音频提取 - Android Termux 安装脚本
#
#  使用方法（在 Termux 中逐条执行）:
#  1. pkg install wget -y
#  2. wget https://你的IP:5000/static/termux_setup.sh
#  或直接从电脑复制文件到手机
#  3. bash termux_setup.sh
# ==============================================

echo "========================================"
echo "  视频音频提取 - Android 安装"
echo "========================================"

# 1. 更新 Termux
echo ">>> 更新 Termux 包管理器..."
pkg update -y && pkg upgrade -y

# 2. 安装基础依赖
echo ">>> 安装 Python 和 ffmpeg..."
pkg install -y python ffmpeg wget openssl

# 3. 安装 Python 依赖
echo ">>> 安装 Python 库..."
pip install flask yt-dlp mutagen qrcode requests

# 4. 安装可选依赖
echo ">>> 安装可选依赖..."
pip install pillow  # 图标生成

# 5. 创建应用目录
echo ">>> 创建应用目录..."
mkdir -p ~/audio-extractor/downloads
mkdir -p ~/audio-extractor/templates
mkdir -p ~/audio-extractor/static

# 6. 下载应用文件（从电脑复制或通过 HTTP）
# 如果你在电脑上启动了服务器，可以:
# wget http://192.168.x.x:5000/static/bundle.tar.gz
# tar xzf bundle.tar.gz -C ~/audio-extractor/

echo ""
echo "========================================"
echo "  安装完成！"
echo ""
echo "  启动方法:"
echo "    cd ~/audio-extractor"
echo "    python start.py"
echo ""
echo "  然后用手机浏览器打开:"
echo "    http://localhost:5000"
echo "========================================"

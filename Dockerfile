# 视频音频提取 - Docker 镜像
# 基于 Python 3.11-slim，包含 ffmpeg、yt-dlp、gunicorn

FROM python:3.11-slim

# 安装 ffmpeg（Debian 官方源）
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app.py .
COPY bilibili_api.py .
COPY lyrics.py .
COPY templates/ templates/
COPY static/ static/

# 创建下载目录
RUN mkdir -p /tmp/audio-extractor-downloads

# 环境变量
ENV DOWNLOAD_DIR=/tmp/audio-extractor-downloads
ENV FILE_MAX_AGE=1800
ENV MAX_CONCURRENT_TASKS=2
ENV PYTHONUNBUFFERED=1

# 暴露端口（Render 默认注入 PORT=10000）
EXPOSE 10000

# Gunicorn 生产服务器
# --workers 1: 免费层 512MB 内存限制
# --timeout 600: ffmpeg 转码可能需要数分钟
# --threads 2: 允许并发请求
CMD gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 600 --threads 2 app:app

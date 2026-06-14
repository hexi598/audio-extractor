#!/usr/bin/env python3
"""
视频音频提取工具 - Web 界面
启动后浏览器访问 http://127.0.0.1:5000
"""

import os
import sys
import re
import json
import time
import queue
import threading
import subprocess

# 强制 UTF-8 输出
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, Response, send_file

try:
    import lyrics
    HAS_LYRICS = True
except Exception:
    HAS_LYRICS = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

# 添加外部静态文件路由（如 app_icon.ico）
@app.route("/static/<path:filename>")
def static_files(filename):
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE_DIR, "static"), filename)

# 输出目录（使用环境变量，默认 /tmp 适合云端 Docker 环境）
OUTPUT_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/audio-extractor-downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 文件最大保留时间（秒），超时自动清理
FILE_MAX_AGE = int(os.environ.get("FILE_MAX_AGE", "1800"))  # 默认 30 分钟
# 最大并发任务数
MAX_CONCURRENT_TASKS = int(os.environ.get("MAX_CONCURRENT_TASKS", "2"))

# 正在进行的任务 {task_id: {"status": "running/done/error", "message": "", "file": ""}}
tasks = {}
task_lock = threading.Lock()


def find_ffmpeg():
    """自动查找 ffmpeg（支持 Linux / Windows / Docker）"""
    # 优先使用环境变量指定的路径
    env_path = os.environ.get("FFMPEG_PATH", "")
    candidates = []
    if env_path:
        candidates.append(env_path)

    # 通用查找
    candidates.extend(["ffmpeg", "ffmpeg.exe"])

    # Windows 专属路径（保留向后兼容）
    if sys.platform == "win32":
        candidates.extend([
            r"C:\Program Files\FFmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
        ])
        winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.isdir(winget_base):
            for root, dirs, files in os.walk(winget_base):
                if "ffmpeg.exe" in files:
                    candidates.append(os.path.join(root, "ffmpeg.exe"))
                    break

    for path in candidates:
        try:
            subprocess.run([path, "-version"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            return path
        except Exception:
            continue
    return None


def find_ytdlp():
    """查找 yt-dlp（支持 Linux / Windows / Docker）"""
    # 优先使用环境变量指定的路径
    env_path = os.environ.get("YTDLP_PATH", "")
    candidates = []
    if env_path:
        candidates.append(env_path)

    candidates.extend(["yt-dlp", "yt-dlp.exe"])

    # Windows 专属路径（保留向后兼容）
    if sys.platform == "win32":
        import site
        for scripts_dir in [
            site.getusersitepackages().replace("site-packages", "Scripts"),
            os.path.expanduser(r"~\AppData\Roaming\Python\Python314\Scripts"),
        ]:
            path = os.path.join(scripts_dir, "yt-dlp.exe")
            if os.path.exists(path):
                candidates.append(path)

    for name in candidates:
        try:
            subprocess.run([name, "--version"], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, check=True)
            return name
        except Exception:
            continue
    return None


def get_video_title(url, ytdlp_path):
    """获取视频标题"""
    try:
        result = subprocess.run(
            [ytdlp_path, "--print", "%(title)s", "--no-playlist", url],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def sanitize_filename(name):
    """清除非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def cleanup_old_files():
    """清理超过 FILE_MAX_AGE 秒的旧文件"""
    now = time.time()
    try:
        for fname in os.listdir(OUTPUT_DIR):
            fpath = os.path.join(OUTPUT_DIR, fname)
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > FILE_MAX_AGE:
                # 跳过正在处理中的任务文件
                with task_lock:
                    active_files = {t.get("file", "") for t in tasks.values()}
                if fpath not in active_files:
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
    except Exception:
        pass


def start_cleanup_scheduler():
    """后台定期清理旧文件（每 10 分钟）"""
    def _schedule():
        while True:
            time.sleep(600)
            cleanup_old_files()
    t = threading.Thread(target=_schedule, daemon=True)
    t.start()


def inject_lyrics_to_file(mp3_path, title="", task_id=None):
    """搜索歌词并嵌入到 MP3 文件中"""
    if not HAS_LYRICS:
        return None

    artist, song = lyrics.extract_artist_song(title)
    result = lyrics.search_lyrics(artist=artist, song=song, title=title)
    if result and lyrics.embed_lyrics(mp3_path, result["lyrics_lrc"]):
        if task_id:
            with task_lock:
                tasks[task_id]["lyrics_source"] = result.get("source", "")
                tasks[task_id]["has_lyrics"] = True
        return result
    return None


def is_bilibili_url(url):
    """判断是否是 B站链接"""
    return bool(re.search(r"bilibili\.com|b23\.tv|BV[a-zA-Z0-9]{10}", url))


def extract_bilibili(task_id, url, output_name, audio_format, want_lyrics=True):
    """使用自定义 API 提取 B站音频"""
    import bilibili_api as bl

    with task_lock:
        tasks[task_id] = {"status": "running", "message": "正在解析 B站链接..."}

    try:
        bvid = bl.extract_bvid(url)
    except Exception as e:
        with task_lock:
            tasks[task_id] = {"status": "error", "message": f"链接解析失败: {e}"}
        return

    try:
        info = bl.get_video_info(bvid)
    except Exception as e:
        with task_lock:
            tasks[task_id] = {"status": "error", "message": f"获取视频信息失败: {e}"}
        return

    title = info["title"]
    with task_lock:
        tasks[task_id] = {
            "status": "running",
            "message": f"视频: {title[:50]}...",
        }

    try:
        audio_url, backup_urls, bw, codec = bl.get_audio_url(bvid, info["cid"])
    except Exception as e:
        with task_lock:
            tasks[task_id] = {"status": "error", "message": f"获取音频流失败: {e}"}
        return

    safe_name = sanitize_filename(output_name or title)
    output_file = os.path.join(OUTPUT_DIR, f"{safe_name}.{audio_format}")

    with task_lock:
        tasks[task_id] = {
            "status": "running",
            "message": f"正在下载音频 ({bw//1000}kbps)...",
        }

    try:
        ffmpeg_path = find_ffmpeg()
        if not ffmpeg_path:
            raise RuntimeError("未找到 ffmpeg")

        # 下载原始音频流
        raw_file = os.path.join(OUTPUT_DIR, f".bili_temp_{task_id}")
        bl._download_raw_audio(audio_url, raw_file, backup_urls)

        with task_lock:
            tasks[task_id] = {"status": "running", "message": "正在转码为 MP3..."}

        # 转码
        subprocess.run([
            ffmpeg_path, "-y",
            "-i", raw_file,
            "-acodec", "libmp3lame",
            "-b:a", "320k", "-vn",
            output_file,
        ], check=True, capture_output=True, timeout=120)

        # 清理临时文件
        if os.path.exists(raw_file):
            os.remove(raw_file)

        if os.path.exists(output_file):
            with task_lock:
                tasks[task_id] = {
                    "status": "done",
                    "message": "完成！",
                    "file": output_file,
                    "filename": os.path.basename(output_file),
                    "title": title,
                }
            # 注入歌词
            if want_lyrics and HAS_LYRICS:
                ly_result = inject_lyrics_to_file(output_file, title, task_id)
                if ly_result:
                    with task_lock:
                        tasks[task_id]["message"] = f"完成！(已嵌入歌词: {ly_result['source']})"
        else:
            with task_lock:
                tasks[task_id] = {
                    "status": "error",
                    "message": "转码完成但未找到输出文件",
                }
    except Exception as e:
        with task_lock:
            tasks[task_id] = {"status": "error", "message": str(e)}


def extract_task(task_id, url, output_name, audio_format, quality, want_lyrics=True):
    """后台提取任务（自动识别平台）"""

    # B站使用专用 API
    if is_bilibili_url(url):
        return extract_bilibili(task_id, url, output_name, audio_format, want_lyrics)

    # 其他平台使用 yt-dlp
    ytdlp_path = find_ytdlp()
    ffmpeg_path = find_ffmpeg()

    if not ytdlp_path:
        with task_lock:
            tasks[task_id] = {"status": "error", "message": "未找到 yt-dlp"}
        return

    with task_lock:
        tasks[task_id] = {"status": "running", "message": "正在获取视频信息..."}

    title = get_video_title(url, ytdlp_path)
    if not output_name:
        output_name = title or "audio"

    safe_name = sanitize_filename(output_name)
    output_template = os.path.join(OUTPUT_DIR, f"{safe_name}.%(ext)s")

    cmd = [
        ytdlp_path, "-x",
        "--audio-format", audio_format,
        "--audio-quality", str(quality),
        "-o", output_template,
        "--no-playlist",
        "--ffmpeg-location", ffmpeg_path,
        "--embed-metadata",
        "--trim-filenames", "200",
        url,
    ]

    expected_file = os.path.join(OUTPUT_DIR, f"{safe_name}.{audio_format}")

    with task_lock:
        tasks[task_id] = {"status": "running", "message": "正在下载和转换音频..."}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        last_update = 0
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            line = line.strip()
            if line:
                if "[download]" in line and "%" in line:
                    now = time.time()
                    if now - last_update > 0.3:
                        last_update = now
                        pct_match = re.search(r'(\d+\.?\d*)%', line)
                        if pct_match:
                            pct = pct_match.group(1)
                            with task_lock:
                                tasks[task_id] = {
                                    "status": "running",
                                    "message": f"下载中... {pct}%",
                                }
                elif "[ExtractAudio]" in line:
                    with task_lock:
                        tasks[task_id] = {
                            "status": "running",
                            "message": "正在转码音频...",
                        }

        proc.wait()

        if proc.returncode == 0:
            found_file = None
            if os.path.exists(expected_file):
                found_file = expected_file
            else:
                for f in os.listdir(OUTPUT_DIR):
                    if f.startswith(safe_name) and f.endswith(f".{audio_format}"):
                        found_file = os.path.join(OUTPUT_DIR, f)
                        break

            if found_file:
                with task_lock:
                    tasks[task_id] = {
                        "status": "done",
                        "message": "完成！",
                        "file": found_file,
                        "filename": os.path.basename(found_file),
                        "title": title or safe_name,
                    }
                # 注入歌词
                if want_lyrics and HAS_LYRICS:
                    ly_result = inject_lyrics_to_file(
                        found_file, title or safe_name, task_id
                    )
                    if ly_result:
                        with task_lock:
                            tasks[task_id]["message"] = f"完成！(已嵌入歌词: {ly_result['source']})"
            else:
                with task_lock:
                    tasks[task_id] = {
                        "status": "error",
                        "message": "转换完成但未找到输出文件",
                    }
        else:
            with task_lock:
                tasks[task_id] = {
                    "status": "error",
                    "message": f"下载失败 (错误码: {proc.returncode})",
                }
    except Exception as e:
        with task_lock:
            tasks[task_id] = {"status": "error", "message": str(e)}


# ---- 路由 ----

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/extract", methods=["POST"])
def api_extract():
    data = request.get_json()
    url = data.get("url", "").strip()
    output_name = data.get("output_name", "").strip() or None
    audio_format = data.get("format", "mp3")
    quality = data.get("quality", 0)
    want_lyrics = data.get("lyrics", True)

    if not url:
        return jsonify({"error": "请输入视频链接"}), 400

    if not re.match(r'^https?://', url):
        return jsonify({"error": "请输入有效的视频链接（以 http:// 或 https:// 开头）"}), 400

    # 并发任务限制
    with task_lock:
        active_count = sum(1 for t in tasks.values()
                          if t.get("status") in ("running", "pending"))
    if active_count >= MAX_CONCURRENT_TASKS:
        return jsonify({
            "error": f"服务器繁忙，当前有 {active_count} 个任务在处理中，请稍后再试"
        }), 429

    # 启动前清理旧文件
    cleanup_old_files()

    task_id = str(int(time.time() * 1000))
    with task_lock:
        tasks[task_id] = {"status": "pending", "message": "排队中..."}

    thread = threading.Thread(
        target=extract_task,
        args=(task_id, url, output_name, audio_format, quality, want_lyrics),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def api_status(task_id):
    with task_lock:
        task = tasks.get(task_id, {"status": "not_found", "message": "任务不存在"})
    return jsonify(task)


@app.route("/api/download/<task_id>")
def api_download(task_id):
    with task_lock:
        task = tasks.get(task_id, {})
    filepath = task.get("file", "")
    if not filepath or not os.path.exists(filepath):
        return "文件不存在或已过期", 404
    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))


@app.route("/api/check-tools")
def api_check_tools():
    ytdlp = find_ytdlp()
    ffmpeg = find_ffmpeg()
    return jsonify({
        "ytdlp": bool(ytdlp),
        "ffmpeg": bool(ffmpeg),
        "ytdlp_path": ytdlp or "",
        "ffmpeg_path": ffmpeg or "",
    })


@app.route("/api/health")
def api_health():
    """健康检查端点（供云平台使用）"""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # 启动后台清理调度器
    start_cleanup_scheduler()
    # 从环境变量读取端口（云平台自动注入 PORT），本地默认 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

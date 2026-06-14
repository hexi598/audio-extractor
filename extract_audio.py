#!/usr/bin/env python3
"""
视频音频提取工具
支持 YouTube、Bilibili、Twitter、TikTok 等数千个网站的视频音频提取。
直接输出 MP3 格式。

用法:
    python extract_audio.py <视频链接> [选项]

示例:
    python extract_audio.py "https://www.youtube.com/watch?v=xxxxx"
    python extract_audio.py "https://www.bilibili.com/video/BVxxxxx" -o "我的音频"
    python extract_audio.py "https://www.youtube.com/watch?v=xxxxx" --format m4a
    python extract_audio.py "https://www.youtube.com/playlist?list=xxxxx" --playlist
"""

import argparse
import os
import subprocess
import sys
import re

# 强制 UTF-8 输出，解决 Windows GBK 终端 emoji 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---- 配置 ----
# 如果 ffmpeg/yt-dlp 不在 PATH 中，在这里指定完整路径
YTDLP_PATH = "yt-dlp"
FFMPEG_PATH = None  # 设为 None 则自动查找，或设为完整路径如 r"C:\ffmpeg\bin\ffmpeg.exe"


def find_ffmpeg():
    """自动查找 ffmpeg"""
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH

    # 常见安装位置
    candidates = [
        "ffmpeg",
        "ffmpeg.exe",
        r"C:\Program Files\FFmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]

    # 搜索 WinGet 安装位置
    winget_base = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
    )
    if os.path.isdir(winget_base):
        for root, dirs, files in os.walk(winget_base):
            if "ffmpeg.exe" in files:
                candidates.append(os.path.join(root, "ffmpeg.exe"))
                break

    for path in candidates:
        try:
            subprocess.run([path, "-version"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           check=True)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    return None


def find_ytdlp():
    """查找 yt-dlp"""
    try:
        subprocess.run([YTDLP_PATH, "--version"],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       check=True)
        return YTDLP_PATH
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 搜索 pip 用户安装位置
    import site
    for scripts_dir in [site.getusersitepackages().replace("site-packages", "Scripts"),
                        os.path.expanduser(r"~\AppData\Roaming\Python\Python314\Scripts")]:
        path = os.path.join(scripts_dir, "yt-dlp.exe")
        if os.path.exists(path):
            return path

    return None


def sanitize_filename(name):
    """清除文件名中的非法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def get_video_info(url, ytdlp_path):
    """获取视频标题"""
    try:
        result = subprocess.run(
            [ytdlp_path, "--print", "%(title)s", "--no-playlist", url],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def download_audio(url, output_name, audio_format, quality, ytdlp_path, ffmpeg_path,
                   playlist=False, output_dir=None, verbose=False):
    """
    下载视频并提取音频。

    参数:
        url: 视频链接
        output_name: 输出文件名（不含扩展名），None 则使用视频标题
        audio_format: 输出格式 (mp3, m4a, wav, flac, opus, aac)
        quality: 音质 (0-10, 0=最好)
        ytdlp_path: yt-dlp 路径
        ffmpeg_path: ffmpeg 路径
        playlist: 是否下载整个播放列表
        output_dir: 输出目录
        verbose: 详细输出模式
    """
    if output_dir is None:
        output_dir = os.getcwd()

    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    cmd = [
        ytdlp_path,
        "-x",  # 只提取音频
        "--audio-format", audio_format,
        "--audio-quality", str(quality),
        "-o", output_template,
        "--no-playlist" if not playlist else "--yes-playlist",
        "--ffmpeg-location", ffmpeg_path,
        # 嵌入缩略图和元数据
        "--embed-metadata",
        "--embed-thumbnail",
        # 限制文件名长度
        "--trim-filenames", "200",
        url,
    ]

    if output_name:
        # 如果指定了输出名称，使用它
        cmd = [
            ytdlp_path,
            "-x",
            "--audio-format", audio_format,
            "--audio-quality", str(quality),
            "-o", os.path.join(output_dir, f"{output_name}.%(ext)s"),
            "--no-playlist" if not playlist else "--yes-playlist",
            "--ffmpeg-location", ffmpeg_path,
            "--embed-metadata",
            "--embed-thumbnail",
            "--trim-filenames", "200",
            url,
        ]

    if verbose:
        cmd.append("--verbose")

    print(f"\n{'='*60}")
    print(f"  视频音频提取工具")
    print(f"{'='*60}")
    print(f"  链接: {url}")
    print(f"  格式: {audio_format}")
    print(f"  音质: {quality} (0=最佳)")
    print(f"  输出: {output_dir}")
    print(f"{'='*60}\n")

    # 获取视频信息
    print("🔍 正在获取视频信息...")
    title = get_video_info(url, ytdlp_path)
    if title:
        print(f"📺 视频标题: {title}")

    print("⬇️  开始下载和转换...\n")

    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            print(f"\n✅ 完成！音频已保存到: {output_dir}")
        else:
            print(f"\n❌ 下载失败，错误码: {result.returncode}",
                  file=sys.stderr)
            print("💡 提示：尝试加 --verbose 查看详细错误信息",
                  file=sys.stderr)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        sys.exit(130)


def main():
    parser = argparse.ArgumentParser(
        description="从视频链接中提取音频（支持 YouTube、Bilibili、Twitter 等数千网站）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "https://www.youtube.com/watch?v=abc123"
  %(prog)s "https://www.bilibili.com/video/BV1xx411c7mD" -o "我的音乐"
  %(prog)s "https://www.youtube.com/watch?v=abc123" --format flac --quality 0
  %(prog)s "https://www.youtube.com/playlist?list=xxx" --playlist -d ./music
        """,
    )
    parser.add_argument("url", help="视频链接")
    parser.add_argument("-o", "--output", default=None,
                        help="输出文件名（不含扩展名），默认使用视频标题")
    parser.add_argument("-d", "--output-dir", default=None,
                        help="输出目录，默认当前目录")
    parser.add_argument("--format", default="mp3",
                        choices=["mp3", "m4a", "wav", "flac", "opus", "aac", "vorbis"],
                        help="音频格式 (默认: mp3)")
    parser.add_argument("--quality", type=int, default=0,
                        help="音质 0=最佳, 10=最差 (默认: 0)")
    parser.add_argument("--playlist", action="store_true",
                        help="下载整个播放列表（默认只下载单个视频）")
    parser.add_argument("--verbose", action="store_true",
                        help="显示详细日志")
    parser.add_argument("--list-formats", action="store_true",
                        help="仅列出可用的格式，不下载")

    args = parser.parse_args()

    # 查找依赖工具
    print("🔧 正在检查工具...")
    ytdlp_path = find_ytdlp()
    if not ytdlp_path:
        print("❌ 未找到 yt-dlp！请先安装: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)
    print(f"  ✅ yt-dlp: {ytdlp_path}")

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        print("❌ 未找到 ffmpeg！请先安装 ffmpeg", file=sys.stderr)
        print("   下载地址: https://ffmpeg.org/download.html", file=sys.stderr)
        print("   或使用: winget install ffmpeg", file=sys.stderr)
        sys.exit(1)
    print(f"  ✅ ffmpeg: {ffmpeg_path}")

    # 仅列出格式
    if args.list_formats:
        print("\n📋 可用格式:\n")
        subprocess.run([ytdlp_path, "-F", args.url])
        return

    # 下载音频
    download_audio(
        url=args.url,
        output_name=sanitize_filename(args.output) if args.output else None,
        audio_format=args.format,
        quality=args.quality,
        ytdlp_path=ytdlp_path,
        ffmpeg_path=ffmpeg_path,
        playlist=args.playlist,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
